from flask import Flask, request, jsonify
import yt_dlp
import os
import json

app = Flask(__name__)

@app.route('/')
def home():
    return 'TubeM3U8Grabber is running! ✅'

@app.route('/extract', methods=['POST'])
def extract():
    data = request.get_json()
    url = data.get('url')

    if not url:
        return jsonify({'error': 'No URL provided'}), 400

    # --- Cookie handling from environment ---
    cookies_json = os.environ.get('COOKIES_JSON')  # You’ll add this in Render → Environment
    cookies_file_path = None

    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'format': 'best',
        'extract_flat': False,
    }

    try:
        if cookies_json:
            # Save cookies to temporary file for yt-dlp use
            cookies_file_path = '/tmp/cookies.json'
            with open(cookies_file_path, 'w', encoding='utf-8') as f:
                f.write(cookies_json)
            ydl_opts['cookiefile'] = cookies_file_path

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = info.get('formats', [])
            m3u8_urls = [f['url'] for f in formats if 'm3u8' in f.get('url', '')]

        return jsonify({'m3u8_urls': m3u8_urls})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

    finally:
        # cleanup cookie file
        if cookies_file_path and os.path.exists(cookies_file_path):
            os.remove(cookies_file_path)


# --- Render Port Handling ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
