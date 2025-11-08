from flask import Flask, request, jsonify
import yt_dlp
import os
import json

app = Flask(__name__)

@app.route('/')
def home():
    return 'TubeM3U8Grssssfgabber is running! ✅<br><br>' \
           'Use:<br>' \
           '<code>/extract?url=https://youtube.com/watch?v=YOUR_ID</code>'

@app.route('/extract', methods=['GET', 'POST'])
def extract():
    # Allow both GET (browser) and POST (API)
    if request.method == 'GET':
        url = request.args.get('url')
    else:
        data = request.get_json(silent=True)
        url = data.get('url') if data else None

    if not url:
        return jsonify({'error': 'No URL provided'}), 400

    cookies_json = os.environ.get('COOKIES_JSON')
    cookies_file_path = None

    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'format': 'best',
    }

    try:
        # Load cookies from environment if available
        if cookies_json:
            cookies_file_path = '/tmp/cookies.json'
            with open(cookies_file_path, 'w', encoding='utf-8') as f:
                f.write(cookies_json)
            ydl_opts['cookiefile'] = cookies_file_path

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = info.get('formats', [])
            m3u8_urls = [f['url'] for f in formats if 'm3u8' in f.get('url', '')]

        # Return result as JSON
        return jsonify({
            'video_title': info.get('title'),
            'm3u8_urls': m3u8_urls
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

    finally:
        # Cleanup temp cookie file
        if cookies_file_path and os.path.exists(cookies_file_path):
            os.remove(cookies_file_path)

# Render will auto-assign PORT
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
