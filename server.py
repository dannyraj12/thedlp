# pip install flask playwright requests
# playwright install chromium

from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright
import os, threading, queue, time, subprocess, re, json, requests

app = Flask(__name__)

os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/tmp/playwright"
subprocess.run(["playwright", "install", "chromium"], check=False)

job_queue = queue.Queue()
result_dict = {}

def extract_with_playwright(url, context):
    """Try to extract using Playwright (JS or HTML parsing)."""
    page = context.new_page()
    page.goto(url, wait_until="networkidle", timeout=120000)
    time.sleep(3)

    # Try direct JS
    js = page.evaluate("window.ytInitialPlayerResponse || null")
    if not js:
        html = page.content()
        match = re.search(r"ytInitialPlayerResponse\s*=\s*(\{.*?\})\s*;", html)
        if match:
            try:
                js = json.loads(match.group(1))
            except Exception:
                js = None
    page.close()
    return js

def fallback_get_info(video_id):
    """Use YouTube public info endpoint as fallback."""
    try:
        params = {"video_id": video_id, "html5": "1", "c": "TVHTML5", "cver": "7.20241026"}
        resp = requests.get("https://www.youtube.com/get_video_info", params=params, timeout=15)
        if "hlsManifestUrl" in resp.text:
            hls = re.search(r"hlsManifestUrl=([^&]+)", resp.text)
            if hls:
                import urllib.parse
                return urllib.parse.unquote(hls.group(1))
        return None
    except Exception:
        return None

def worker():
    """Persistent Playwright worker."""
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            locale="en-US",
            timezone_id="Asia/Kolkata",
        )
        context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)

        print("✅ Playwright worker started (browser persistent).")

        while True:
            job = job_queue.get()
            if job is None:
                break
            url, job_id, video_id = job
            data = {}
            try:
                js = extract_with_playwright(url, context)
                if js:
                    hls = js.get("streamingData", {}).get("hlsManifestUrl")
                    if hls:
                        data = {"hlsManifestUrl": hls}
                    else:
                        data = {"error": "No hlsManifestUrl found (not live/DVR)"}
                else:
                    # 🔁 Fallback: use get_video_info API
                    hls = fallback_get_info(video_id)
                    if hls:
                        data = {"hlsManifestUrl": hls, "source": "fallback_api"}
                    else:
                        data = {"error": "ytInitialPlayerResponse not found and fallback failed"}
            except Exception as e:
                data = {"error": str(e)}

            result_dict[job_id] = data
            job_queue.task_done()

        context.close()
        browser.close()
        print("🛑 Browser closed.")

threading.Thread(target=worker, daemon=True).start()

@app.route("/api/hls")
def get_hls():
    video_id = request.args.get("id")
    if not video_id:
        return jsonify({"error": "missing ?id="}), 400

    url = f"https://www.youtube.com/watch?v={video_id}"
    job_id = str(time.time())
    job_queue.put((url, job_id, video_id))
    job_queue.join()
    return jsonify(result_dict.pop(job_id, {"error": "No result"}))

@app.route("/")
def home():
    return jsonify({
        "usage": "/api/hls?id=<YouTube_Video_ID>",
        "example": "/api/hls?id=5qap5aO4i9A",
        "note": "Tries Playwright first, falls back to YouTube API.",
        "optimized_for": "Render headless environment"
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
