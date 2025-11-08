from flask import Flask, request, jsonify
import yt_dlp
import os

app = Flask(__name__)

def get_m3u8_links(video_id):
    """Extract HLS (.m3u8) links for a YouTube Live video."""
    youtube_url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=False)

            if not info:
                return {"error": "Could not extract video information."}

            if not info.get("is_live"):
                return {"error": "This is not a live stream."}

            formats = info.get("formats", [])
            hls_links = [f["url"] for f in formats if "m3u8" in f.get("url", "")]
            if not hls_links:
                return {"error": "No m3u8 links found."}

            return {
                "title": info.get("title"),
                "hls": hls_links,
                "is_live": True
            }
    except Exception as e:
        return {"error": str(e)}

@app.route("/api/hls")
def api_hls():
    """API endpoint: /api/hls?id=<YouTube_ID>"""
    video_id = request.args.get("id")
    if not video_id:
        return jsonify({"error": "Missing ?id="}), 400
    return jsonify(get_m3u8_links(video_id))

@app.route("/")
def home():
    return jsonify({
        "usage": "/api/hls?id=<YouTube_Video_ID>",
        "example": "/api/hls?id=5qap5aO4i9A",
        "note": "This version uses yt_dlp (no cookies or Playwright needed)."
    })

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
