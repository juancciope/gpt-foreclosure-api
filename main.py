import re
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable

app = FastAPI()

# --- Configuration ---
# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Google Sheets Configuration
SHEET_NAME = "Foreclosure Deals"
WORKSHEET_NAME = "Sheet1"
CREDENTIALS_FILE = "credentials2.json"

# --- Services and Caching ---
# Initialize geolocator (Nominatim is free and doesn't require an API key)
geolocator = Nominatim(user_agent="foreclosure_finder_app")
# Cache for storing coordinates of already looked-up locations to speed up requests
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

# --- Helper Functions ---

def get_coords(location_str: str):
    """Geocodes a location string and caches the result."""
    if location_str in geocode_cache:
        return geocode_cache[location_str]
    try:
        location = geolocator.geocode(location_str)
        if location:
            coords = (location.latitude, location.longitude)
            geocode_cache[location_str] = coords
            return coords
    except (GeocoderTimedOut, GeocoderUnavailable):
        print(f"Geocoding service timed out for: {location_str}")
    except Exception as e:
        print(f"An error occurred during geocoding for {location_str}: {e}")
    
    geocode_cache[location_str] = None # Cache failure to avoid retrying
    return None

def parse_date_query(query: str):
    """Parses relative date queries like 'today' or 'next week'."""
    today = datetime.now().date()
    query = query.strip().lower()
    if query == "today":
        return today, today
    if query == "tomorrow":
        tomorrow = today + timedelta(days=1)
        return tomorrow, tomorrow
    if query == "this week":
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        return start_of_week, end_of_week
    if query == "next week":
        start_of_next_week = today + timedelta(days=(7 - today.weekday()))
        end_of_next_week = start_of_next_week + timedelta(days=6)
        return start_of_next_week, end_of_next_week
    return None

def parse_distance_query(query: str):
    """
    Parses natural language distance queries like "within 10 miles of Nashville".
    Returns a tuple of (distance_in_miles, target_location_coords) or None.
    """
    # Regex to find patterns like "10 miles from nashville" or "30 minutes of 37209"
    pattern = re.compile(r"(\d+)\s*(mile|min|minute|hr|hour)s?\s*(from|of|around)\s*(.*)", re.IGNORECASE)
    match = pattern.search(query)

    if not match:
        return None

    value, unit, _, location_str = match.groups()
    distance = float(value)
    location_str = location_str.strip()

    # Simplistic conversion of time to distance. 
    # ASSUMPTION: 1 minute of driving = 0.8 miles. This is a huge simplification!
    if 'min' in unit:
        distance *= 0.8
    elif 'h' in unit:
        distance *= 45 # Assuming ~45 mph average travel speed

    target_coords = get_coords(location_str)
    if not target_coords:
        return None # Could not find the location user asked for

    return distance, target_coords

# --- Main API Endpoint ---
@app.post("/query_foreclosure_sheet", response_model=list[Property])
def query_foreclosure_sheet(payload: QueryRequestModel):
    if not worksheet:
        return [{"error": "Google Sheet not accessible. Check server logs."}]

    query = payload.query.strip()
    data = worksheet.get_all_records()
    results = []

    # --- Search Logic Priority ---
    # 1. Try to parse as a distance query first
    # 2. Then, try to parse as a date query
    # 3. Finally, fall back to a generic keyword search

    distance_params = parse_distance_query(query)
    date_range = parse_date_query(query)

    if distance_params:
        # --- 1. GEOGRAPHIC DISTANCE SEARCH ---
        max_distance_miles, target_coords = distance_params
        for row in data:
            address = f"{row.get('PropertyAddress', '')}, {row.get('City', '')}, {row.get('ZipCode', '')}"
            property_coords = get_coords(address)
            if property_coords:
                distance = geodesic(target_coords, property_coords).miles
                if distance <= max_distance_miles:
                    results.append(row)

    elif date_range:
        # --- 2. DATE-BASED SEARCH ---
        start_date, end_date = date_range
        for row in data:
            sale_date_str = row.get("SaleDate")
            if not sale_date_str: continue
            try:
                sale_date = datetime.strptime(sale_date_str, "%m/%d/%Y").date()
                if start_date <= sale_date <= end_date:
                    results.append(row)
            except (ValueError, TypeError):
                continue
    
    else:
        # --- 3. GENERAL KEYWORD SEARCH (Fallback) ---
        query_lower = query.lower()
        for row in data:
            row_text = " ".join([str(v).strip().lower() for v in row.values()])
            if query_lower in row_text:
                results.append(row)

    # Format results to match Pydantic model
    formatted_results = [
        {
            "PropertyAddress": str(row.get("PropertyAddress", "")),
            "SaleDate": str(row.get("SaleDate", "")),
            "SaleTime": str(row.get("SaleTime", "")),
            "City": str(row.get("City", "")),
            "County": str(row.get("County", "")),
            "ZipCode": str(row.get("ZipCode", "")),
            "Source": str(row.get("Source", "")),
        }
        for row in results
    ]

    return formatted_results
