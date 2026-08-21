"""EasyMart Caption Generator (S1).

Usage:
    python caption_generator.py

Reads GOOGLE_API_KEY from env. Generates a Thai caption for an EasyMart product.
"""

import os
import sys
import time

from dotenv import load_dotenv
from google import genai
from google.genai.errors import APIError


PROMPT_TEMPLATE = """\
คุณคือ social media manager ของร้าน EasyMart ร้านขายของชำมินิมาร์ทชุมชนออนไลน์

จงเขียนแคปชั่นภาษาไทย 2 ถึง 3 ประโยคโปรโมตสินค้า: {menu}

เงื่อนไข:
- โทนเป็นกันเอง อบอุ่น คุ้มค่า น่าซื้อ ใส่ emoji ได้ (เช่น 🛒, 📦, 🥤, 🍚)
- ต้องมี call-to-action ปิดท้าย เช่น สั่งเลยที่ EasyMart หรือ ทักแชตเพื่อสั่งซื้อ
- ห้ามใช้ em dash
"""


def generate_caption(menu: str, api_key: str | None = None) -> str:
    """Generate a Thai caption for the given grocery store product item."""
    key = api_key or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("GOOGLE_API_KEY not set in env or argument")
    client = genai.Client(api_key=key)
    
    models_to_try = [
        os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        "gemini-1.5-flash",
        "gemini-1.5-flash-8b",
    ]
    models_to_try = list(dict.fromkeys(models_to_try))

    last_err = None
    for model in models_to_try:
        try:
            response = client.models.generate_content(
                model=model,
                contents=PROMPT_TEMPLATE.format(menu=menu),
            )
            if response.text:
                return response.text.strip()
        except APIError as e:
            last_err = e
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                time.sleep(2)
                continue
            if "404" in str(e):
                continue
            raise

    if last_err:
        raise last_err
    return ""


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    load_dotenv()
    menu = input("สินค้าที่จะโปรโมต: ").strip()
    if not menu:
        print("กรุณาใส่ชื่อสินค้า")
        return 1
    try:
        caption = generate_caption(menu)
        print()
        print(caption)
        return 0
    except APIError as exc:
        if "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc):
            print("\n[WARN] โควตา Google Gemini API รายวัน/รายนาทีชั่วคราวเต็ม (429 Rate Limit)")
            print("กรุณารอประมาณ 30-60 วินาที แล้วลองใหม่อีกครั้งครับ")
            return 1
        print(f"\n[ERROR] เกิดข้อผิดพลาดจาก Gemini API: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
