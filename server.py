# pip install flask requests
from flask import Flask, request, jsonify
import os, re, tempfile, atexit, requests

app = Flask(__name__)

# ─────────────────────────────────────────────
# Load cookies from env (for restricted videos)
# ─────────────────────────────────────────────
cookiefile_path = None
cookies_env = os.getenv("COOKIES")
if cookies_env:
    cookies_text = cookies_env.replace("\\n", "\n").strip()
    tmp = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt")
    tmp.write(cookies_text)
    tmp.close()
    cookiefile_path = tmp.name
    atexit.register(lambda: os.remove(cookiefile_path) if os.path.exists(cookiefile_path) else None)

# ─────────────────────────────────────────────
# Extract auto-quality HLS manifest
# ─────────────────────────────────────────────
def extract_hls_manifest(video_id):
    url = f"https://www.youtube.com/watch?v={video_id}"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "en-US,en;q=0.9",
    }

    cookies = None
    if cookiefile_path:
        cookies = {}
        with open(cookiefile_path, "r") as f:
            for line in f:
                if not line.strip() or line.startswith("#"): continue
                parts = line.strip().split("\t")
                if len(parts) >= 7:
                    cookies[parts[5]] = parts[6]

    resp = requests.get(url, headers=headers, cookies=cookies, timeout=25)
    html = resp.text

    match = re.search(r"ytInitialPlayerResponse\s*=\s*(\{.+?\});", html)
    if not match:
        raise Exception("ytInitialPlayerResponse not found (page may be restricted or bot-checked).")

    js = match.group(1)
    hls_match = re.search(r'"hlsManifestUrl"\s*:\s*"([^"]+)"', js)
    if not hls_match:
        raise Exception("No hlsManifestUrl found (not live/DVR stream).")

    m3u8_url = hls_match.group(1).encode("utf-8").decode("unicode_escape")
    return m3u8_url


@app.route("/api/hls")
def get_hls():
    video_id = request.args.get("id")
    if not video_id:
        return jsonify({"error": "missing ?id="}), 400

    try:
        hls_url = extract_hls_manifest(video_id)
        return jsonify({
            "hlsManifestUrl": hls_url,
            "auto_quality": True,
            "cookies_used": bool(cookiefile_path)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/")
def home():
    return jsonify({
        "usage": "/api/hls?id=<YouTube_Video_ID>",
        "example": "/api/hls?id=uXNU0XgGZhs",
        "note": "✅ Auto-quality HLS manifest (up to 1080p). Uses cookies from env if provided."
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
