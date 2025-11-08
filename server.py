from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync
import os, json, threading, queue, time, re, traceback

app = Flask(__name__)

job_queue = queue.Queue()
results = {}

def worker():
    """Background thread that owns the Playwright browser forever."""
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                        " AppleWebKit/537.36 (KHTML, like Gecko)"
                        " Chrome/120.0 Safari/537.36")
        )

        # load cookies once
        cookies_json = os.getenv("COOKIES")
        if cookies_json:
            try:
                cookies = json.loads(cookies_json)
                for c in cookies:
                    c.setdefault("sameSite", "None")
                context.add_cookies(cookies)
                print(f"🍪 Loaded {len(cookies)} cookies.")
            except Exception as e:
                print("⚠️ Cookie error:", e)

        print("✅ Browser worker ready.")

        while True:
            job = job_queue.get()
            if job is None:
                break
            url, job_id = job
            print(f"🔍 Processing {url}")
            try:
                page = context.new_page()
                stealth_sync(page)
                page.goto(url, wait_until="networkidle", timeout=60000)

                try:
                    js = page.evaluate("window.ytInitialPlayerResponse") or {}
                except Exception:
                    html = page.content()
                    m = re.search(r"ytInitialPlayerResponse\s*=\s*(\{.*?\})\s*;", html)
                    js = json.loads(m.group(1)) if m else {}

                page.close()
                streaming = js.get("streamingData", {})
                hls = streaming.get("hlsManifestUrl")
                data = (
                    {"hlsManifestUrl": hls, "stealth": True}
                    if hls else {"error": "No hlsManifestUrl found", "stealth": True}
                )
            except Exception as e:
                print("❌ Job error:", e)
                traceback.print_exc()
                data = {"error": str(e), "stealth": True}

            results[job_id] = data
            job_queue.task_done()

        browser.close()
        print("🛑 Browser closed.")


# start worker thread at startup
threading.Thread(target=worker, daemon=True).start()


@app.route("/api/hls")
def api_hls():
    url = request.args.get("url")
    if not url:
        return jsonify({"error": "missing ?url="}), 400

    job_id = str(time.time())
    job_queue.put((url, job_id))
    job_queue.join()
    return jsonify(results.pop(job_id, {"error": "No result"}))


@app.route("/")
def home():
    return jsonify({
        "usage": "/api/hls?url=<YouTube_URL>",
        "example": "/api/hls?url=https://www.youtube.com/watch?v=5qap5aO4i9A",
        "note": "Thread-safe Playwright worker. Fixes 'cannot switch to a different thread'."
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
