from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright
import os, tempfile, threading, queue, time

app = Flask(__name__)

# Queue for job requests (url -> result)
job_queue = queue.Queue()
result_dict = {}

def worker():
    """Background thread owning the Playwright browser."""
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
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_function("window.ytInitialPlayerResponse !== undefined", timeout=15000)
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

# Start the worker thread once
threading.Thread(target=worker, daemon=True).start()

# ─────────────────────────────────────────────
# ✅ Updated route — only accepts YouTube video ID (?id=)
# ─────────────────────────────────────────────
@app.route("/api/hls")
def get_hls():
    video_id = request.args.get("id")
    if not video_id:
        return jsonify({"error": "missing ?id="}), 400

    # Build full YouTube URL from the ID
    url = f"https://www.youtube.com/watch?v={video_id}"

    job_id = str(time.time())
    job_queue.put((url, job_id))
    job_queue.join()  # wait for the worker to finish
    return jsonify(result_dict.pop(job_id, {"error": "No result"}))

@app.route("/")
def home():
    return jsonify({
        "usage": "/api/hls?id=<YouTube_Video_ID>",
        "example": "/api/hls?id=5qap5aO4i9A",
        "note": "Returns hlsManifestUrl for live/DVR streams (≤1080 p)."
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
