from flask import Flask, request, jsonify
from yt_dlp import YoutubeDL
import os, tempfile, re

app = Flask(__name__)

@app.route("/api/m3u8")
def get_m3u8():
    video = request.args.get("url") or request.args.get("id")
    if not video:
        return jsonify({"error": "missing ?id= or ?url="}), 400

    # Normalize input
    if "youtube.com" not in video and "youtu.be" not in video:
        video = f"https://www.youtube.com/watch?v={video}"

    try:
        # ✅ Optional cookies for restricted videos
        cookies_env = os.getenv("COOKIES")
        cookiefile = None
        if cookies_env:
            tmp = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt")
            cookies_text = cookies_env.replace("\\n", "\n").strip()
            tmp.write(cookies_text)
            tmp.close()
            cookiefile = tmp.name

        # ✅ yt-dlp options – note: no “format=best” this time!
        ydl_opts = {
            "quiet": True,
            "skip_download": True,
            "cookiefile": cookiefile,
            "ignoreerrors": True,
            "no_warnings": True,
            "extract_flat": False
        }

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video, download=False)

        # ✅ Step 1: Try direct master HLS URL (YouTube sometimes puts it in "requested_formats")
        master_url = None

        # Some live/regular videos store the full HLS manifest link
        if "url" in info and "playlist_type=HLS_MASTER" in info["url"]:
            master_url = info["url"]

        # ✅ Step 2: Search all formats for master playlist (playlist_type=HLS_MASTER)
        if not master_url:
            for f in info.get("formats", []):
                u = f.get("url") or ""
                if "manifest.googlevideo.com" in u and "playlist_type=HLS_MASTER" in u:
                    master_url = u
                    break

        # ✅ Step 3: Try generic m3u8 URL containing "hls_playlist" if no master found
        if not master_url:
            for f in info.get("formats", []):
                u = f.get("url") or ""
                if "m3u8" in u and "hls_playlist" in u:
                    master_url = u
                    break

        # ✅ Step 4: As last fallback, check "protocol": "m3u8_native"
        if not master_url:
            for f in info.get("formats", []):
                if (f.get("protocol") or "") == "m3u8_native":
                    master_url = f.get("url")
                    break

        if master_url:
            # Strip any overly long signatures (optional cleanup)
            master_url = re.sub(r"(&cnr=.*)$", "", master_url)

            return jsonify({
                "m3u8": master_url,
                "title": info.get("title"),
                "id": info.get("id"),
                "uploader": info.get("uploader"),
                "duration": info.get("duration"),
                "type": "auto-quality HLS master"
            })

        return jsonify({
            "error": "No auto-quality master .m3u8 found.",
            "title": info.get("title")
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/")
def home():
    return jsonify({
        "usage": "/api/m3u8?id=VIDEO_ID or ?url=YOUTUBE_URL",
        "example": "/api/m3u8?id=5qap5aO4i9A",
        "note": "Returns true auto-quality HLS master playlist (.m3u8)"
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
