from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import gspread
from google.oauth2.service_account import Credentials

app = FastAPI()

# CORS setup
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

# Input model
class QueryRequestModel(BaseModel):
    query: str

# Output model
class Property(BaseModel):
    PropertyAddress: str
    SaleDate: str
    SaleTime: str
    City: str
    County: str
    ZipCode: str
    Source: str

@app.post("/query_foreclosure_sheet", response_model=list[Property])
def query_foreclosure_sheet(payload: QueryRequestModel):
    query = payload.query.strip().lower()
    
    worksheet = gc.open(SHEET_NAME).worksheet(WORKSHEET_NAME)
    data = worksheet.get_all_records()

    results = []
    for row in data:
        row_text = " ".join([str(v).strip().lower() for v in row.values()])
        if query in row_text:
            results.append({
                "PropertyAddress": str(row.get("PropertyAddress", "")),
                "SaleDate": str(row.get("SaleDate", "")),
                "SaleTime": str(row.get("SaleTime", "")),
                "City": str(row.get("City", "")),
                "County": str(row.get("County", "")),
                "ZipCode": str(row.get("ZipCode", "")),
                "Source": str(row.get("Source", "")),
            })

    return results
