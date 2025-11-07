from flask import Flask, request, jsonify
from yt_dlp import YoutubeDL
import os

app = Flask(__name__)

@app.route("/api/m3u8")
def get_m3u8():
    video = request.args.get("url") or request.args.get("id")
    if not video:
        return jsonify({"error": "missing ?id= or ?url="}), 400

    if "youtube.com" not in video and "youtu.be" not in video:
        video = f"https://www.youtube.com/watch?v={video}"

    try:
        ydl_opts = {"quiet": True, "skip_download": True}
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video, download=False)

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
