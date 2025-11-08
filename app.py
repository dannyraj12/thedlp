from flask import Flask, request, jsonify
import yt_dlp
import os

app = Flask(__name__)

@app.route('/')
def home():
    return (
        "TubeM3U8Grabber is running! ✅<br><br>"
        "Usage:<br>"
        "<code>/extract?url=https://youtube.com/watch?v=YOUR_ID</code><br><br>"
        "Supports both browser (GET) and POST JSON requests."
    )

@app.route('/extract', methods=['GET', 'POST'])
def extract():
    # --- Handle GET or POST ---
    if request.method == 'GET':
        url = request.args.get('url')
    else:
        data = request.get_json(silent=True)
        url = data.get('url') if data else None

    if not url:
        return jsonify({'error': 'No URL provided'}), 400

    # --- Load cookies from Render env (Netscape format) ---
    cookies_env = os.environ.get('COOKIES')
    cookie_path = None

    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'format': 'best',
        'noprogress': True,
    }

    try:
        if cookies_env:
            cookie_path = '/tmp/cookies.txt'
            with open(cookie_path, 'w', encoding='utf-8') as f:
                f.write(cookies_env.strip() + "\n")
            ydl_opts['cookiefile'] = cookie_path

        # --- Extract video info ---
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            fmts = info.get('formats', [])

            # ---- Detect master/auto m3u8 ----
            master_m3u8 = None
            for f in fmts:
                url_ = f.get('url', '')
                if 'index.m3u8' in url_ or 'playlist.m3u8' in url_:
                    master_m3u8 = url_
                    break

            # fallback (if master not found)
            if not master_m3u8:
                for f in fmts:
                    if 'm3u8' in f.get('url', ''):
                        master_m3u8 = f['url']
                        break

            # ---- Collect all .m3u8 urls ----
            all_m3u8s = [f['url'] for f in fmts if 'm3u8' in f.get('url', '')]

        return jsonify({
            'video_title': info.get('title'),
            'm3u8_auto': master_m3u8 or 'Not found',
            'm3u8_all': all_m3u8s
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

    finally:
        if cookie_path and os.path.exists(cookie_path):
            os.remove(cookie_path)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
