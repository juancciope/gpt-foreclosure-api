from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import gspread
from google.oauth2.service_account import Credentials
import re

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SHEET_NAME = "Foreclosure Deals"
WORKSHEET_NAME = "Sheet1"
CREDENTIALS_FILE = "credentials2.json"

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scope)
gc = gspread.authorize(creds)

class QueryRequestModel(BaseModel):
    query: str

@app.post("/query_foreclosure_sheet")
def query_foreclosure_sheet(payload: QueryRequestModel):
    query = payload.query.lower().strip()
    worksheet = gc.open(SHEET_NAME).worksheet(WORKSHEET_NAME)
    data = worksheet.get_all_records()

    results = []
    for row in data:
        # Normalize and join all row values for fuzzy matching
        row_text = " ".join([str(v).lower().strip() for v in row.values() if v])

        if query in row_text or query == "":
            result = {
                "address": row.get("Address", "Unknown"),
                "city": row.get("City", "Unknown"),
                "state": row.get("State", ""),
                "zip_code": str(row.get("Zip Code", "")),
                "price": row.get("Price", "N/A"),
                "sale_date": row.get("Sale Date", "N/A")
            }
            results.append(result)

    if not results:
        return [{"address": "No matches found", "city": "", "state": "", "zip_code": "", "price": "", "sale_date": ""}]

    return results
