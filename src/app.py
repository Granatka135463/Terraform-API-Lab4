import json
import boto3
import os
import uuid
import urllib.request
from datetime import datetime

TABLE_NAME  = os.environ.get("TABLE_NAME")
AWS_REGION  = os.environ.get("AWS_REGION", "eu-central-1")

dynamodb   = boto3.resource("dynamodb", region_name=AWS_REGION)
table      = dynamodb.Table(TABLE_NAME)
comprehend = boto3.client("comprehend", region_name=AWS_REGION)


def check_url_reachable(url: str) -> bool:
    """HEAD-запит для перевірки доступності URL."""
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status < 400
    except Exception:
        return False


def detect_language(text: str) -> dict:
    """
    Викликає Comprehend detect_dominant_language().
    Повертає словник з полями:
      language_code  — код мови (напр. "uk", "en", "de")
      confidence     — впевненість моделі (0.0–1.0)
      all_languages  — повний список мов з впевненістю
    При будь-якій помилці повертає graceful fallback замість падіння.
    """
    try:
        response = comprehend.detect_dominant_language(Text=text[:4900])
        languages = response.get("Languages", [])
        if not languages:
            return {"language_code": "unknown", "confidence": 0.0, "all_languages": []}

        languages_sorted = sorted(languages, key=lambda x: x["Score"], reverse=True)
        dominant = languages_sorted[0]

        return {
            "language_code": dominant["LanguageCode"],
            "confidence":    round(dominant["Score"], 4),
            "all_languages": [
                {"code": l["LanguageCode"], "score": round(l["Score"], 4)}
                for l in languages_sorted
            ]
        }
    except comprehend.exceptions.TextSizeLimitExceededException:
        print("[WARN] Text too large for Comprehend, skipping language detection")
        return {"language_code": "unknown", "confidence": 0.0, "all_languages": [], "error": "text_too_large"}
    except Exception as e:
        print(f"[WARN] Comprehend error: {str(e)}")
        return {"language_code": "unknown", "confidence": 0.0, "all_languages": [], "error": str(e)}



def handler(event, context):
    try:
        method       = event["requestContext"]["http"]["method"]
        path         = event["requestContext"]["http"]["path"]
        query_params = event.get("queryStringParameters") or {}
        path_params  = event.get("pathParameters") or {}

        # POST /links
        if method == "POST" and path == "/links":
            body = json.loads(event.get("body") or "{}")
            url         = body.get("url")
            description = body.get("description", "")  
            tags        = body.get("tags", [])

            if not url:
                return _resp(400, {"error": "Field 'url' is required"})

            reachable = check_url_reachable(url)

            language_info = {}
            if description:
                language_info = detect_language(description)

            item = {
                "id":           str(uuid.uuid4()),
                "url":          url,
                "description":  description,
                "tags":         tags,
                "reachable":    reachable,
                "created_at":   datetime.utcnow().isoformat(),
                **( {"language_code":  language_info["language_code"],
                     "lang_confidence": str(language_info["confidence"]),
                     "lang_all":        json.dumps(language_info.get("all_languages", []))}
                    if language_info else {} )
            }
            table.put_item(Item=item)
            return _resp(201, {"message": "Created", "item": item})

        # GET /links?tag=cloud 
        elif method == "GET" and path == "/links":
            tag      = query_params.get("tag")
            response = table.scan()
            items    = response.get("Items", [])

            if tag:
                items = [i for i in items if tag in i.get("tags", [])]

            return _resp(200, {"items": items, "count": len(items)})

        # GET /links/{id}/language 
        elif method == "GET" and "/language" in path:
            link_id = path_params.get("id")
            if not link_id:
                return _resp(400, {"error": "Missing path parameter 'id'"})

            # Отримуємо запис з DynamoDB
            result = table.get_item(Key={"id": link_id})
            item   = result.get("Item")
            if not item:
                return _resp(404, {"error": f"Link '{link_id}' not found"})

            description = item.get("description", "")
            if not description:
                return _resp(422, {"error": "This link has no description to analyze"})

            language_info = detect_language(description)

            table.update_item(
                Key={"id": link_id},
                UpdateExpression=(
                    "SET language_code = :lc, "
                    "lang_confidence = :cf, "
                    "lang_all = :la, "
                    "lang_analyzed_at = :ts"
                ),
                ExpressionAttributeValues={
                    ":lc": language_info["language_code"],
                    ":cf": str(language_info["confidence"]),
                    ":la": json.dumps(language_info.get("all_languages", [])),
                    ":ts": datetime.utcnow().isoformat()
                }
            )

            return _resp(200, {
                "id":           link_id,
                "url":          item.get("url"),
                "description":  description,
                "language":     language_info,
                "analyzed_at":  datetime.utcnow().isoformat()
            })

        return _resp(405, {"error": "Method Not Allowed"})

    except Exception as e:
        print(f"[ERROR] {str(e)}")
        return _resp(500, {"error": "Internal Server Error"})


def _resp(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers":    {"Content-Type": "application/json"},
        "body":       json.dumps(body, ensure_ascii=False, default=str)
    }