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
sheet_name = os.getenv("SHEET_NAME", "milklab-sales")
ws = gc.open(sheet_name).sheet1

# Clear all values
ws.clear()

# Set headers and values
headers = ["timestamp", "menu", "qty", "price", "total"]
rows = [
    headers,
    ["2026-07-21T20:04:58+07:00", "นมหมีฮอกไกโด", 1, 65, 65],
    ["2026-07-21T20:06:38+07:00", "นมหมี", 2, 65, 130],
    ["2026-07-21T20:07:15+07:00", "นมหมี", 2, 65, 130]
]

ws.update("A1", rows)
print("Sheet successfully reset with correct headers and clean data!")
