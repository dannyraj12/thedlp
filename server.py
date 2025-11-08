# pip install flask playwright
from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright
import os, threading, queue, time, json, subprocess, traceback

app = Flask(__name__)
job_queue = queue.Queue()
result_dict = {}
worker_status = {"state": "starting", "last_error": None, "cookies_count": 0}

def ensure_chromium():
    """Ensure Chromium binary exists (safe install)."""
    try:
        print("🔧 ensure_chromium: attempting playwright chromium install (idempotent)...")
        subprocess.run(["python", "-m", "playwright", "install", "chromium"], check=True, timeout=600)
        print("✅ ensure_chromium: chromium installed/verified.")
    except Exception as e:
        print("⚠️ ensure_chromium: install failed:", e)
        # still continue — worker will retry browser launch and log detailed error

def _parse_cookies():
    """Load JSON cookies from COOKIES env. Return list or [] and set worker_status."""
    raw = os.getenv("COOKIES", "").strip()
    if not raw:
        worker_status["cookies_count"] = 0
        return []
    try:
        cookies = json.loads(raw)
        if not isinstance(cookies, list):
            raise ValueError("COOKIES must be a JSON array of cookie objects")
        worker_status["cookies_count"] = len(cookies)
        return cookies
    except Exception as e:
        print("⚠️ parse_cookies error:", e)
        worker_status["last_error"] = f"cookie-parse-error: {e}"
        worker_status["cookies_count"] = 0
        return []

def worker():
    """Persistent Playwright worker with retries and verbose logging."""
    global worker_status
    try:
        cookies = _parse_cookies()
        # retry launching browser a few times if something transient happens
        attempts = 0
        max_attempts = 3
        browser = None
        with sync_playwright() as p:
            while attempts < max_attempts:
                attempts += 1
                try:
                    print(f"🧪 worker: Launch attempt {attempts} for Playwright browser...")
                    browser = p.chromium.launch(
                        headless=True,
                        args=[
                            "--no-sandbox",
                            "--disable-gpu",
                            "--disable-dev-shm-usage",
                            "--disable-software-rasterizer",
                            "--disable-background-timer-throttling",
                            "--disable-renderer-backgrounding",
                            "--disable-blink-features=AutomationControlled",
                        ],
                        timeout=60000,
                    )
                    print("✅ worker: browser.launch succeeded.")
                    break
                except Exception as e:
                    print(f"❌ worker: browser.launch attempt {attempts} failed: {e}")
                    traceback.print_exc()
                    worker_status["last_error"] = f"launch-failed-{attempts}:{e}"
                    time.sleep(3 * attempts)

            if not browser:
                worker_status["state"] = "browser_launch_failed"
                print("🛑 worker: all browser launch attempts failed. Exiting worker.")
                return

            # create a single persistent context
            context = browser.new_context(
                viewport={"width": 1366, "height": 768},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/119.0.0.0 Safari/537.36"
                ),
            )

            # Add init script to spoof common headless indicators (applies to every page)
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                window.chrome = window.chrome || { runtime: {} };
                Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
                Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
            """)

            if cookies:
                try:
                    # ensure cookies are objects; Playwright accepts domain/path based cookies
                    context.add_cookies(cookies)
                    print(f"🍪 worker: added {len(cookies)} cookies to context.")
                    worker_status["cookies_count"] = len(cookies)
                except Exception as e:
                    print("⚠️ worker: failed to add cookies:", e)
                    traceback.print_exc()
                    worker_status["last_error"] = f"cookie-add-failed:{e}"

            worker_status["state"] = "ready"
            print("✅ worker: ready and waiting for jobs.")

            # main loop
            while True:
                job = job_queue.get()
                if job is None:
                    print("worker: received shutdown signal.")
                    break
                url, job_id = job
                print(f"➡️ worker: processing job {job_id} -> {url}")
                data = {}
                try:
                    page = context.new_page()
                    # set Accept-Language header to reduce localized consent pages
                    page.set_extra_http_headers({"Accept-Language": "en-US,en;q=0.9"})
                    page.goto(url, wait_until="domcontentloaded", timeout=90000)
                    # Give plenty of time for YT's heavy JS (90s)
                    try:
                        page.wait_for_function("window.ytInitialPlayerResponse !== undefined", timeout=90000)
                    except Exception as e_wait:
                        # capture HTML to detect common consent/bot text
                        html = page.content().lower()
                        if "verify" in html or "captcha" in html or "consent" in html or "robot" in html:
                            data = {"error": "YouTube bot/consent page detected"}
                            print("🚫 worker: detected consent/bot page in HTML.")
                        else:
                            raise

                    if not data:
                        js = page.evaluate("window.ytInitialPlayerResponse")
                        streaming = js.get("streamingData", {}) if js else {}
                        hls = streaming.get("hlsManifestUrl")
                        if hls:
                            data = {"hlsManifestUrl": hls, "cookies_used": bool(cookies), "auto_quality": True}
                            print(f"✅ worker: job {job_id} found hlsManifestUrl.")
                        else:
                            data = {"error": "no hlsManifestUrl (not live/DVR)"}
                            print(f"⚠️ worker: job {job_id} no hls found.")
                    page.close()
                except Exception as e:
                    data = {"error": str(e)}
                    print("❌ worker: exception while processing job:", e)
                    traceback.print_exc()
                    worker_status["last_error"] = str(e)

                result_dict[job_id] = data
                job_queue.task_done()

            # cleanup
            worker_status["state"] = "stopped"
            context.close()
            browser.close()
            print("🛑 worker: browser/context closed, worker finished.")
    except Exception as e_outer:
        print("🔥 worker: uncaught exception, crashing worker:", e_outer)
        traceback.print_exc()
        worker_status["state"] = "crashed"
        worker_status["last_error"] = str(e_outer)

# API endpoints
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

@app.route("/status")
def status():
    return jsonify(worker_status)

@app.route("/")
def home():
    return jsonify({
        "usage": "/api/hls?id=<YouTube_ID>",
        "example": "/api/hls?id=uXNU0XgGZhs",
        "note": "Use /status to inspect worker state and cookie count."
    })

if __name__ == "__main__":
    # Install chromium before starting worker to avoid race on Render
    ensure_chromium()
    # start worker thread after chromium ensured
    t = threading.Thread(target=worker, daemon=True)
    t.start()
    # run flask
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
