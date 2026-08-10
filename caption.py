"""MilkLab Caption Generator — 3 styles (Cute / Minimal / Gen-Z).

Usage:
    python caption.py
or:
    python caption.py --menu "นมหมีฮอกไกโด"
"""

import argparse
import os
import sys
from dotenv import load_dotenv
from google import genai


STYLES = {
    "Cute": (
        "คุณคือ social media manager ของร้าน MilkLab° ร้านนมสดกลางคืน สไตล์น่ารัก ใส่ emoji เยอะ "
        "เขียนแคปชั่นภาษาไทย 2-3 ประโยคโปรโมตเมนู: {menu} ปิดด้วย call-to-action ห้ามใช้ em dash"
    ),
    "Minimal": (
        "คุณคือ copywriter ร้าน MilkLab° สไตล์ minimalist เรียบง่าย ประโยคสั้น ไม่ใช้ emoji "
        "เขียนแคปชั่นภาษาไทย 2 ประโยคโปรโมตเมนู: {menu} ปิดด้วย call-to-action ห้ามใช้ em dash"
    ),
    "Gen-Z": (
        "คุณคือ social media manager ร้าน MilkLab° สไตล์ Gen-Z เท่ cool สลับภาษาไทย-อังกฤษ "
        "ใช้ slang วัยรุ่น เขียนแคปชั่น 2-3 ประโยคโปรโมตเมนู: {menu} ปิดด้วย call-to-action ห้ามใช้ em dash"
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

    parser = argparse.ArgumentParser(description="MilkLab Caption Generator (3 styles)")
    parser.add_argument("--menu", default="นมหมีฮอกไกโด", help="ชื่อเมนู (default: นมหมีฮอกไกโด)")
    args = parser.parse_args()

    print(f"\n🥛 MilkLab° Caption Generator — เมนู: {args.menu}\n")
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
