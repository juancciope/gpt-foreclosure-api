from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import gspread
from google.oauth2.service_account import Credentials

# Initialize app
app = FastAPI()

# CORS (for external requests, including GPT)
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

# Authenticate
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scope)
gc = gspread.authorize(creds)

# Request model
class QueryRequestModel(BaseModel):
    query: str

# Endpoint: POST /query_foreclosure_sheet
@app.post("/query_foreclosure_sheet")
def query_foreclosure_sheet(payload: QueryRequestModel):
    query = payload.query.lower()
    worksheet = gc.open(SHEET_NAME).worksheet(WORKSHEET_NAME)
    data = worksheet.get_all_records()

    results = []
    for row in data:
        row_text = " ".join([str(v).lower() for v in row.values()])
        if query in row_text:
            results.append(row)  # Return full row

    return results

@app.get("/ping")
def ping():
    return {"status": "alive"}
