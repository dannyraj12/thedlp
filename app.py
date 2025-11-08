from flask import Flask, request, jsonify
import yt_dlp
import os

app = Flask(__name__)

@app.route('/')
def home():
    return (
        "TubeM3U8Grabber is running! ✅<br><br>"
        "Usage (GET): <code>/extract?url=https://youtube.com/watch?v=YOUR_ID</code><br>"
        "or POST JSON: {\"url\":\"https://youtube.com/watch?v=YOUR_ID\"}"
    )


@app.route('/extract', methods=['GET', 'POST'])
def extract():
    # ---- handle GET & POST ----
    if request.method == "GET":
        url = request.args.get("url")
    else:
        data = request.get_json(silent=True)
        url = data.get("url") if data else None

    if not url:
        return jsonify({"error": "No URL provided"}), 400

    # ---- cookie setup ----
    cookies_env = os.environ.get("COOKIES_JSON")  # holds Netscape text
    cookie_path = None

    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "format": "best",
        "noprogress": True,
    }

    try:
        if cookies_env:
            # write Netscape cookie text correctly
            cookie_path = "/tmp/cookies.txt"
            with open(cookie_path, "w", encoding="utf-8") as f:
                f.write(cookies_env.strip() + "\n")
            ydl_opts["cookiefile"] = cookie_path

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            fmts = info.get("formats", [])
            m3u8_urls = [f["url"] for f in fmts if "m3u8" in f.get("url", "")]

        return jsonify({
            "video_title": info.get("title"),
            "m3u8_urls": m3u8_urls,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    finally:
        if cookie_path and os.path.exists(cookie_path):
            os.remove(cookie_path)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
