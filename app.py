from flask import Flask, request, jsonify
import yt_dlp
import os
import tempfile
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)


def write_cookies_from_env():
    """
    Read COOKIES env var (Netscape cookies.txt content),
    write to a temporary file, and return its path.
    """
    cookies_env = os.getenv("COOKIES")
    if not cookies_env:
        return None
    fd, path = tempfile.mkstemp(prefix="yt_cookies_", suffix=".txt")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        f.write(cookies_env)
    logging.info(f"🍪 Cookies written to temp file: {path}")
    return path


def get_streams(video_id, cookiefile=None):
    """
    Extract master (auto) and all quality HLS URLs using yt_dlp.
    """
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

                # Detect master playlist
                if "hls_variant" in url or "/manifest/hls_variant" in url:
                    master = url

                # Collect resolution-based playlists
                elif "hls_playlist" in url:
                    qualities.append({
                        "resolution": f.get("resolution")
                            or f"{f.get('width','?')}x{f.get('height','?')}",
                        "fps": f.get("fps"),
                        "url": url
                    })

            if not master:
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
                "error": ("YouTube requires authentication for this stream. "
                          "Provide cookies in COOKIES env var (Netscape cookies.txt format)."),
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

    # cleanup
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
        "note": ("Uses yt_dlp to return both Auto (hls_variant) and per-quality (hls_playlist) links. "
                 "Supports COOKIES env var in Netscape cookies.txt format for restricted videos.")
    })


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
