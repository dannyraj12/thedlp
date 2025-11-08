from flask import Flask, request, jsonify
import yt_dlp
import os
import tempfile
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

def write_cookies_from_env():
    cookies_env = os.getenv("COOKIES")
    if not cookies_env:
        return None
    fd, path = tempfile.mkstemp(prefix="yt_cookies_", suffix=".txt")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        f.write(cookies_env)
    logging.info(f"Cookies written to {path}")
    return path

def get_streams(video_id, cookiefile=None):
    """Return both master (auto) and all quality playlists."""
    youtube_url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
    }
    if cookiefile:
        ydl_opts["cookiefile"] = cookiefile

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=False)
            if not info:
                return {"error": "Could not extract video information."}
            if not info.get("is_live"):
                return {"error": "This is not a live stream."}

            formats = info.get("formats", [])
            master = None
            qualities = []

            for f in formats:
                url = f.get("url", "")
                if not url or "m3u8" not in url:
                    continue

                # Detect master (auto)
                if "hls_variant" in url or "/manifest/hls_variant" in url:
                    master = url

                # Collect individual qualities
                elif "hls_playlist" in url:
                    qualities.append({
                        "resolution": f.get("resolution") or f"{f.get('width','?')}x{f.get('height','?')}",
                        "fps": f.get("fps"),
                        "url": url
                    })

            if not master:
                # fallback: choose any hls_variant if exists, else none
                for f in formats:
                    url = f.get("url", "")
                    if "hls" in url:
                        master = url
                        break

            if not master:
                return {"error": "No hlsManifestUrl found."}

            return {
                "title": info.get("title"),
                "channel": info.get("uploader"),
                "is_live": True,
                "hlsManifestUrl": master,
                "qualities": qualities
            }

    except Exception as e:
        msg = str(e)
        if "Sign in to confirm" in msg:
            return {
                "error": "This stream requires login. Provide Netscape-format cookies in COOKIES env var.",
                "detail": msg
            }
        return {"error": msg}

@app.route("/api/hls")
def api_hls():
    video_id = request.args.get("id")
    if not video_id:
        return jsonify({"error": "Missing ?id="}), 400

    cookiefile = write_cookies_from_env()
    result = get_streams(video_id, cookiefile=cookiefile)

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
        "example": "/api/hls?id=fO9e9jnhYK8",
        "note": "Returns both Auto Quality (master hls_variant) and all available quality m3u8s."
    })

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
