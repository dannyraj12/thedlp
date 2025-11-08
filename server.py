# pip install flask playwright
from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright
import os, threading, queue, time, json, subprocess

app = Flask(__name__)
job_queue = queue.Queue()
result_dict = {}

def ensure_chromium():
    """Ensure Playwright Chromium exists before launching."""
    try:
        subprocess.run(
            ["python", "-m", "playwright", "install", "chromium"],
            check=True,
        )
        print("✅ Chromium verified/installed.")
    except Exception as e:
        print(f"⚠️ Chromium install failed: {e}")

def worker():
    """Persistent browser worker."""
    with sync_playwright() as p:
        print("🚀 Launching Chromium...")
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
                "--disable-software-rasterizer", "--disable-blink-features=AutomationControlled"
            ],
        )

        # cookies
        cookies_raw = os.getenv("COOKIES", "")
        cookies = []
        if cookies_raw.strip():
            try:
                cookies = json.loads(cookies_raw)
                print(f"🍪 Loaded {len(cookies)} cookies.")
            except Exception as e:
                print(f"⚠️ Cookie JSON parse error: {e}")

        context = browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/119.0.0.0 Safari/537.36"
        )

        if cookies:
            try:
                context.add_cookies(cookies)
                print("✅ Cookies added to browser context.")
            except Exception as e:
                print(f"⚠️ Cookie injection failed: {e}")

        print("✅ Browser worker ready.")

        while True:
            job = job_queue.get()
            if job is None:
                break
            url, job_id = job
            print(f"🌐 Processing {url}")
            result = {}
            try:
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    window.chrome = { runtime: {} };
                    Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3]});
                    Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
                """)
                page.wait_for_function("window.ytInitialPlayerResponse !== undefined", timeout=75000)
                js = page.evaluate("window.ytInitialPlayerResponse")
                hls = js.get("streamingData", {}).get("hlsManifestUrl")
                result = (
                    {"hlsManifestUrl": hls, "cookies_used": bool(cookies), "auto_quality": True}
                    if hls else {"error": "no hlsManifestUrl (not live)"}
                )
                page.close()
            except Exception as e:
                result = {"error": str(e)}
            result_dict[job_id] = result
            job_queue.task_done()

        context.close()
        browser.close()

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
    return jsonify({"usage": "/api/hls?id=<id>", "note": "Playwright + cookies"})

if __name__ == "__main__":
    ensure_chromium()
    threading.Thread(target=worker, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
