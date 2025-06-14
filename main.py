from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import gspread
from google.oauth2.service_account import Credentials

app = FastAPI()

# Allow CORS so GPT or other apps can query it
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

# Response model (matching actual column names)
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
    query = payload.query.lower()

    worksheet = gc.open(SHEET_NAME).worksheet(WORKSHEET_NAME)
    data = worksheet.get_all_records()

    results = []
    for row in data:
        row_text = " ".join([str(v).lower() for v in row.values()])
        if query in row_text:
            results.append({
                "PropertyAddress": str(row["PropertyAddress"]) if row.get("PropertyAddress") else "",
                "SaleDate": str(row["SaleDate"]) if row.get("SaleDate") else "",
                "SaleTime": str(row["SaleTime"]) if row.get("SaleTime") else "",
                "City": str(row["City"]) if row.get("City") else "",
                "County": str(row["County"]) if row.get("County") else "",
                "ZipCode": str(row["ZipCode"]) if row.get("ZipCode") else "",
                "Source": str(row["Source"]) if row.get("Source") else "",
            })

    return results
