# pip install flask yt-dlp
from flask import Flask, request, jsonify
from yt_dlp import YoutubeDL
import os, tempfile, atexit

app = Flask(__name__)

# ─────────────────────────────────────────────
# Load COOKIES from environment variable (Render)
# ─────────────────────────────────────────────
cookiefile_path = None
cookies_env = os.getenv("COOKIES")
if cookies_env:
    tmp = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt")
    tmp.write(cookies_env.replace("\\n", "\n").strip())
    tmp.close()
    cookiefile_path = tmp.name
    atexit.register(lambda: os.remove(cookiefile_path) if os.path.exists(cookiefile_path) else None)

# ─────────────────────────────────────────────
# Main HLS extractor route
# ─────────────────────────────────────────────
@app.route("/api/hls")
def get_hls():
    vid = request.args.get("id")
    if not vid:
        return jsonify({"error": "missing ?id="}), 400

    url = f"https://www.youtube.com/watch?v={vid}"

    # yt-dlp options
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "geo_bypass": True,
        "extract_flat": False,
        "force_generic_extractor": False,
    }

    if cookiefile_path:
        ydl_opts["cookiefile"] = cookiefile_path

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return jsonify({"error": "No info extracted (maybe invalid ID or private video)"}), 404

            formats = info.get("formats", [])
            for f in formats:
                if "m3u8" in (f.get("protocol") or ""):
                    return jsonify({
                        "hlsManifestUrl": f["url"],
                        "title": info.get("title"),
                        "uploader": info.get("uploader"),
                        "auto_quality": True,
                        "cookies_used": bool(cookiefile_path)
                    })

        return jsonify({"error": "No m3u8 found (not live/DVR stream)"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/")
def home():
    return jsonify({
        "usage": "/api/hls?id=<YouTube_Video_ID>",
        "example": "/api/hls?id=uXNU0XgGZhs",
        "note": "✅ Auto-quality up to 1080p HLS using yt-dlp + cookies."
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
