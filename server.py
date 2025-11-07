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

        # ✅ Step 2: Pass that file path to yt-dlp
        ydl_opts = {
            "quiet": True,
            "skip_download": True,
            "cookiefile": cookiefile,
        }

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video, download=False)

        # ✅ Step 3: Return m3u8 if found
        formats = info.get("formats", [])
        for f in formats:
            if "m3u8" in (f.get("protocol") or ""):
                return jsonify({"m3u8": f["url"], "title": info.get("title")})
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
