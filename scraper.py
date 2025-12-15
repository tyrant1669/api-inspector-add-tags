
from playwright.sync_api import sync_playwright
import json

def fetch_webpage(url, wait_ms: int = 5000):
  
    api_calls = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        def handle_response(response):
            try:
                content_type = (response.headers.get("content-type") or "").lower()
                if "application/json" in content_type or response.url.lower().endswith(".json"):

                    text = ""
                    try:
                        text = response.text()
                    except Exception:
                        text = ""

                    try:
                        data = json.loads(text)
                    except Exception:
                        data = None

                    api_calls.append({
                        "url": response.url,
                        "status": response.status,
                        "method": response.request.method,
                        "data": data
                    })
            except Exception:
                pass

        page.on("response", handle_response)

        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(wait_ms)
        except Exception:
            pass

        browser.close()

  
    seen = set()
    filtered = []
    for item in api_calls:
        if item["url"] not in seen:
            seen.add(item["url"])
            filtered.append(item)

    return filtered
