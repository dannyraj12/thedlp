# pip install flask yt-dlp
from flask import Flask, request, jsonify
from yt_dlp import YoutubeDL
import os, tempfile, atexit

app = Flask(__name__)

# If COOKIES env var exists, write it to a temporary cookies file (Netscape cookies.txt format)
cookiefile_path = None
cookies_env = os.getenv("COOKIES")
if cookies_env:
    # Render sometimes stores newlines as "\n" — convert them back
    cookies_text = cookies_env.replace("\\n", "\n").strip()
    # Create a persistent temp file path so yt-dlp can read it across requests
    tmp = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt")
    tmp.write(cookies_text)
    tmp.close()
    cookiefile_path = tmp.name

    # Ensure we remove it on process exit
    def _cleanup():
        try:
            os.unlink(cookiefile_path)
        except Exception:
            pass
    atexit.register(_cleanup)

@app.route("/api/hls")
def get_hls():
    """
    Usage: /api/hls?id=<YouTube_ID>
    Expects COOKIES env var (optional but required for some videos).
    COOKIES must contain the cookies.txt (Netscape) format content.
    """
    video_id = request.args.get("id")
    if not video_id:
        return jsonify({"error": "missing ?id="}), 400

    url = f"https://www.youtube.com/watch?v={video_id}"

    # yt-dlp options
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        # Prefer native extractor behavior (no automatic console spamming)
        "no_warnings": True,
    }

    if cookiefile_path:
        ydl_opts["cookiefile"] = cookiefile_path

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = info.get("formats", []) or []
            # find an HLS variant (protocol contains "m3u8")
            for f in formats:
                if "m3u8" in (f.get("protocol") or ""):
                    return jsonify({
                        "hlsManifestUrl": f["url"],
                        "title": info.get("title"),
                        "uploader": info.get("uploader")
                    })
            # none found
            return jsonify({"error": "no m3u8 found (not live/DVR or yt-dlp couldn't parse)"}), 404

    except Exception as e:
        # yt-dlp often embeds rich messages in Exception text — forward it
        msg = str(e)

        # If it's a cookies/auth prompt, add actionable hints
        if "Sign in to confirm you're not a bot" in msg or "Use --cookies-from-browser" in msg:
            hint = (
                "yt-dlp needs YouTube cookies to bypass the 'not a bot' check. "
                "Set COOKIES env var with your cookies.txt content (Netscape format). "
                "See https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp "
                "or export cookies using browser extensions (cookies.txt) and paste into Render as COOKIES."
            )
            return jsonify({"error": msg, "hint": hint}), 403

        return jsonify({"error": msg}), 500

@app.route("/")
def home():
    return jsonify({
        "usage": "/api/hls?id=<YouTube_Video_ID>",
        "example": "/api/hls?id=uXNU0XgGZhs",
        "note": "Set COOKIES env var to cookies.txt content if you get a bot/sign-in prompt."
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
