# pip install flask playwright
# playwright install chromium

from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright
import os, threading, queue, time, subprocess, re, json

app = Flask(__name__)

# ─────────────────────────────────────────────
# ✅ Ensure Chromium installs every time Render restarts
# ─────────────────────────────────────────────
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/tmp/playwright"
subprocess.run(["playwright", "install", "chromium"], check=False)

# ─────────────────────────────────────────────
# ✅ Persistent Playwright Worker Setup
# ─────────────────────────────────────────────
job_queue = queue.Queue()
result_dict = {}

def worker():
    """Background thread that keeps a persistent Playwright browser open."""
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--disable-software-rasterizer",
                "--disable-background-timer-throttling",
                "--disable-renderer-backgrounding",
            ],
        )

        # ✅ Anti-bot, realistic desktop fingerprint
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            locale="en-US",
            timezone_id="Asia/Kolkata",
            java_script_enabled=True,
        )

        # Hide automation fingerprints
        context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3]});
        Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
        Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
        """)

        print("✅ Playwright worker started (browser persistent).")

        while True:
            job = job_queue.get()
            if job is None:
                break

            url, job_id = job
            try:
                page = context.new_page()

                # Wait for full page + JS load
                page.goto(url, wait_until="networkidle", timeout=120000)
                time.sleep(3)

                # Try direct JS evaluation first
                js = page.evaluate("window.ytInitialPlayerResponse || null")

                # Fallback: parse from HTML if blocked
                if not js:
                    html = page.content()
                    match = re.search(r"ytInitialPlayerResponse\\s*=\\s*(\\{.*?\\})\\s*;", html)
                    if match:
                        try:
                            js = json.loads(match.group(1))
                        except Exception:
                            js = None

                page.close()

                if not js:
                    data = {"error": "ytInitialPlayerResponse not found (YouTube JS blocked or stripped)"}
                else:
                    streaming = js.get("streamingData", {})
                    hls = streaming.get("hlsManifestUrl")
                    data = (
                        {"hlsManifestUrl": hls}
                        if hls
                        else {"error": "No hlsManifestUrl found (not live/DVR)"}
                    )

            except Exception as e:
                data = {"error": str(e)}

            result_dict[job_id] = data
            job_queue.task_done()

        context.close()
        browser.close()
        print("🛑 Browser closed.")

# Start persistent worker thread
threading.Thread(target=worker, daemon=True).start()

# ─────────────────────────────────────────────
# ✅ API Route — accepts YouTube video ID (?id=)
# ─────────────────────────────────────────────
@app.route("/api/hls")
def get_hls():
    video_id = request.args.get("id")
    if not video_id:
        return jsonify({"error": "missing ?id="}), 400

    url = f"https://www.youtube.com/watch?v={video_id}"
    job_id = str(time.time())

    job_queue.put((url, job_id))
    job_queue.join()

    return jsonify(result_dict.pop(job_id, {"error": "No result"}))

# ─────────────────────────────────────────────
# ✅ Root route
# ─────────────────────────────────────────────
@app.route("/")
def home():
    return jsonify({
        "usage": "/api/hls?id=<YouTube_Video_ID>",
        "example": "/api/hls?id=5qap5aO4i9A",
        "note": "Returns hlsManifestUrl for live/DVR streams (≤1080p).",
        "optimized_for": "Render + Playwright stealth mode",
        "fallback": "Parses HTML if JS blocked"
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
