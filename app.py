# updated app.py — returns only the auto/master m3u8 and supports cookies via ENV
from flask import Flask, render_template, request, jsonify
import yt_dlp
import re
import logging
import os
import tempfile

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

def extract_video_id(url):
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([^&\n?#]+)',
        r'youtube\.com\/live\/([^&\n?#]+)'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def write_cookies_from_env():
    """
    If COOKIES env var is present, write it to a temp file and return path.
    Expect COOKIES to contain Netscape cookie format (cookies.txt) OR raw cookie text.
    """
    cookies_env = os.getenv("COOKIES")
    if not cookies_env:
        return None
    # create temp file
    fd, path = tempfile.mkstemp(prefix="yt_cookies_", suffix=".txt")
    os.close(fd)
    # Write raw content to file.
    # If user pasted JSON or something else, this still writes it — yt_dlp expects Netscape format,
    # so best to paste exported cookies.txt content into COOKIES in Render/Replit.
    with open(path, "w", encoding="utf-8") as f:
        f.write(cookies_env)
    logging.info(f"Cookies written to {path}")
    return path

def get_master_hls(youtube_url, cookiefile_path=None):
    """
    Use yt_dlp to extract info and return a single auto/master m3u8 URL (if available).
    """
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        # we want full extraction (not flattened)
        "extract_flat": False,
    }
    if cookiefile_path:
        ydl_opts["cookiefile"] = cookiefile_path

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=False)

            if not info:
                return {"error": "Could not extract video information."}

            # if not live, return friendly message
            if not info.get("is_live"):
                return {"error": "This is not a live stream."}

            formats = info.get("formats", []) or []
            # Look for first m3u8/master playlist url — yt-dlp sometimes includes many m3u8 variant URLs,
            # the master (auto) is usually the first m3u8 encountered in formats.
            for f in formats:
                url = f.get("url", "")
                if isinstance(url, str) and "m3u8" in url:
                    return {
                        "title": info.get("title"),
                        "is_live": True,
                        "hlsManifestUrl": url
                    }
            return {"error": "No hlsManifestUrl found."}
    except Exception as exc:
        msg = str(exc)
        # yt-dlp common message for YouTube private/age gate/bot check:
        if "Sign in to confirm you" in msg or "Sign in to confirm you're not a bot" in msg:
            return {
                "error": ("yt-dlp requires authentication/cookies for this video. "
                          "Provide YouTube cookies via the COOKIES env var (Netscape cookies.txt format). "
                          "See: https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp"),
                "detail": msg
            }
        # Generic error
        return {"error": msg}

@app.route("/api/hls")
def api_hls():
    """
    Accepts: /api/hls?id=<YouTube_ID>
    """
    video_id = request.args.get("id")
    if not video_id:
        return jsonify({"error": "Missing ?id="}), 400

    youtube_url = f"https://www.youtube.com/watch?v={video_id}"

    # If COOKIES env var present, write to temp file and pass to yt-dlp
    cookiefile = write_cookies_from_env()

    result = get_master_hls(youtube_url, cookiefile_path=cookiefile)

    # If we created a cookie temp file, optionally remove it after use
    if cookiefile and os.path.exists(cookiefile):
        try:
            os.remove(cookiefile)
        except Exception:
            pass

    return jsonify(result)

@app.route("/")
def home():
    return jsonify({
        "usage": "/api/hls?id=<YouTube_Video_ID>",
        "example": "/api/hls?id=5qap5aO4i9A",
        "note": "This version uses yt-dlp and returns the master (auto) m3u8 URL. "
                "If yt-dlp complains about signing in, provide cookies in COOKIES env var (Netscape cookies.txt content)."
    })

if __name__ == '__main__':
    # Use environment PORT if provided (Render/Heroku), otherwise default to 5000 for Replit
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
