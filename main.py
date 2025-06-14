import re
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, time
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable
from functools import lru_cache

app = FastAPI()

# --- Configuration ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)
SHEET_NAME = "Foreclosure Deals"
WORKSHEET_NAME = "Sheet1"
CREDENTIALS_FILE = "credentials2.json"

# --- Services ---
geolocator = Nominatim(user_agent="foreclosure_finder_app_v4")

# --- Google Sheets Connection & Data Caching ---
@lru_cache(maxsize=1)
def get_sheet_data():
    """Caches the sheet data to avoid repeated API calls to Google."""
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scope)
        gc = gspread.authorize(creds)
        worksheet = gc.open(SHEET_NAME).worksheet(WORKSHEET_NAME)
        data = worksheet.get_all_records()
        
        # Extract unique locations for smarter searching
        all_cities = set(row['City'].lower() for row in data if row.get('City'))
        all_counties = set(row['County'].lower() for row in data if row.get('County'))
        known_locations = all_cities.union(all_counties)

        return data, known_locations
    except Exception as e:
        print(f"CRITICAL ERROR: Could not connect to Google Sheets. {e}")
        return [], set()

# --- API Data Models ---
class QueryRequestModel(BaseModel):
    query: str

class Property(BaseModel):
    PropertyAddress: str
    SaleDate: str
    SaleTime: str
    City: str
    County: str
    ZipCode: str
    Source: str

# --- Smart Parsing Helper Functions ---

@lru_cache(maxsize=128)
def get_coords(location_str: str):
    """Geocodes a location string with caching."""
    try:
        location = geolocator.geocode(location_str.strip().lower(), timeout=5)
        if location:
            return (location.latitude, location.longitude)
    except (GeocoderTimedOut, GeocoderUnavailable):
        print(f"Geocoding service timed out for: {location_str}")
    return None

def parse_date_query(query: str):
    query_lower = query.lower()
    today = datetime.now().date()
    if "today" in query_lower: return today, today
    if "tomorrow" in query_lower: return today + timedelta(days=1), today + timedelta(days=1)
    if "this week" in query_lower:
        start = today - timedelta(days=today.weekday())
        return start, start + timedelta(days=6)
    if "next week" in query_lower:
        start = today + timedelta(days=(7 - today.weekday()))
        return start, start + timedelta(days=6)
    return None

def parse_distance_query(query: str):
    pattern = re.compile(r"(at least|more than|over|greater than|at most|within|less than|under)?\s*(\d+(?:\.\d+)?)\s*(mile|min|minute|hr|hour)s?\s*(?:from|of|around|near)?\s*(.+)", re.IGNORECASE)
    match = pattern.search(query)
    if not match: return None
    comp, val_str, unit, loc_str = match.groups()
    dist = float(val_str)
    if 'min' in unit: dist *= 0.8
    elif 'hr' in unit: dist *= 45
    
    min_dist, max_dist = (dist, None) if comp and comp.lower() in ["at least", "more than", "over", "greater than"] else (None, dist)
    target_coords = get_coords(loc_str)
    return (max_dist, min_dist, target_coords) if target_coords else None

def parse_time_of_day_query(query: str):
    query_lower = query.lower()
    if "morning" in query_lower: return time(7, 0), time(12, 0)
    if "afternoon" in query_lower: return time(12, 0), time(17, 0)
    if "evening" in query_lower: return time(17, 0), time(21, 0)
    return None

# --- Main API Endpoint ---
@app.post("/query_foreclosure_sheet", response_model=list[Property])
def query_foreclosure_sheet(payload: QueryRequestModel):
    data, known_locations = get_sheet_data()
    if not data: return []

    query = payload.query.strip()
    query_lower = query.lower()

    # --- Step 1: Parse all possible filters from the query ---
    distance_params = parse_distance_query(query)
    date_range = parse_date_query(query)
    time_range = parse_time_of_day_query(query)
    
    location_keywords = []
    if not distance_params:
        location_keywords = [loc for loc in known_locations if loc in query_lower]

    # --- Step 2: Iteratively filter the data ---
    results = []
    for row in data:
        is_match = True

        if date_range:
            sale_date_str = row.get("SaleDate")
            if not sale_date_str: is_match = False
            else:
                try:
                    sale_date = datetime.strptime(sale_date_str, "%m/%d/%Y").date()
                    if not (date_range[0] <= sale_date <= date_range[1]): is_match = False
                except (ValueError, TypeError): is_match = False
        if not is_match: continue

        if time_range:
            sale_time_str = row.get("SaleTime")
            if not sale_time_str: is_match = False
            else:
                try:
                    sale_time = datetime.strptime(sale_time_str, "%I:%M %p").time()
                    if not (time_range[0] <= sale_time <= time_range[1]): is_match = False
                except (ValueError, TypeError): is_match = False
        if not is_match: continue

        if distance_params:
            max_dist, min_dist, target_coords = distance_params
            address = f"{row.get('PropertyAddress', '')}, {row.get('City', '')}, TN"
            prop_coords = get_coords(address)
            if not prop_coords: is_match = False
            else:
                dist = geodesic(target_coords, prop_coords).miles
                if max_dist is not None and dist > max_dist: is_match = False
                if min_dist is not None and dist < min_dist: is_match = False
        if not is_match: continue

        if location_keywords:
            row_loc_text = f"{row.get('City', '')} {row.get('County', '')}".lower()
            if not any(loc in row_loc_text for loc in location_keywords):
                is_match = False
        if not is_match: continue
        
        if not any([distance_params, date_range, time_range, location_keywords]):
             if query_lower not in " ".join(str(v).lower() for v in row.values()):
                 is_match = False
        if not is_match: continue

        results.append(row)

    # --- Step 3: Format and Validate the final results ---
    validated_results = []
    for r in results:
        try:
            # Explicitly cast all values to string to match the Pydantic model and prevent errors.
            property_instance = Property(
                PropertyAddress=str(r.get("PropertyAddress", "")),
                SaleDate=str(r.get("SaleDate", "")),
                SaleTime=str(r.get("SaleTime", "")),
                City=str(r.get("City", "")),
                County=str(r.get("County", "")),
                ZipCode=str(r.get("ZipCode", "")),
                Source=str(r.get("Source", ""))
            )
            validated_results.append(property_instance)
        except ValidationError as e:
            # This will log if a row has fundamentally invalid data that even casting can't fix.
            print(f"Skipping row due to validation error: {r} -> {e}")

    return validated_results
