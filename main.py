from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import List
import gspread
from google.oauth2.service_account import Credentials
import math
from geopy.distance import geodesic

# Google Sheets authentication
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
gc = gspread.authorize(creds)

# Sheet setup
SHEET_NAME = "Foreclosure Deals"
WORKSHEET_NAME = "Sheet1"

worksheet = gc.open(SHEET_NAME).worksheet(WORKSHEET_NAME)

# Load worksheet values
records = worksheet.get_all_records()

# Static coordinates for reference points
REFERENCE_POINTS = {
    "Mt. Juliet": (36.2006, -86.5186),
    "Nashville": (36.1627, -86.7816),
}


def calculate_drive_time(address: str, reference_coords: tuple) -> float:
    # In real implementation, you'd use Google Maps API
    # Here we simulate drive time as 1.3x straight-line distance (in miles) converted to minutes
    try:
        from geopy.geocoders import Nominatim
        geolocator = Nominatim(user_agent="foreclosure-finder")
        location = geolocator.geocode(address)
        if location:
            address_coords = (location.latitude, location.longitude)
            miles = geodesic(reference_coords, address_coords).miles
            return round(miles * 1.3)  # Approximate drive time in minutes
        else:
            return math.inf
    except Exception:
        return math.inf


app = FastAPI()

# Allow requests from any origin (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/get_properties")
def get_properties(
    location: str = Query(..., description="City name (e.g., 'Mt. Juliet')"),
    max_drive_time: int = Query(..., description="Maximum drive time in minutes")
) -> List[dict]:
    if location not in REFERENCE_POINTS:
        return {"error": f"Location '{location}' is not supported."}

    reference_coords = REFERENCE_POINTS[location]
    filtered_properties = []

    for row in records:
        address = row.get("Property Address")
        if not address:
            continue

        drive_time = calculate_drive_time(address, reference_coords)
        if drive_time <= max_drive_time:
            row["Drive Time (min)"] = drive_time
            filtered_properties.append(row)

    return filtered_properties
