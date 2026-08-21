"""EasyMart Caption Generator — 3 styles (Friendly / Minimal / Promotion).

Usage:
    python caption.py
or:
    python caption.py --menu "ข้าวสารหอมมะลิ 100% 5kg"
"""

import argparse
import os
import sys
import time
from dotenv import load_dotenv
from google import genai


COMBINED_PROMPT = """\
คุณคือ social media manager และ copywriter ของร้าน EasyMart ร้านขายของชำออนไลน์

จงเขียนแคปชั่นภาษาไทยสำหรับสินค้า: {menu} ทั้งหมด 3 สไตล์ ดังนี้:

[Friendly]
- สไตล์เป็นกันเอง อบอุ่น ใส่ emoji สดใส
- ความยาว 2-3 ประโยค ปิดด้วย call-to-action
- ห้ามใช้ em dash

[Minimal]
- สไตล์ minimalist เรียบหรู ตรงประเด็น ไม่ใช้ emoji
- ความยาว 2 ประโยค ปิดด้วย call-to-action
- ห้ามใช้ em dash

[Promotion]
- สไตล์การตลาดเน้นโปรโมชั่นสุดคุ้ม ราคาถูกใจพ่อบ้านแม่บ้าน
- ความยาว 2-3 ประโยค ปิดด้วย call-to-action
- ห้ามใช้ em dash

ตอบเป็นข้อความแยกแต่ละสไตล์ชัดเจนดังนี้:
---Friendly---
<แคปชั่น>
---Minimal---
<แคปชั่น>
---Promotion---
<แคปชั่น>
"""


def generate_all_captions(menu: str, api_key: str) -> dict[str, str]:
    client = genai.Client(api_key=api_key)
    prompt = COMBINED_PROMPT.format(menu=menu)
    
    # รายชื่อโมเดลเรียงลำดับจากหลักไปสำรอง
    models_to_try = [
        os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        "gemini-3.5-flash-lite",
        "gemini-1.5-flash",
    ]
    models_to_try = list(dict.fromkeys(models_to_try))

    response_text = ""
    last_err = None

    for model in models_to_try:
        try:
            resp = client.models.generate_content(
                model=model,
                contents=prompt,
            )
            if resp and resp.text:
                response_text = resp.text
                break
        except Exception as e:
            last_err = e
            err_str = str(e)
            # ถ้าเจอ 429 (Rate Limit) หรือ 404 (Model Not Found) ให้ข้ามไปลองรุ่นถัดไป
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "404" in err_str or "NOT_FOUND" in err_str:
                time.sleep(1)
                continue
            raise

    if not response_text:
        if last_err:
            raise last_err
        raise RuntimeError("ไม่สามารถสร้างแคปชั่นได้")

    # Parse response
    results = {}
    for style in ["Friendly", "Minimal", "Promotion"]:
        tag = f"---{style}---"
        if tag in response_text:
            part = response_text.split(tag)[1]
            for next_style in ["Friendly", "Minimal", "Promotion"]:
                next_tag = f"---{next_style}---"
                if next_style != style and next_tag in part:
                    part = part.split(next_tag)[0]
            results[style] = part.strip()
        else:
            results[style] = response_text.strip()

    return results


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

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

    try:
        captions = generate_all_captions(args.menu, api_key)
        for style, caption in captions.items():
            print(f"\n✨ [{style}]")
            print(caption)
            print()
    except Exception as exc:
        err_str = str(exc)
        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
            print(f"\n[WARN] โควตา Google Gemini API รายวัน/รายนาทีชั่วคราวเต็ม (429 Rate Limit)")
            print("กรุณารอประมาณ 30-60 วินาที แล้วลองใหม่อีกครั้งครับ")
            return 1
        print(f"\n[ERROR] เกิดข้อผิดพลาดจาก Gemini API: {exc}", file=sys.stderr)
        return 1

    print("=" * 60)
    print("✅ Done!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
