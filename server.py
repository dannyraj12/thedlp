# pip install flask playwright playwright-stealth
# playwright install chromium

from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth  # ✅ latest API import
import os, json, threading, queue, time, traceback, re

app = Flask(__name__)

job_queue = queue.Queue()
result_dict = {}

def worker():
    """Background worker that holds a persistent Playwright browser."""
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--disable-software-rasterizer",
                    "--disable-background-timer-throttling",
                    "--disable-renderer-backgrounding",
                    "--window-size=1280,720",
                ],
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/120.0 Safari/537.36",
                viewport={"width": 1280, "height": 720}
            )
            print("✅ Chromium launched successfully.")
        except Exception as e:
            print("❌ Failed to launch Chromium:", e)
            return

        # 🍪 Load cookies from environment
        cookies_json = os.getenv("COOKIES")
        if cookies_json:
            try:
                cookies = json.loads(cookies_json)
                for c in cookies:
                    c.setdefault("sameSite", "None")
                context.add_cookies(cookies)
                print(f"🍪 Added {len(cookies)} cookies from environment.")
            except Exception as e:
                print(f"⚠️ Failed to parse/add cookies: {e}")
        else:
            print("⚠️ No COOKIES environment variable found.")

        print("✅ Playwright worker started (browser persistent).")

        while True:
            job = job_queue.get()
            if job is None:
                break

            url, job_id = job
            print(f"🔍 Processing: {url}")

            try:
                page = context.new_page()
                Stealth(page)  # ✅ new API automatically applies stealth
                page.set_default_navigation_timeout(60000)
                page.goto(url, wait_until="networkidle")

                # Try to extract ytInitialPlayerResponse
                try:
                    js = page.evaluate("window.ytInitialPlayerResponse") or {}
                except Exception:
                    html = page.content()
                    match = re.search(r"ytInitialPlayerResponse\s*=\s*(\{.*?\})\s*;", html)
                    js = json.loads(match.group(1)) if match else {}

                page.close()

                streaming = js.get("streamingData", {})
                hls = streaming.get("hlsManifestUrl")

                data = (
                    {"hlsManifestUrl": hls, "cookies_used": bool(cookies_json), "stealth": True}
                    if hls
                    else {"error": "No hlsManifestUrl found (not live/DVR)", "stealth": True}
                )

            except Exception as e:
                err = traceback.format_exc(limit=1)
                print("❌ Error extracting HLS:", err)
                data = {"error": str(e), "stealth": True}

            result_dict[job_id] = data
            job_queue.task_done()

        context.close()
        browser.close()
        print("🛑 Browser closed. Worker stopped.")


# Start the background worker once
threading.Thread(target=worker, daemon=True).start()


@app.route("/api/hls")
def get_hls():
    url = request.args.get("url")
    if not url:
        return jsonify({"error": "missing ?url="}), 400

    job_id = str(time.time())
    job_queue.put((url, job_id))
    job_queue.join()

    return jsonify(result_dict.pop(job_id, {"error": "No result"}))


@app.route("/")
def home():
    return jsonify({
        "usage": "/api/hls?url=<YouTube_URL>",
        "example": "/api/hls?url=https://www.youtube.com/watch?v=5qap5aO4i9A",
        "note": "Extracts hlsManifestUrl (auto-quality) using Playwright + Stealth + Cookies."
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
