"""MilkLab Sales Logger (S2).

Usage:
    python sales_logger.py --menu "นมหมีฮอกไกโด" --qty 2 --price 65

Reads GOOGLE_SHEETS_CREDENTIALS and TELEGRAM_BOT_TOKEN (or LINE_CHANNEL_TOKEN) from env.
Appends row [timestamp, menu, qty, price, total] to a Google Sheet,
then sends a notification via Telegram or LINE bot.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv


def append_to_sheet(menu: str, qty: int, price: float) -> dict:
    """ใช้ gspread เปิด Sheet ของตัวเอง แล้ว append_row ด้วย [timestamp, menu, qty, price, total]

    Returns dict {timestamp, menu, qty, price, total} ที่ append แล้ว
    Raises RuntimeError ถ้า credentials ไม่มี หรือ Sheet ไม่ accessible
    """
    import gspread
    from google.oauth2.service_account import Credentials

    creds_raw = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
    if not creds_raw:
        raise RuntimeError("GOOGLE_SHEETS_CREDENTIALS ไม่ได้ตั้งค่าใน .env")

    # Parse JSON credentials
    try:
        creds_info = json.loads(creds_raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"GOOGLE_SHEETS_CREDENTIALS ไม่ใช่ JSON ที่ถูกต้อง: {e}")

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials = Credentials.from_service_account_info(creds_info, scopes=scopes)
    gc = gspread.authorize(credentials)

    # เปิด spreadsheet — ใช้ชื่อ milklab-sales หรือ env var SHEET_NAME
    sheet_name = os.getenv("SHEET_NAME", "milklab-sales")
    try:
        sh = gc.open(sheet_name)
    except gspread.SpreadsheetNotFound:
        raise RuntimeError(
            f"ไม่พบ Google Sheet ชื่อ '{sheet_name}' — ตรวจสอบว่า share sheet ให้ service account email แล้ว"
        )

    ws = sh.sheet1

    # สร้าง header ถ้า sheet ว่าง
    if ws.row_count == 0 or not ws.get_all_values():
        ws.append_row(["timestamp", "menu", "qty", "price", "total"])

    # คำนวณ timestamp และ total
    tz_bkk = timezone(timedelta(hours=7))
    timestamp = datetime.now(tz=tz_bkk).isoformat(timespec="seconds")
    total = qty * price

    ws.append_row([timestamp, menu, qty, price, total])

    return {"timestamp": timestamp, "menu": menu, "qty": qty, "price": price, "total": total}


def send_notification(message: str) -> str:
    """ส่ง message ไปยัง Telegram bot (ใช้ TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID)
    หรือ LINE bot (ใช้ LINE_CHANNEL_TOKEN) เลือกตัวใดตัวหนึ่ง

    Returns: provider name ที่ใช้ ("telegram" หรือ "line")
    Raises RuntimeError ถ้า no credentials
    """
    import requests

    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
    line_token = os.getenv("LINE_CHANNEL_TOKEN")

    if telegram_token and telegram_chat_id:
        url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
        resp = requests.post(url, json={"chat_id": telegram_chat_id, "text": message}, timeout=10)
        if not resp.ok:
            raise RuntimeError(f"Telegram ส่งไม่สำเร็จ: {resp.status_code} {resp.text}")
        return "telegram"

    elif line_token:
        url = "https://api.line.me/v2/bot/message/broadcast"
        headers = {
            "Authorization": f"Bearer {line_token}",
            "Content-Type": "application/json",
        }
        payload = {"messages": [{"type": "text", "text": message}]}
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        if not resp.ok:
            raise RuntimeError(f"LINE ส่งไม่สำเร็จ: {resp.status_code} {resp.text}")
        return "line"

    else:
        raise RuntimeError("ไม่พบ TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID หรือ LINE_CHANNEL_TOKEN ใน .env")


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="MilkLab Sales Logger")
    parser.add_argument("--menu", required=True, help="ชื่อเมนู")
    parser.add_argument("--qty", type=int, required=True, help="จำนวนขวด")
    parser.add_argument("--price", type=float, required=True, help="ราคาต่อขวด")
    args = parser.parse_args()

    try:
        row = append_to_sheet(args.menu, args.qty, args.price)
        total = row["total"]
    except Exception as exc:
        print(f"[ERROR] บันทึก Sheet ล้มเหลว: {exc}", file=sys.stderr)
        print("[HINT] ตรวจ GOOGLE_SHEETS_CREDENTIALS และ share Sheet กับ service account email", file=sys.stderr)
        return 1

    try:
        provider = send_notification(f"บันทึก {args.menu} x{args.qty} = {total} บาท")
    except Exception as exc:
        print(f"[WARN] บันทึก Sheet สำเร็จแต่ส่งแจ้งเตือนล้มเหลว: {exc}", file=sys.stderr)
        return 0

    print(f"[OK] บันทึกและแจ้งเตือนผ่าน {provider} เรียบร้อย ยอด {total} บาท")
    return 0


if __name__ == "__main__":
    sys.exit(main())
