# pip install flask playwright
# playwright install chromium

from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright
import os, threading, queue, time, subprocess

# ─────────────────────────────────────────────
# ✅ Ensure Chromium installs at runtime (Render resets /tmp)
# ─────────────────────────────────────────────
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/tmp/playwright"
subprocess.run(["playwright", "install", "chromium"], check=False)

app = Flask(__name__)

# Queue for job requests (url -> result)
job_queue = queue.Queue()
result_dict = {}

def worker():
    """Background thread owning the Playwright browser (persistent)."""
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
        context = browser.new_context()
        print("✅ Playwright worker started (browser persistent).")
        while True:
            job = job_queue.get()
            if job is None:
                break

            url, job_id = job
            try:
                page = context.new_page()

                # Allow up to 2 minutes (slow free-tier CPU, YouTube loads)
                page.goto(url, wait_until="load", timeout=120000)
                page.wait_for_function(
                    "window.ytInitialPlayerResponse !== undefined",
                    timeout=120000,
                )

                js = page.evaluate("window.ytInitialPlayerResponse") or {}
                page.close()
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

# Start Playwright worker thread once (browser stays persistent)
threading.Thread(target=worker, daemon=True).start()

@app.route("/api/hls")
def get_hls():
    url = request.args.get("url")
    if not url:
        return jsonify({"error": "missing ?url="}), 400

    job_id = str(time.time())
    job_queue.put((url, job_id))
    job_queue.join()  # Wait for job to complete
    return jsonify(result_dict.pop(job_id, {"error": "No result"}))

@app.route("/")
def home():
    return jsonify({
        "usage": "/api/hls?url=<YouTube_URL>",
        "example": "/api/hls?url=https://www.youtube.com/watch?v=5qap5aO4i9A",
        "note": "Extracts hlsManifestUrl for live/DVR streams (≤1080p).",
        "auto_runtime_setup": True,
        "timeout": "2 minutes max wait per request"
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
