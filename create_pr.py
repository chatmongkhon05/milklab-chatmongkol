"""Create a GitHub Pull Request using the GitHub REST API for Session 4 (Pivot)."""
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

pivot_body = ""
if os.path.exists("PIVOT.md"):
    with open("PIVOT.md", "r", encoding="utf-8") as f:
        pivot_body = f.read()

data = json.dumps({
    "title": "Pivot to PetLab° (Pet Shop Domain)",
    "head": "pivot",
    "base": "main",
    "body": pivot_body or "Pivot to PetLab° domain for Session 4",
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
        print("Pull Request สร้างสำเร็จ!")
        print(f"URL: {result['html_url']}")
        print(f"หมายเลข: #{result['number']}")
except urllib.error.HTTPError as e:
    body = json.loads(e.read())
    print(f"Error: {e.code} - {body.get('message', e.reason)}")
    if "errors" in body:
        for err in body["errors"]:
            print(f"  - {err}")
    sys.exit(1)

