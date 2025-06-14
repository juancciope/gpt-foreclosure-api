from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials

app = FastAPI()

# CORS
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
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file("credentials2.json", scopes=scope)
gc = gspread.authorize(creds)

# Pydantic Models
class QueryRequestModel(BaseModel):
    query: str

class Property(BaseModel):
    address: str
    city: str
    state: str
    zip_code: str
    price: str
    sale_date: str

@app.post("/query_foreclosure_sheet")
def query_foreclosure_sheet(payload: QueryRequestModel):
    query = payload.query.lower()
    worksheet = gc.open(SHEET_NAME).worksheet(WORKSHEET_NAME)
    data = worksheet.get_all_records()

    today = datetime.now().date()
    next_week_start = today + timedelta(days=1)
    next_week_end = today + timedelta(days=7)

    results = []

    for row in data:
        row_text = " ".join([str(v).lower() for v in row.values()])

        # Fuzzy match: catch any query match
        if query in row_text:
            results.append(format_row(row))
            continue

        # Smart match: look for "next week"
        if "next week" in query or "coming week" in query:
            try:
                sale_date = parse_date(row.get("Sale Date", ""))
                if next_week_start <= sale_date <= next_week_end:
                    results.append(format_row(row))
                    continue
            except:
                pass

        # Smart match: if user mentions date range
        if "june" in query or "2025" in query:
            try:
                sale_date = parse_date(row.get("Sale Date", ""))
                if "june 16" in query and "june 20" in query:
                    if datetime(2025, 6, 16).date() <= sale_date <= datetime(2025, 6, 20).date():
                        results.append(format_row(row))
                        continue
            except:
                pass

        # Smart match: city
        if "nashville" in query and row.get("City", "").lower() == "nashville":
            results.append(format_row(row))
            continue

    return results


def parse_date(date_str):
    return datetime.strptime(date_str.strip(), "%m/%d/%Y").date()

def format_row(row):
    return {
        "address": row.get("Address", ""),
        "city": row.get("City", ""),
        "state": row.get("State", ""),
        "zip_code": row.get("Zip Code", ""),
        "price": row.get("Price", ""),
        "sale_date": row.get("Sale Date", ""),
    }
