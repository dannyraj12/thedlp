# pip install flask playwright
# playwright install chromium
from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright
import os, json, threading, queue, time, traceback

app = Flask(__name__)

job_queue = queue.Queue()
result_dict = {}
worker_status = {"state": "starting", "last_error": None, "cookies_count": 0}

def ensure_chromium(p):
    """Ensure chromium is installed on render"""
    try:
        browser_path = p.chromium.executable_path()
        print(f"✅ Chromium ready at {browser_path}")
    except Exception as e:
        print(f"⚠️ Chromium not ready yet: {e}")
        print("Installing Chromium...")
        os.system("python -m playwright install chromium --with-deps")

def worker():
    """Background worker that holds the persistent Playwright browser."""
    with sync_playwright() as p:
        ensure_chromium(p)
        for attempt in range(3):
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
                print("✅ Browser launch successful.")
                break
            except Exception as e:
                print(f"❌ Launch attempt {attempt+1} failed: {e}")
                time.sleep(5)
        else:
            print("🚫 Browser launch failed after 3 attempts.")
            worker_status["state"] = "failed"
            return

        context = browser.new_context()
        # Load cookies from environment
        cookies_json = os.getenv("COOKIES")
        if cookies_json:
            try:
                cookies = json.loads(cookies_json)
                # Auto add sameSite if missing
                for c in cookies:
                    c.setdefault("sameSite", "None")
                context.add_cookies(cookies)
                worker_status["cookies_count"] = len(cookies)
                print(f"🍪 Added {len(cookies)} cookies from env.")
            except Exception as e:
                print(f"⚠️ Cookie load failed: {e}")
                worker_status["last_error"] = str(e)
        else:
            print("⚠️ No cookies found in env.")
            worker_status["cookies_count"] = 0

        page = None
        worker_status["state"] = "ready"

        while True:
            job = job_queue.get()
            if job is None:
                break
            url, job_id = job
            print(f"🔍 Processing job for {url}")
            try:
                page = context.new_page()
                page.set_default_navigation_timeout(90000)
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_function(
                    "window.ytInitialPlayerResponse !== undefined",
                    timeout=90000
                )
                js = page.evaluate("window.ytInitialPlayerResponse") or {}
                page.close()
                streaming = js.get("streamingData", {})
                hls = streaming.get("hlsManifestUrl")
                data = (
                    {"hlsManifestUrl": hls, "auto_quality": True, "cookies_used": True}
                    if hls
                    else {"error": "No hlsManifestUrl found (not live/DVR)"}
                )
            except Exception as e:
                print("❌ Error:", e)
                traceback.print_exc()
                data = {"error": str(e)}
                worker_status["last_error"] = str(e)
            result_dict[job_id] = data
            job_queue.task_done()

        if page:
            page.close()
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
    job_queue.put((url, job_id))
    job_queue.join()
    return jsonify(result_dict.pop(job_id, {"error": "No result"}))


@app.route("/status")
def status():
    return jsonify(worker_status)


@app.route("/")
def home():
    return jsonify({
        "usage": "/api/hls?id=<YouTube_Video_ID>",
        "example": "/api/hls?id=uXNU0XgGZhs",
        "note": "Extracts hlsManifestUrl (auto-quality, 1080p supported) using Playwright with cookies."
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
