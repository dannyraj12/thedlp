# updated app.py — stronger master/auto HLS selection (returns hlsManifestUrl)
from flask import Flask, render_template, request, jsonify
import yt_dlp
import re
import logging
import os
import tempfile
import urllib.parse

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)


def extract_video_id(url):
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([^&\n?#]+)',
        r'youtube\.com\/live\/([^&\n?#]+)'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


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


def choose_master_m3u8(formats):
    """
    Heuristic to pick the master/auto m3u8 URL from yt-dlp formats list.
    Returns URL string or None.
    """
    if not formats:
        return None

    # collect candidate m3u8 urls
    candidates = []
    for f in formats:
        url = f.get("url") or ""
        if not isinstance(url, str):
            continue
        if "m3u8" in url:
            candidates.append((f, url))

    if not candidates:
        return None

    # scoring: prefer manifest/hls_playlist or manifest/hls_variant URLs (these are master playlists)
    preferred_markers = ["/manifest/hls_playlist", "/manifest/hls_variant", "hls_playlist", "hls_variant"]
    for marker in preferred_markers:
        for f, url in candidates:
            if marker in url:
                logging.info("Selected master by marker %s -> %s", marker, url)
                return url

    # prefer protocol == 'm3u8_native' (yt-dlp sets protocol)
    for f, url in candidates:
        if f.get("protocol") and "m3u8" in f.get("protocol"):
            logging.info("Selected master by protocol %s -> %s", f.get("protocol"), url)
            return url

    # prefer urls that look like a playlist (contain 'index.m3u8' but not a tiny fragment path)
    for f, url in candidates:
        parsed = urllib.parse.urlparse(url)
        path = parsed.path or ""
        if path.endswith("index.m3u8") or path.endswith(".m3u8"):
            # Small heuristic: if query params contain 'playlist' or 'manifest' it's more likely master
            qs = parsed.query or ""
            if "playlist" in qs or "manifest" in qs or "variant" in qs:
                logging.info("Selected master by path+query -> %s", url)
                return url

    # otherwise prefer candidate with shortest or longest query? pick the one with fewer 'itag' param occurrences
    def score_url(u):
        # higher score = more likely master: penalize presence of 'itag=' (these are per-itag variants)
        q = urllib.parse.urlparse(u).query
        if "itag=" in q or "format=" in q:
            return -len(q)
        # slightly prefer longer urls (likely playlist)
        return len(u)

    candidates_sorted = sorted(candidates, key=lambda tup: score_url(tup[1]), reverse=True)
    selected = candidates_sorted[0][1]
    logging.info("Selected master by fallback heuristic -> %s", selected)
    return selected


def get_master_hls(youtube_url, cookiefile_path=None):
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
    }
    if cookiefile_path:
        ydl_opts["cookiefile"] = cookiefile_path

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=False)

            if not info:
                return {"error": "Could not extract video information."}

            if not info.get("is_live"):
                return {"error": "This is not a live stream."}

            formats = info.get("formats", []) or []
            # Try to choose a master/auto m3u8
            master = choose_master_m3u8(formats)
            if master:
                return {
                    "title": info.get("title"),
                    "is_live": True,
                    "hlsManifestUrl": master
                }

            # Fallback: some extractors embed master in 'url' top-level or 'hls_url'
            # check common keys
            fallback_keys = ["hls_url", "url"]
            for key in fallback_keys:
                v = info.get(key)
                if v and isinstance(v, str) and "m3u8" in v:
                    return {"title": info.get("title"), "is_live": True, "hlsManifestUrl": v}

            return {"error": "No hlsManifestUrl found."}
    except Exception as exc:
        msg = str(exc)
        if "Sign in to confirm you" in msg or "Sign in to confirm you're not a bot" in msg:
            return {
                "error": ("yt-dlp requires authentication/cookies for this video. "
                          "Provide YouTube cookies via the COOKIES env var (Netscape cookies.txt format). "
                          "See: https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp"),
                "detail": msg
            }
        return {"error": msg}


@app.route("/api/hls")
def api_hls():
    video_id = request.args.get("id")
    if not video_id:
        return jsonify({"error": "Missing ?id="}), 400

    youtube_url = f"https://www.youtube.com/watch?v={video_id}"
    cookiefile = write_cookies_from_env()
    result = get_master_hls(youtube_url, cookiefile_path=cookiefile)

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
        "example": "/api/hls?id=5qap5aO4i9A",
        "note": "Uses yt-dlp to return the master (auto) m3u8 playlist URL."
    })


if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
