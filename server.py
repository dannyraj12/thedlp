from flask import Flask, request, jsonify
from yt_dlp import YoutubeDL
import os, tempfile

app = Flask(__name__)

@app.route("/api/m3u8")
def get_m3u8():
    video = request.args.get("url") or request.args.get("id")
    if not video:
        return jsonify({"error": "missing ?id= or ?url="}), 400

    # Allow short YouTube IDs too
    if "youtube.com" not in video and "youtu.be" not in video:
        video = f"https://www.youtube.com/watch?v={video}"

    try:
        # ✅ Step 1: Write COOKIES env var into a real file (for login-restricted videos)
        cookies_env = os.getenv("COOKIES")
        cookiefile = None
        if cookies_env:
            tmp = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt")
            cookies_text = cookies_env.replace("\\n", "\n").strip()
            tmp.write(cookies_text)
            tmp.close()
            cookiefile = tmp.name

        # ✅ Step 2: yt-dlp options
        ydl_opts = {
            "quiet": True,
            "skip_download": True,
            "cookiefile": cookiefile,
            "sleep_interval_requests": 1,
            "ignoreerrors": True,
            "no_warnings": True,
            "format": "best",
            "extract_flat": False
        }

        # ✅ Step 3: Extract info
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video, download=False)

        # ✅ Step 4: Try to find the master (auto-quality) .m3u8 URL
        hls_url = None

        # Sometimes yt-dlp sets it as info["url"]
        if info.get("url") and "m3u8" in info["url"]:
            hls_url = info["url"]

        # Otherwise, search through formats
        if not hls_url:
            for f in info.get("formats", []):
                url = f.get("url") or ""
                protocol = f.get("protocol") or ""
                if "m3u8" in protocol and "hls_playlist" in url:
                    hls_url = url
                    break
                # fallback to any m3u8 if above missing
                elif "m3u8" in protocol and not hls_url:
                    hls_url = url

        if hls_url:
            return jsonify({
                "m3u8": hls_url,
                "title": info.get("title"),
                "id": info.get("id"),
                "uploader": info.get("uploader"),
                "duration": info.get("duration"),
                "auto_quality": True
            })

        return jsonify({
            "error": "No auto-quality m3u8 found.",
            "title": info.get("title")
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/")
def home():
    return jsonify({
        "usage": "/api/m3u8?id=VIDEO_ID or ?url=YOUTUBE_URL",
        "example": "/api/m3u8?id=5qap5aO4i9A",
        "note": "Returns auto-quality .m3u8 (144p–1080p+)"
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
