from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync  # ✅ old stable version import
import os, json, threading, queue, time, traceback, re

def worker():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0 Safari/537.36"
        )

        cookies_json = os.getenv("COOKIES")
        if cookies_json:
            try:
                cookies = json.loads(cookies_json)
                for c in cookies:
                    c.setdefault("sameSite", "None")
                context.add_cookies(cookies)
                print(f"🍪 Added {len(cookies)} cookies.")
            except Exception as e:
                print(f"⚠️ Failed to load cookies: {e}")

        while True:
            job = job_queue.get()
            if job is None:
                break
            url, job_id = job
            try:
                page = context.new_page()
                stealth_sync(page)  # ✅ stable stealth injection
                page.goto(url, wait_until="networkidle", timeout=60000)

                try:
                    js = page.evaluate("window.ytInitialPlayerResponse") or {}
                except:
                    html = page.content()
                    match = re.search(r"ytInitialPlayerResponse\s*=\s*(\{.*?\})\s*;", html)
                    js = json.loads(match.group(1)) if match else {}

                page.close()
                streaming = js.get("streamingData", {})
                hls = streaming.get("hlsManifestUrl")
                data = {"hlsManifestUrl": hls} if hls else {"error": "No hlsManifestUrl found"}
            except Exception as e:
                data = {"error": str(e)}
            result_dict[job_id] = data
            job_queue.task_done()

        context.close()
        browser.close()
