# pip install flask yt-dlp
from flask import Flask, request, jsonify
from yt_dlp import YoutubeDL
import os

app = Flask(__name__)

@app.route("/api/hls")
def get_hls():
    vid = request.args.get("id")
    if not vid:
        return jsonify({"error": "missing ?id="}), 400
    url = f"https://www.youtube.com/watch?v={vid}"

    try:
        with YoutubeDL({"quiet": True, "skip_download": True}) as ydl:
            info = ydl.extract_info(url, download=False)
            for f in info.get("formats", []):
                if "m3u8" in (f.get("protocol") or ""):
                    return jsonify({
                        "hlsManifestUrl": f["url"],
                        "title": info.get("title"),
                        "uploader": info.get("uploader")
                    })
        return jsonify({"error": "no m3u8 found (not live/DVR)"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/")
def home():
    return jsonify({
        "usage": "/api/hls?id=<YouTube_Video_ID>",
        "example": "/api/hls?id=5qap5aO4i9A",
        "note": "Uses yt-dlp to extract HLS manifest reliably (no browser)"
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
