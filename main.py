from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import gspread
from google.oauth2.service_account import Credentials

app = FastAPI()

# CORS (so GPT can call it)
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
CREDENTIALS_FILE = "credentials2.json"  # Update if renamed

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file("credentials2.json", scopes=scope)
gc = gspread.authorize(creds)

# Request model
class QueryRequestModel(BaseModel):
    query: str

# Response model
class Property(BaseModel):
    address: str
    city: str
    state: str
    zip_code: str
    price: str

@app.post("/query_foreclosure_sheet")
def query_foreclosure_sheet(payload: QueryRequestModel):
    query = payload.query.lower()
    
    # Load the sheet
    worksheet = gc.open(SHEET_NAME).worksheet(WORKSHEET_NAME)
    data = worksheet.get_all_records()

    results = []
    for row in data:
        row_text = " ".join([str(v).lower() for v in row.values()])
        if query in row_text:
            results.append({
                "address": row.get("Address", ""),
                "city": row.get("City", ""),
                "state": row.get("State", ""),
                "zip_code": row.get("Zip Code", ""),
                "price": row.get("Price", ""),
            })

    return results  # Always return a list, even if empty
