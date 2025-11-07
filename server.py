from flask import Flask, request, jsonify
from yt_dlp import YoutubeDL
import os, tempfile, textwrap

app = Flask(__name__)

@app.route("/api/m3u8")
def get_m3u8():
    video = request.args.get("url") or request.args.get("id")
    if not video:
        return jsonify({"error": "missing ?id= or ?url="}), 400

    if "youtube.com" not in video and "youtu.be" not in video:
        video = f"https://www.youtube.com/watch?v={video}"

    try:
        # ✅ Step 1: Write COOKIES env var into a real file (handle newlines)
        cookies_env = os.getenv("COOKIES")
        cookiefile = None
        if cookies_env:
            tmp = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt")
            # Reinsert newlines if Render stripped them
            cookies_text = cookies_env.replace("\\n", "\n").strip()
            tmp.write(cookies_text)
            tmp.close()
            cookiefile = tmp.name

        # ✅ Step 2: yt-dlp options (stabilized)
        ydl_opts = {
            "quiet": True,                  # suppress detailed logs
            "skip_download": True,          # we only need info, not the file
            "cookiefile": cookiefile,       # use cookies for auth/trust
            "sleep_interval_requests": 1,   # prevent HTTP 429 (Too Many Requests)
            "ignoreerrors": True,           # skip any minor extraction errors
            "no_warnings": True,            # hide warnings in console/logs
        }

        # ✅ Step 3: Extract info using yt-dlp
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video, download=False)

        # ✅ Step 4: Return .m3u8 if found
        formats = info.get("formats", [])
        for f in formats:
            if "m3u8" in (f.get("protocol") or ""):
                return jsonify({
                    "m3u8": f["url"],
                    "title": info.get("title"),
                    "id": info.get("id"),
                    "uploader": info.get("uploader")
                })
        return jsonify({"error": "no m3u8 found", "title": info.get("title")})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/")
def home():
    return jsonify({
        "usage": "/api/m3u8?id=VIDEO_ID",
        "example": "/api/m3u8?id=5qap5aO4i9A"
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
