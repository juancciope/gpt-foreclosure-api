from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta

app = FastAPI()

# CORS (allows access from GPT and other frontends)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Google Sheets setup
SHEET_NAME = "Foreclosure Deals"
WORKSHEET_NAME = "Sheet1"
CREDENTIALS_FILE = "credentials2.json"

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scope)
gc = gspread.authorize(creds)

# Request model
class QueryRequestModel(BaseModel):
    query: str

# Response model (based on your sheet structure)
class Property(BaseModel):
    PropertyAddress: str
    SaleDate: str
    SaleTime: str
    City: str
    County: str
    ZipCode: str
    Source: str

@app.post("/query_foreclosure_sheet", response_model=List[Property])
def query_foreclosure_sheet(payload: QueryRequestModel):
    query = payload.query.lower()
    today = datetime.today()
    
    # Load sheet data
    worksheet = gc.open(SHEET_NAME).worksheet(WORKSHEET_NAME)
    data = worksheet.get_all_records()

    # Prepare date filters
    next_week = False
    next_monday = next_sunday = None

    if "next week" in query:
        next_week = True
        next_monday = today + timedelta(days=-today.weekday() + 7)
        next_sunday = next_monday + timedelta(days=6)

    results = []
    for row in data:
        try:
            # Normalize all fields
            row_normalized = {k: str(v).strip() for k, v in row.items()}
            row_text = " ".join(v.lower() for v in row_normalized.values())

            # If query says "next week", filter by date
            if next_week:
                sale_date_str = row_normalized.get("SaleDate", "")
                if not sale_date_str:
                    continue
                try:
                    sale_date = datetime.strptime(sale_date_str, "%m/%d/%Y")
                    if next_monday <= sale_date <= next_sunday:
                        results.append(Property(**row_normalized))
                except ValueError:
                    continue
            else:
                if query in row_text:
                    results.append(Property(**row_normalized))

        except Exception as e:
            continue  # silently skip bad rows

    return results
