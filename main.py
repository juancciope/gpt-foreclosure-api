from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta

app = FastAPI()

# CORS setup to allow all origins, which is fine for development
# For production, you might want to restrict this to your frontend's domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Google Sheets Configuration ---
# IMPORTANT: Make sure your credentials file is in the same directory
# or provide the full path.
SHEET_NAME = "Foreclosure Deals"
WORKSHEET_NAME = "Sheet1"
CREDENTIALS_FILE = "credentials2.json"

try:
    # Set up credentials and authorize gspread
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scope)
    gc = gspread.authorize(creds)
    worksheet = gc.open(SHEET_NAME).worksheet(WORKSHEET_NAME)
except FileNotFoundError:
    print(f"ERROR: Credentials file not found at '{CREDENTIALS_FILE}'.")
    worksheet = None
except Exception as e:
    print(f"An error occurred during Google Sheets setup: {e}")
    worksheet = None

# --- API Data Models ---

class QueryRequestModel(BaseModel):
    """Model for incoming search queries."""
    query: str

class Property(BaseModel):
    """Model for the property data returned by the API."""
    PropertyAddress: str
    SaleDate: str
    SaleTime: str
    City: str
    County: str
    ZipCode: str
    Source: str

# --- Helper Function for Date Parsing ---

def parse_date_query(query: str):
    """
    Checks if the query is a relative date keyword and returns a date range.
    Returns (start_date, end_date) tuple or None if it's not a date query.
    """
    today = datetime.now().date()
    query = query.strip().lower()

    if query == "today":
        return today, today
    elif query == "tomorrow":
        tomorrow = today + timedelta(days=1)
        return tomorrow, tomorrow
    elif query == "this week":
        # This week is from last Monday to this coming Sunday
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        return start_of_week, end_of_week
    elif query == "next week":
        # Next week is from next Monday to the following Sunday
        start_of_next_week = today + timedelta(days=(7 - today.weekday()))
        end_of_next_week = start_of_next_week + timedelta(days=6)
        return start_of_next_week, end_of_next_week
    
    return None

# --- API Endpoint ---

@app.post("/query_foreclosure_sheet", response_model=list[Property])
def query_foreclosure_sheet(payload: QueryRequestModel):
    """
    Queries the foreclosure sheet. It handles both specific date phrases
    and general text searches.
    """
    if not worksheet:
        return {"error": "Google Sheet not accessible. Check server logs."}

    query = payload.query.strip().lower()
    data = worksheet.get_all_records()
    results = []

    # Try to process the query as a date range first
    date_range = parse_date_query(query)

    if date_range:
        # --- DATE-BASED SEARCH ---
        start_date, end_date = date_range
        for row in data:
            sale_date_str = row.get("SaleDate")
            if not sale_date_str:
                continue

            try:
                # Assuming date format in sheet is MM/DD/YYYY or M/D/YYYY
                sale_date = datetime.strptime(sale_date_str, "%m/%d/%Y").date()
                if start_date <= sale_date <= end_date:
                    results.append(row)
            except (ValueError, TypeError):
                # Ignore rows where SaleDate is not a valid date
                continue
    else:
        # --- GENERAL KEYWORD SEARCH (Fallback) ---
        for row in data:
            # Create a searchable string from all values in the row
            row_text = " ".join([str(v).strip().lower() for v in row.values()])
            if query in row_text:
                results.append(row)

    # Format results to match the Pydantic model, ensuring all values are strings
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
