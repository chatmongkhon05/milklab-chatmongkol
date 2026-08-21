import os
import json
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

dotenv_path = ".env"
load_dotenv(dotenv_path)

creds_raw = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
creds_info = json.loads(creds_raw)
scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
credentials = Credentials.from_service_account_info(creds_info, scopes=scopes)
gc = gspread.authorize(credentials)
sheet_name = os.getenv("SHEET_NAME", "petlab-sales")
try:
    ws = gc.open(sheet_name).sheet1
except gspread.SpreadsheetNotFound:
    print(f"Sheet '{sheet_name}' not found, skipping reset.")
    exit(0)

# Clear all values
ws.clear()

# Set headers and values
headers = ["timestamp", "menu", "qty", "price", "total"]
rows = [
    headers,
    ["2026-08-21T10:00:00+07:00", "อาหารสุนัขเกรดพรีเมียม (โฮลิสติก) 1.5kg", 1, 450, 450],
    ["2026-08-21T10:15:00+07:00", "ทรายแมวภูเขาไฟ 10 ลิตร", 2, 220, 440],
]

ws.update("A1", rows)
print("Sheet successfully reset with correct headers and clean data!")

