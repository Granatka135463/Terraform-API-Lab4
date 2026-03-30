# src/app.py  — Варіант 3: Рейтинг посилань 
import json
import boto3
import os
import uuid
import urllib.request
from datetime import datetime

TABLE_NAME = os.environ.get("TABLE_NAME")
dynamodb   = boto3.resource("dynamodb")
table      = dynamodb.Table(TABLE_NAME)


def check_url_reachable(url: str) -> bool:
    """★ HEAD-запит для перевірки доступності URL."""
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status < 400
    except Exception:
        return False


def handler(event, context):
    try:
        method     = event["requestContext"]["http"]["method"]
        query_params = event.get("queryStringParameters") or {}

        # ── POST /links ──────────────────────────────────────────────────────
        if method == "POST":
            body = json.loads(event.get("body") or "{}")
            url  = body.get("url")
            tags = body.get("tags", [])   # список міток, наприклад ["cloud","aws"]

            if not url:
                return _resp(400, {"error": "Field 'url' is required"})

            # ★ Перевірка доступності
            reachable = check_url_reachable(url)

            item = {
                "id":         str(uuid.uuid4()),
                "url":        url,
                "tags":       tags,
                "reachable":  reachable,
                "created_at": datetime.utcnow().isoformat()
            }
            table.put_item(Item=item)
            return _resp(201, {"message": "Created", "item": item})

        # ── GET /links?tag=cloud ─────────────────────────────────────────────
        elif method == "GET":
            tag = query_params.get("tag")
            response = table.scan()
            items = response.get("Items", [])

            if tag:
                items = [i for i in items if tag in i.get("tags", [])]

            return _resp(200, {"items": items, "count": len(items)})

        return _resp(405, {"error": "Method Not Allowed"})

    except Exception as e:
        print(f"[ERROR] {str(e)}")
        return _resp(500, {"error": "Internal Server Error"})


def _resp(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers":    {"Content-Type": "application/json"},
        "body":       json.dumps(body, ensure_ascii=False)
    }