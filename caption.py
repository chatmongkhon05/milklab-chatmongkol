"""EasyMart Caption Generator — 3 styles (Friendly / Minimal / Promotion).

Usage:
    python caption.py
or:
    python caption.py --menu "ข้าวสารหอมมะลิ 100% 5kg"
"""

import argparse
import os
import sys
from dotenv import load_dotenv
from google import genai


STYLES = {
    "Friendly": (
        "คุณคือ social media manager ของร้าน EasyMart ร้านขายของชำออนไลน์ สไตล์เป็นกันเอง อบอุ่น ใส่ emoji สดใส "
        "เขียนแคปชั่นภาษาไทย 2-3 ประโยคโปรโมตสินค้า: {menu} ปิดด้วย call-to-action ห้ามใช้ em dash"
    ),
    "Minimal": (
        "คุณคือ copywriter ร้าน EasyMart สไตล์ minimalist เรียบหรู ตรงประเด็น ไม่ใช้ emoji "
        "เขียนแคปชั่นภาษาไทย 2 ประโยคโปรโมตสินค้า: {menu} ปิดด้วย call-to-action ห้ามใช้ em dash"
    ),
    "Promotion": (
        "คุณคือทีมการตลาดร้าน EasyMart เน้นโปรโมชั่นสุดคุ้ม ราคาถูกใจพ่อบ้านแม่บ้าน สลับใช้คำฮิต "
        "เขียนแคปชั่น 2-3 ประโยคโปรโมตสินค้า: {menu} ปิดด้วย call-to-action ห้ามใช้ em dash"
    ),
}


def generate_caption(menu: str, style: str, api_key: str) -> str:
    client = genai.Client(api_key=api_key)
    prompt = STYLES[style].format(menu=menu)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )
    return (response.text or "").strip()


def main() -> int:
    load_dotenv()
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("[ERROR] GOOGLE_API_KEY not set", file=sys.stderr)
        return 1

    parser = argparse.ArgumentParser(description="EasyMart Caption Generator (3 styles)")
    parser.add_argument("--menu", default="ข้าวสารหอมมะลิ 100% 5kg", help="ชื่อสินค้า (default: ข้าวสารหอมมะลิ 100% 5kg)")
    args = parser.parse_args()

    print(f"\n🛒 EasyMart Caption Generator — สินค้า: {args.menu}\n")
    print("=" * 60)

    for style in STYLES:
        print(f"\n✨ [{style}]")
        caption = generate_caption(args.menu, style, api_key)
        print(caption)
        print()

    print("=" * 60)
    print("✅ Done!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
