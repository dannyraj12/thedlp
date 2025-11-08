# pip install flask playwright
# playwright install chromium
from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright
import os, tempfile, threading, queue, time, atexit

app = Flask(__name__)

# Queue system (keep 1 Chromium alive)
job_queue = queue.Queue()
result_dict = {}

# ─────────────────────────────
# ✅ Handle cookies from ENV
# ─────────────────────────────
cookiefile_path = None
cookies_env = os.getenv("COOKIES")
if cookies_env:
    tmp = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt")
    tmp.write(cookies_env.replace("\\n", "\n").strip())
    tmp.close()
    cookiefile_path = tmp.name
    atexit.register(lambda: os.remove(cookiefile_path) if os.path.exists(cookiefile_path) else None)

# ─────────────────────────────
# ✅ Background Playwright Worker
# ─────────────────────────────
def worker():
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
                "--no-zygote",
                "--disable-extensions",
            ],
        )
        context = browser.new_context()
        print("✅ Playwright worker started (persistent browser).")

        # Add cookies if provided
        if cookiefile_path:
            try:
                with open(cookiefile_path, "r") as f:
                    raw = f.read().strip()
                    # accept both Netscape and JSON cookie formats
                    if raw.startswith("["):
                        import json
                        cookies = json.loads(raw)
                        context.add_cookies(cookies)
            except Exception as e:
                print("Cookie load error:", e)

        while True:
            job = job_queue.get()
            if job is None:
                break
            video_id, job_id = job
            try:
                url = f"https://www.youtube.com/watch?v={video_id}"
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=60000)

                # Wait up to 90 sec for ytInitialPlayerResponse (Render is slower)
                page.wait_for_function(
                    "window.ytInitialPlayerResponse !== undefined",
                    timeout=90000
                )
                js = page.evaluate("window.ytInitialPlayerResponse")
                page.close()

                if not js:
                    data = {"error": "ytInitialPlayerResponse not found (page restricted)"}
                else:
                    streaming = js.get("streamingData", {})
                    hls = streaming.get("hlsManifestUrl")
                    if hls:
                        data = {
                            "auto_quality": True,
                            "cookies_used": bool(cookiefile_path),
                            "hlsManifestUrl": hls,
                            "title": js.get("videoDetails", {}).get("title"),
                            "uploader": js.get("videoDetails", {}).get("author"),
                        }
                    else:
                        data = {"error": "No hlsManifestUrl (not live/DVR)"}
            except Exception as e:
                data = {"error": str(e)}
            result_dict[job_id] = data
            job_queue.task_done()

        context.close()
        browser.close()
        print("🛑 Browser closed.")

# Start persistent browser once
threading.Thread(target=worker, daemon=True).start()

# ─────────────────────────────
# ✅ API Route
# ─────────────────────────────
@app.route("/api/hls")
def get_hls():
    video_id = request.args.get("id")
    if not video_id:
        return jsonify({"error": "missing ?id="}), 400

    job_id = str(time.time())
    job_queue.put((video_id, job_id))
    job_queue.join()
    return jsonify(result_dict.pop(job_id, {"error": "No result"}))

# ─────────────────────────────
# ✅ Info Route
# ─────────────────────────────
@app.route("/")
def home():
    return jsonify({
        "usage": "/api/hls?id=<YouTube_Video_ID>",
        "example": "/api/hls?id=uXNU0XgGZhs",
        "note": "Returns adaptive (multi-quality) HLS manifest using real browser.",
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
