"""MilkLab Agent Harness (S2).

Usage:
    python agent_harness.py --cmd "บันทึกขายนมหมี 2 ขวด ขวดละ 65"

รับคำสั่งภาษาไทย ส่งให้ Gemini พร้อม tool schema parse response เป็น tool call
เรียก tool จริง print trace log
"""

import argparse
import json
import os
import sys

from dotenv import load_dotenv
from google import genai
from google.genai import types


TOOL_SCHEMA = [
    {
        "name": "log_sale",
        "description": "บันทึกการขายลง Google Sheets และส่ง notification",
        "parameters": {
            "type": "object",
            "properties": {
                "menu": {"type": "string", "description": "ชื่อเมนู"},
                "qty": {"type": "integer", "description": "จำนวนที่ขาย"},
                "price": {"type": "number", "description": "ราคาต่อหน่วย"},
            },
            "required": ["menu", "qty", "price"],
        },
    },
    {
        "name": "query_sales",
        "description": "ดูยอดขายของวันที่ระบุ",
        "parameters": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "วันที่ format YYYY-MM-DD"},
            },
            "required": ["date"],
        },
    },
    {
        "name": "send_alert",
        "description": "ส่ง message แจ้งเตือนผ่าน Bot",
        "parameters": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
            },
            "required": ["message"],
        },
    },
]


def parse_command(cmd: str, api_key: str | None = None) -> dict:
    """TODO 1: ส่ง cmd ไป Gemini พร้อม TOOL_SCHEMA ขอให้ตอบเป็น JSON {tool, args}

    Returns dict {"tool": <name>, "args": <dict>}
    Raises RuntimeError ถ้า parse ไม่ได้
    """
    api_key = api_key or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY ไม่ได้ตั้งค่าใน .env")

    client = genai.Client(api_key=api_key)

    # แปลง TOOL_SCHEMA เป็น Gemini FunctionDeclaration format
    tools = [
        types.Tool(
            function_declarations=[
                types.FunctionDeclaration(**schema) for schema in TOOL_SCHEMA
            ]
        )
    ]

    system_prompt = (
        "คุณเป็น AI assistant สำหรับร้านนม MilkLab "
        "รับคำสั่งภาษาไทยจากพนักงาน แล้วเรียก tool ที่เหมาะสม "
        "ถ้าคำสั่งไม่ชัดเจนให้เดาจากบริบทให้ดีที่สุด"
    )

    model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-lite")
    response = client.models.generate_content(
        model=model_name,
        contents=cmd,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            tools=tools,
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode="ANY"  # บังคับให้ต้องเรียก tool เสมอ
                )
            ),
        ),
    )

    # Parse function call จาก response
    for part in response.candidates[0].content.parts:
        if part.function_call:
            fc = part.function_call
            return {"tool": fc.name, "args": dict(fc.args)}

    # Fallback: ลอง parse JSON จาก text response
    text = response.text if hasattr(response, "text") else ""
    try:
        data = json.loads(text)
        if "tool" in data and "args" in data:
            return data
    except (json.JSONDecodeError, AttributeError):
        pass

    raise RuntimeError(f"Gemini ไม่คืน tool call — response: {response}")


def dispatch_tool(tool_call: dict) -> str:
    """TODO 2: เรียก tool ตาม tool_call["tool"] ด้วย args จริง

    Returns: ข้อความสรุปผลที่ tool คืน
    """
    from sales_logger import append_to_sheet, send_notification

    name = tool_call["tool"]
    args = tool_call["args"]

    if name == "log_sale":
        menu = args["menu"]
        qty = int(args["qty"])
        price = float(args["price"])
        row = append_to_sheet(menu, qty, price)
        total = row["total"]
        ts = row["timestamp"]
        # ส่ง notification ด้วย
        try:
            send_notification(f"บันทึก {menu} x{qty} = {total} บาท")
        except Exception:
            pass  # notification ล้มเหลวไม่หยุดโปรแกรม
        return f"OK: row appended at {ts}"

    elif name == "query_sales":
        date = args["date"]
        import gspread
        from google.oauth2.service_account import Credentials
        import json as _json
        import os as _os

        creds_raw = _os.getenv("GOOGLE_SHEETS_CREDENTIALS")
        if not creds_raw:
            return "ERROR: GOOGLE_SHEETS_CREDENTIALS ไม่ได้ตั้งค่า"
        creds_info = _json.loads(creds_raw)
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        credentials = Credentials.from_service_account_info(creds_info, scopes=scopes)
        gc = gspread.authorize(credentials)
        sheet_name = _os.getenv("SHEET_NAME", "milklab-sales")
        try:
            ws = gc.open(sheet_name).sheet1
        except gspread.SpreadsheetNotFound:
            return f"ERROR: ไม่พบ Sheet '{sheet_name}'"

        rows = ws.get_all_records()
        day_rows = [r for r in rows if str(r.get("timestamp", "")).startswith(date)]
        if not day_rows:
            return f"ไม่มีข้อมูลวันที่ {date}"
        total = sum(float(r.get("total", 0)) for r in day_rows)
        return f"ยอดขายวันที่ {date}: {len(day_rows)} รายการ รวม {total:.0f} บาท"

    elif name == "send_alert":
        message = args["message"]
        provider = send_notification(message)
        return f"OK: ส่งแจ้งเตือนผ่าน {provider} แล้ว"

    else:
        return f"ERROR: ไม่รู้จัก tool '{name}'"


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--cmd", required=True, help="คำสั่งภาษาไทย")
    args = parser.parse_args()

    print(f"[USER] {args.cmd}")

    # TODO 3: เรียก parse_command then dispatch_tool then print trace ตาม format ใน session-2.md
    try:
        tool_call = parse_command(args.cmd)
    except Exception as exc:
        print(f"[ERROR] parse_command ล้มเหลว: {exc}", file=sys.stderr)
        return 1

    print(f"[LLM]  tool={tool_call['tool']} args={tool_call['args']}")

    try:
        result = dispatch_tool(tool_call)
    except Exception as exc:
        print(f"[ERROR] dispatch_tool ล้มเหลว: {exc}", file=sys.stderr)
        return 1

    print(f"[TOOL] {tool_call['tool']} {result}")
    print(f"[USER] <- {result}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
