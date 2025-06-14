
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta

app = FastAPI()

# CORS (allow GPT to call the endpoint)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Google Sheets authentication
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
creds = Credentials.from_service_account_file('credentials.json', scopes=SCOPES)
gc = gspread.authorize(creds)
SHEET_NAME = 'Foreclosure Deals'
WORKSHEET_NAME = 'Sheet1'

@app.get("/get_properties")
def get_properties(location: str = Query(...), max_drive_time: int = Query(...)):
    worksheet = gc.open(SHEET_NAME).worksheet(WORKSHEET_NAME)
    rows = worksheet.get_all_records()

    today = datetime.today()
    start_week = today - timedelta(days=today.weekday())
    end_week = start_week + timedelta(days=6)

    results = []
    for row in rows:
        sale_date_str = row.get("SaleDate", "")
        if not sale_date_str:
            continue
        try:
            sale_date = datetime.strptime(sale_date_str.strip(), "%m/%d/%Y")
        except:
            continue

        if not (start_week <= sale_date <= end_week):
            continue

        drive_key = "DriveTimeToMtJuliet" if "juliet" in location.lower() else "DriveTimeToNashville"
        try:
            drive_time = int(str(row.get(drive_key, "")).strip())
        except:
            continue

        if drive_time <= max_drive_time:
            results.append({
                "PropertyAddress": row.get("PropertyAddress"),
                "SaleDate": row.get("SaleDate"),
                "SaleTime": row.get("SaleTime"),
                "City": row.get("City"),
                "County": row.get("County"),
                "ZipCode": row.get("ZipCode"),
                "DriveTime": drive_time,
                "Source": row.get("Source")
            })

    return {"results": results[:10]}
