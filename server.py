# pip install flask playwright
# playwright install chromium

from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright
import os, tempfile, threading, queue, time, subprocess

app = Flask(__name__)

# Ensure browsers install to a writable temporary directory (Render-safe)
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/tmp/playwright"
subprocess.run(["playwright", "install", "chromium"], check=False)

# Queue for job requests (id -> result)
job_queue = queue.Queue()
result_dict = {}


def worker():
    """Persistent Playwright worker thread (keeps browser open between requests)."""
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

        # ✅ Use desktop-like context to avoid YouTube bot blocks
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/130.0.0.0 Safari/537.36"
            ),
            locale="en-US,en;q=0.9",
        )

        print("✅ Playwright worker started (browser persistent).")

        while True:
            job = job_queue.get()
            if job is None:
                break
            video_url, job_id = job

            try:
                page = context.new_page()
                # ⏳ Wait for full page load (slower CPUs need more time)
                page.goto(video_url, wait_until="load", timeout=45000)

                # Wait for YouTube player data to appear
                page.wait_for_function(
                    "window.ytInitialPlayerResponse !== undefined",
                    timeout=30000,  # 30s timeout for slower servers
                )

                js = page.evaluate("window.ytInitialPlayerResponse") or {}
                page.close()

                streaming = js.get("streamingData", {})
                hls = streaming.get("hlsManifestUrl")

                if hls:
                    data = {"hlsManifestUrl": hls}
                else:
                    data = {"error": "No hlsManifestUrl found (not live/DVR)"}

            except Exception as e:
                data = {"error": str(e)}

            result_dict[job_id] = data
            job_queue.task_done()

        context.close()
        browser.close()
        print("🛑 Browser closed.")


# Start the background Playwright worker
threading.Thread(target=worker, daemon=True).start()


@app.route("/api/hls")
def get_hls():
    """Extract HLS manifest from YouTube video ID."""
    video_id = request.args.get("id")
    if not video_id:
        return jsonify({"error": "missing ?id="}), 400

    # Build full YouTube URL from ID
    url = f"https://www.youtube.com/watch?v={video_id}"

    job_id = str(time.time())
    job_queue.put((url, job_id))
    job_queue.join()  # wait for worker to finish
    return jsonify(result_dict.pop(job_id, {"error": "No result"}))


@app.route("/")
def home():
    return jsonify({
        "usage": "/api/hls?id=<YouTube_Video_ID>",
        "example": "/api/hls?id=5qap5aO4i9A",
        "note": "Returns hlsManifestUrl for live/DVR streams (≤1080p).",
        "status": "✅ Running fine on Render with persistent Playwright worker"
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
