from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import gspread
from google.oauth2.service_account import Credentials
from typing import List

app = FastAPI()

# CORS middleware to allow requests from anywhere
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

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scope)
gc = gspread.authorize(creds)
worksheet = gc.open(SHEET_NAME).worksheet(WORKSHEET_NAME)

data = worksheet.get_all_records()

# Request model
class QueryRequestModel(BaseModel):
    query: str

# Response model
class Property(BaseModel):
    PropertyAddress: str
    SaleDate: str
    SaleTime: str
    City: str
    County: str
    ZipCode: str
    Source: str
    DriveTimeToNashville: str
    DriveTimeToMtJuliet: str

@app.post("/query_foreclosure_sheet", response_model=List[Property])
def query_foreclosure_sheet(payload: QueryRequestModel):
    query = payload.query.lower()

    results = []
    for row in data:
        row_text = " ".join([str(v).lower() for v in row.values()])
        if query in row_text:
            results.append({
                "PropertyAddress": row.get("PropertyAddress", ""),
                "SaleDate": row.get("SaleDate", ""),
                "SaleTime": row.get("SaleTime", ""),
                "City": row.get("City", ""),
                "County": row.get("County", ""),
                "ZipCode": row.get("ZipCode", ""),
                "Source": row.get("Source", ""),
                "DriveTimeToNashville": row.get("DriveTimeToNashville", ""),
                "DriveTimeToMtJuliet": row.get("DriveTimeToMtJuliet", ""),
            })

    return results
