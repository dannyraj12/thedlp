# pip install flask playwright
# playwright install chromium
from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright
import os, threading, queue, time, subprocess

app = Flask(__name__)

# ─────────────────────────────────────────────
# ✅ Ensure Chromium installs (Render clears /tmp each boot)
# ─────────────────────────────────────────────
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/tmp/playwright"
subprocess.run(["playwright", "install", "chromium"], check=False)

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

        # ✅ Spoof desktop Chrome user agent
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720}
        )

        print("✅ Playwright worker started (browser persistent).")

        while True:
            job = job_queue.get()
            if job is None:
                break

            url, job_id = job
            try:
                page = context.new_page()

                # ✅ Wait for full network activity to settle (Render CPUs are slow)
                page.goto(url, wait_until="networkidle", timeout=120000)
                time.sleep(3)  # Let YouTube JS fully initialize

                js = page.evaluate("window.ytInitialPlayerResponse || null")
                page.close()

                if not js:
                    data = {"error": "ytInitialPlayerResponse not found (JS blocked or delayed)"}
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

# Start worker thread once (persistent browser session)
threading.Thread(target=worker, daemon=True).start()

# ─────────────────────────────────────────────
# ✅ Route — supports YouTube video ID (?id=)
# ─────────────────────────────────────────────
@app.route("/api/hls")
def get_hls():
    video_id = request.args.get("id")
    if not video_id:
        return jsonify({"error": "missing ?id="}), 400

    # Build full YouTube URL from ID
    url = f"https://www.youtube.com/watch?v={video_id}"

    job_id = str(time.time())
    job_queue.put((url, job_id))
    job_queue.join()  # Wait for worker to finish
    return jsonify(result_dict.pop(job_id, {"error": "No result"}))

@app.route("/")
def home():
    return jsonify({
        "usage": "/api/hls?id=<YouTube_Video_ID>",
        "example": "/api/hls?id=5qap5aO4i9A",
        "note": "Returns hlsManifestUrl for live/DVR streams (≤1080p).",
        "optimized_for": "Render + Playwright headless",
        "timeout": "Up to 120s max for slow cold starts"
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
