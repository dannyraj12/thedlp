# pip install flask playwright
from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright
import os, tempfile, threading, queue, time, subprocess

app = Flask(__name__)

# ───────────────────────────────
# ✅ Auto-install Chromium at runtime if missing
# ───────────────────────────────
try:
    from playwright.sync_api import sync_playwright
    chromium_path = "/opt/render/.cache/ms-playwright"
    if not os.path.exists(chromium_path):
        os.makedirs(chromium_path, exist_ok=True)
    if not os.path.exists(os.path.join(chromium_path, "chromium-1187")):
        print("⚙️ Installing Chromium runtime...")
        subprocess.run(["python", "-m", "playwright", "install", "chromium"], check=True)
except Exception as e:
    print(f"⚠️ Failed to preinstall Chromium: {e}")

# ───────────────────────────────
# Queue setup
# ───────────────────────────────
job_queue = queue.Queue()
result_dict = {}

def worker():
    """Persistent browser worker for YouTube HLS extraction."""
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
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_function("window.ytInitialPlayerResponse !== undefined", timeout=20000)
                js = page.evaluate("window.ytInitialPlayerResponse") or {}
                streaming = js.get("streamingData", {})
                hls = streaming.get("hlsManifestUrl")
                data = (
                    {"hlsManifestUrl": hls}
                    if hls
                    else {"error": "No hlsManifestUrl found (not live/DVR)"}
                )
                page.close()
            except Exception as e:
                data = {"error": str(e)}
            result_dict[job_id] = data
            job_queue.task_done()
        context.close()
        browser.close()
        print("🛑 Browser closed.")

# Start background worker
threading.Thread(target=worker, daemon=True).start()

@app.route("/api/hls")
def get_hls():
    vid = request.args.get("id")
    if not vid:
        return jsonify({"error": "missing ?id="}), 400
    url = f"https://www.youtube.com/watch?v={vid}"
    job_id = str(time.time())
    job_queue.put((url, job_id))
    job_queue.join()
    return jsonify(result_dict.pop(job_id, {"error": "No result"}))

@app.route("/")
def home():
    return jsonify({
        "usage": "/api/hls?id=<YouTube_Video_ID>",
        "example": "/api/hls?id=uXNU0XgGZhs",
        "note": "Auto-installs Chromium on first run. Extracts HLS manifest."
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
