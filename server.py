from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync
import os, json, queue, threading, time, traceback, re

app = Flask(__name__)

# globals created lazily
p = browser = context = None
lock = threading.Lock()

def ensure_browser():
    """Start browser only once, when first needed."""
    global p, browser, context
    with lock:
        if browser:
            return context
        p = sync_playwright().start()
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                        " AppleWebKit/537.36 (KHTML, like Gecko)"
                        " Chrome/120.0 Safari/537.36")
        )

        cookies_json = os.getenv("COOKIES")
        if cookies_json:
            try:
                cookies = json.loads(cookies_json)
                for c in cookies:
                    c.setdefault("sameSite", "None")
                context.add_cookies(cookies)
                print(f"🍪 Added {len(cookies)} cookies")
            except Exception as e:
                print("⚠️ Cookie load error:", e)
        else:
            print("⚠️ No COOKIES env found.")
        return context


@app.route("/api/hls")
def get_hls():
    url = request.args.get("url")
    if not url:
        return jsonify({"error": "missing ?url="}), 400

    ctx = ensure_browser()
    try:
        page = ctx.new_page()
        stealth_sync(page)
        page.goto(url, wait_until="networkidle", timeout=60000)

        try:
            js = page.evaluate("window.ytInitialPlayerResponse") or {}
        except Exception:
            html = page.content()
            match = re.search(r"ytInitialPlayerResponse\s*=\s*(\{.*?\})\s*;", html)
            js = json.loads(match.group(1)) if match else {}

        page.close()
        streaming = js.get("streamingData", {})
        hls = streaming.get("hlsManifestUrl")
        return jsonify(
            {"hlsManifestUrl": hls, "stealth": True}
            if hls else {"error": "No hlsManifestUrl found", "stealth": True}
        )
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e), "stealth": True})


@app.route("/")
def home():
    return jsonify({
        "usage": "/api/hls?url=<YouTube_URL>",
        "example": "/api/hls?url=https://www.youtube.com/watch?v=5qap5aO4i9A",
        "note": "Lazy-launch Playwright + Stealth (stable on Render)."
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
