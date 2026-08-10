"""Create a GitHub Pull Request using the GitHub REST API."""
import json
import os
import sys
from dotenv import load_dotenv
load_dotenv()

import urllib.request

# GitHub API credentials from .env
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
if not GITHUB_TOKEN:
    print("GITHUB_TOKEN not found in .env")
    print("Need to generate one at: https://github.com/settings/tokens")
    sys.exit(1)

owner = "chatmongkhon05"
repo = "milklab-chatmongkol"
url = f"https://api.github.com/repos/{owner}/{repo}/pulls"

data = json.dumps({
    "title": "feat(S2): Sales Logger + Agent Harness",
    "head": "feature/sales-logger",
    "base": "main",
    "body": (
        "## Session 2: Sales Logger + Agent Harness\n\n"
        "### สิ่งที่พัฒนา:\n"
        "- **sales_logger.py**: บันทึกยอดขายลง Google Sheets + ส่งแจ้งเตือน Telegram\n"
        "- **agent_harness.py**: รับคำสั่งภาษาไทย ส่ง Gemini API ตีความ tool call และรัน tool จริง\n"
        "- **.github/workflows/sales-logger.yml**: ตั้ง cron 20:00 ICT ทุกวัน\n"
        "- **reset_sheet.py**: utility สำหรับล้าง/ตั้งหัวตาราง Sheets\n\n"
        "### Self-check:\n"
        "- [x] Sheets append ทำงาน (มี row ใหม่ทุกครั้งที่รัน)\n"
        "- [x] Telegram Bot ส่ง notification ได้\n"
        "- [x] GitHub Actions workflow run ผ่าน (manual trigger)\n"
        "- [x] agent_harness.py ตีความ 3 ตัวอย่างคำสั่งที่ต่างกัน\n"
    )
}).encode("utf-8")

req = urllib.request.Request(
    url,
    data=data,
    headers={
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
    },
    method="POST"
)

try:
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())
        print(f"Pull Request สร้างสำเร็จ!")
        print(f"URL: {result['html_url']}")
        print(f"หมายเลข: #{result['number']}")
except urllib.error.HTTPError as e:
    body = json.loads(e.read())
    print(f"Error: {e.code} - {body.get('message', e.reason)}")
    if "errors" in body:
        for err in body["errors"]:
            print(f"  - {err}")
    sys.exit(1)
