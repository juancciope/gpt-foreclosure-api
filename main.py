import re
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, time
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable

app = FastAPI()

# --- Configuration ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)
SHEET_NAME = "Foreclosure Deals"
WORKSHEET_NAME = "Sheet1"
CREDENTIALS_FILE = "credentials2.json"

# --- Services and Caching ---
geolocator = Nominatim(user_agent="foreclosure_finder_app_v3")
geocode_cache = {}

# --- Google Sheets Connection ---
try:
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scope)
    gc = gspread.authorize(creds)
    worksheet = gc.open(SHEET_NAME).worksheet(WORKSHEET_NAME)
except Exception as e:
    print(f"CRITICAL ERROR: Could not connect to Google Sheets. {e}")
    worksheet = None

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

def get_coords(location_str: str, row_context=None):
    normalized_location = location_str.strip().lower()
    if normalized_location in geocode_cache:
        return geocode_cache[normalized_location]
    coords = None
    try:
        location = geolocator.geocode(normalized_location, timeout=5)
        if location:
            coords = (location.latitude, location.longitude)
        elif row_context:
            for fallback_key in ['City', 'ZipCode']:
                fallback_val = row_context.get(fallback_key)
                if fallback_val:
                    fallback_str = str(fallback_val).lower()
                    if fallback_str in geocode_cache: return geocode_cache[fallback_str]
                    fallback_loc = geolocator.geocode(fallback_str, timeout=5)
                    if fallback_loc:
                        coords = (fallback_loc.latitude, fallback_loc.longitude)
                        geocode_cache[fallback_str] = coords
                        break # Found a fallback, stop trying
    except (GeocoderTimedOut, GeocoderUnavailable):
        print(f"Geocoding service timed out for: {normalized_location}")
    except Exception as e:
        print(f"An error occurred during geocoding for {normalized_location}: {e}")
    geocode_cache[normalized_location] = coords
    return coords

def parse_date_query(query: str):
    today = datetime.now().date()
    query_lower = query.strip().lower()
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
    pattern = re.compile(r"(?:(at least|more than|over|greater than)\s*)?(?:(at most|within|less than|under)\s*)?(\d+(?:\.\d+)?)\s*(mile|min|minute|hr|hour)s?\s*(?:from|of|around|near)?\s*(.+)", re.IGNORECASE)
    match = pattern.search(query)
    if not match: return None
    min_comp, max_comp, val_str, unit, loc_str = match.groups()
    dist = float(val_str)
    if 'min' in unit: dist *= 0.8
    elif 'hr' in unit: dist *= 45
    min_dist, max_dist = (dist, None) if min_comp else (None, dist if max_comp else dist)
    target_coords = get_coords(loc_str)
    return (max_dist, min_dist, target_coords) if target_coords else None

def parse_time_of_day_query(query: str):
    """Parses 'morning', 'afternoon', 'evening' and returns a time range."""
    query_lower = query.lower()
    if "morning" in query_lower:
        return time(7, 0), time(12, 0) # 7:00 AM to 12:00 PM
    if "afternoon" in query_lower:
        return time(12, 0), time(17, 0) # 12:00 PM to 5:00 PM
    if "evening" in query_lower:
        return time(17, 0), time(21, 0) # 5:00 PM to 9:00 PM
    return None

# --- Main API Endpoint ---
@app.post("/query_foreclosure_sheet", response_model=list[Property])
def query_foreclosure_sheet(payload: QueryRequestModel):
    if not worksheet: return [{"error": "Google Sheet not accessible."}]

    query = payload.query.strip()
    data = worksheet.get_all_records()
    
    # --- Detect all possible filters in the query ---
    distance_params = parse_distance_query(query)
    date_range = parse_date_query(query)
    time_range = parse_time_of_day_query(query)
    # Simple keywords are what's left after removing common filter words
    keywords = re.sub(r'(in|for|at|the|a|are|that|show|me|give|find|listings|properties|list|homes|sale)', '', query, flags=re.I).split()
    
    results = []
    for row in data:
        # --- Assume row is a match until a filter fails ---
        is_match = True
        
        # 1. Apply Distance Filter
        if distance_params:
            max_dist, min_dist, target_coords = distance_params
            address = f"{row.get('PropertyAddress', '')}, {row.get('City', '')}, {row.get('ZipCode', '')}"
            prop_coords = get_coords(address, row_context=row)
            if not prop_coords:
                is_match = False
            else:
                dist = geodesic(target_coords, prop_coords).miles
                if max_dist is not None and dist > max_dist: is_match = False
                if min_dist is not None and dist < min_dist: is_match = False

        # 2. Apply Date Filter (if still a match)
        if is_match and date_range:
            sale_date_str = row.get("SaleDate")
            if not sale_date_str: is_match = False
            else:
                try:
                    sale_date = datetime.strptime(sale_date_str, "%m/%d/%Y").date()
                    if not (date_range[0] <= sale_date <= date_range[1]): is_match = False
                except (ValueError, TypeError): is_match = False

        # 3. Apply Time of Day Filter (if still a match)
        if is_match and time_range:
            sale_time_str = row.get("SaleTime")
            if not sale_time_str: is_match = False
            else:
                try:
                    # Handles formats like "10:00 AM" or "1:30 PM"
                    sale_time = datetime.strptime(sale_time_str, "%I:%M %p").time()
                    if not (time_range[0] <= sale_time <= time_range[1]): is_match = False
                except (ValueError, TypeError): is_match = False

        # 4. Apply Keyword Filter (if still a match)
        if is_match and keywords:
             row_text = " ".join([str(v).strip().lower() for v in row.values()])
             if not all(kw.lower() in row_text for kw in keywords):
                 is_match = False

        # If all checks passed, add to results
        if is_match:
            results.append(row)

    return [Property(**row) for row in results]
