"""EasyMart Caption Generator (S1).

Usage:
    python caption_generator.py

Reads GOOGLE_API_KEY from env. Generates a Thai caption for an EasyMart product.
"""

import os
import sys

from dotenv import load_dotenv
from google import genai


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
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=PROMPT_TEMPLATE.format(menu=menu),
    )
    return response.text or ""


def main() -> int:
    load_dotenv()
    menu = input("สินค้าที่จะโปรโมต: ").strip()
    if not menu:
        print("กรุณาใส่ชื่อสินค้า")
        return 1
    caption = generate_caption(menu)
    print()
    print(caption)
    return 0


if __name__ == "__main__":
    sys.exit(main())
