# pip install flask yt-dlp
from flask import Flask, request, jsonify
from yt_dlp import YoutubeDL
import os, tempfile, atexit

app = Flask(__name__)

# ────────────────────────────────
# ✅ Handle Cookies from Environment
# ────────────────────────────────
cookiefile_path = None
cookies_env = os.getenv("COOKIES")
if cookies_env:
    tmp = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt")
    tmp.write(cookies_env.replace("\\n", "\n").strip())
    tmp.close()
    cookiefile_path = tmp.name
    atexit.register(lambda: os.remove(cookiefile_path) if os.path.exists(cookiefile_path) else None)

# ────────────────────────────────
# ✅ Route: /api/hls?id=<video_id>
# ────────────────────────────────
@app.route("/api/hls")
def get_hls():
    vid = request.args.get("id")
    if not vid:
        return jsonify({"error": "missing ?id="}), 400

    url = f"https://www.youtube.com/watch?v={vid}"

    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "no_warnings": True,
        "geo_bypass": True,
        "extract_flat": False,
        "force_generic_extractor": False,

        # 🔹 Pretend to be desktop Chrome (helps get 720p–1080p)
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "*/*",
            "Origin": "https://www.youtube.com",
            "Referer": "https://www.youtube.com/",
        },
    }

    if cookiefile_path:
        ydl_opts["cookiefile"] = cookiefile_path

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return jsonify({"error": "Failed to extract info"}), 500

            # 🔹 Collect all m3u8/native HLS formats
            hls_formats = [
                f for f in info.get("formats", [])
                if "m3u8" in (f.get("protocol") or "") or "m3u8" in (f.get("url") or "")
            ]

            if not hls_formats:
                return jsonify({"error": "No HLS formats found (not live/DVR)"}), 404

            # 🔹 Sort formats by resolution height
            hls_formats.sort(key=lambda f: f.get("height", 0), reverse=True)
            best = hls_formats[0]

            return jsonify({
                "hlsManifestUrl": best["url"],
                "quality": f"{best.get('height', '?')}p",
                "title": info.get("title"),
                "uploader": info.get("uploader"),
                "cookies_used": bool(cookiefile_path),
                "auto_quality": True
            })

    except Exception as e:
        return jsonify({"error": str(e)})

# ────────────────────────────────
# ✅ Root route for info
# ────────────────────────────────
@app.route("/")
def home():
    return jsonify({
        "usage": "/api/hls?id=<YouTube_Video_ID>",
        "example": "/api/hls?id=uXNU0XgGZhs",
        "note": "Forces Chrome headers + cookies to get up to 1080p adaptive HLS."
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
