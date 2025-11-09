from flask import Flask, render_template, request, jsonify
import yt_dlp
import re
import logging
import tempfile
import os

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


def get_m3u8_links(youtube_url):
    try:
        # ✅ Improved yt_dlp options for more reliable live stream extraction
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'noplaylist': True,
            'geo_bypass': True,
            'source_address': '0.0.0.0',
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                'Accept-Language': 'en-US,en;q=0.9',
                'Referer': 'https://www.youtube.com/',
                'Origin': 'https://www.youtube.com',
            },
            'extractor_args': {
                'youtube': {
                    'player_skip': ['webpage'],
                    'player_client': ['android', 'tv', 'ios'],  # tries multiple client types
                }
            },
        }

        # ✅ Auto-load Netscape cookies from env variable COOKIES if available
        cookies_env = os.getenv("COOKIES")
        if cookies_env:
            temp_cookie_path = tempfile.NamedTemporaryFile(delete=False, suffix=".txt").name
            with open(temp_cookie_path, "w", encoding="utf-8") as f:
                f.write(cookies_env)
            ydl_opts["cookiefile"] = temp_cookie_path

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=False)

            # 🔁 Fallback: retry with iOS client if nothing extracted
            if not info or 'formats' not in info or not info.get('formats'):
                logging.warning("Retrying with iOS player client...")
                ydl_opts['extractor_args']['youtube']['player_client'] = ['ios']
                with yt_dlp.YoutubeDL(ydl_opts) as ydl2:
                    info = ydl2.extract_info(youtube_url, download=False)

            if not info:
                return {'error': 'Could not extract video information. Please check the URL and try again.'}
            
            is_live = info.get('is_live', False)
            was_live = info.get('was_live', False)
            
            if was_live and not is_live:
                return {'error': 'This stream has ended. M3U8 links are only available for currently live streams.'}
            
            if not is_live and not was_live:
                live_status = info.get('live_status', '')
                if live_status == 'is_upcoming':
                    return {'error': 'This stream has not started yet. M3U8 links will be available once the stream goes live.'}
                elif live_status == 'not_live':
                    return {'error': 'This is not a live stream. This tool only works with YouTube live streams.'}
            
            logging.info(f"Processing video: {info.get('title')} - Live: {is_live}")
            logging.info(f"Total formats available: {len(info.get('formats', []))}")
            
            m3u8_formats = []
            
            for fmt in info.get('formats', []):
                url = fmt.get('url', '')
                protocol = fmt.get('protocol', '')
                
                if protocol == 'm3u8_native' or protocol == 'm3u8' or '.m3u8' in url:
                    vcodec = fmt.get('vcodec', 'none')
                    acodec = fmt.get('acodec', 'none')
                    
                    is_audio_only = vcodec == 'none' and acodec != 'none'
                    
                    quality = fmt.get('format_note', 'unknown')
                    resolution = fmt.get('resolution', 'N/A')
                    fps = fmt.get('fps', 'N/A')
                    format_id = fmt.get('format_id', '')
                    tbr = fmt.get('tbr', 0)
                    height = fmt.get('height', 0)
                    width = fmt.get('width', 0)
                    
                    m3u8_formats.append({
                        'url': url,
                        'quality': quality,
                        'resolution': resolution,
                        'fps': fps,
                        'format_id': format_id,
                        'tbr': tbr or 0,
                        'height': height or 0,
                        'width': width or 0,
                        'is_audio_only': is_audio_only
                    })
            
            logging.info(f"Found {len(m3u8_formats)} m3u8 formats")
            
            video_formats = [f for f in m3u8_formats if not f['is_audio_only']]
            
            if video_formats:
                video_formats.sort(key=lambda x: (x['height'], x['width'], x['tbr']), reverse=True)
                logging.info(f"Found {len(video_formats)} video formats (excluding audio-only)")
            
            manifest_url = info.get('manifest_url')
            best_m3u8 = None
            
            if manifest_url and '.m3u8' in manifest_url:
                best_m3u8 = manifest_url
                logging.info(f"Using manifest_url as best quality")
            elif video_formats:
                best_m3u8 = video_formats[0]['url']
                logging.info(f"Using top video format: {video_formats[0]['quality']} - {video_formats[0]['resolution']}")
            elif m3u8_formats:
                best_m3u8 = m3u8_formats[0]['url']
                logging.info(f"Using first m3u8 format (possibly audio-only)")
            else:
                logging.warning("No m3u8 formats found!")
            
            logging.info(f"Best m3u8 URL length: {len(best_m3u8) if best_m3u8 else 0}")
            
            formats_for_display = [
                {
                    'url': f['url'],
                    'quality': f['quality'] + (' (audio only)' if f['is_audio_only'] else ''),
                    'resolution': f['resolution'],
                    'fps': f['fps'],
                    'format_id': f['format_id']
                }
                for f in m3u8_formats
            ]
            
            return {
                'title': info.get('title', 'Unknown'),
                'is_live': is_live,
                'thumbnail': info.get('thumbnail', ''),
                'formats': formats_for_display,
                'auto_quality_url': best_m3u8,
                'uploader': info.get('uploader', 'Unknown')
            }
            
    except yt_dlp.utils.DownloadError as e:
        error_str = str(e)
        logging.error(f"yt-dlp DownloadError: {error_str}")
        if 'Private video' in error_str or 'members-only' in error_str:
            return {'error': 'This video is private or members-only and cannot be accessed.'}
        elif 'Video unavailable' in error_str:
            return {'error': 'This video is unavailable. It may have been removed or made private.'}
        elif 'not a live stream' in error_str.lower():
            return {'error': 'This is not a live stream. This tool only works with currently live YouTube streams.'}
        else:
            return {'error': 'Unable to extract video information. Please check the URL and try again.'}
    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}")
        return {'error': 'An unexpected error occurred. Please check the URL and try again.'}


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/extract', methods=['POST'])
def extract():
    data = request.get_json()
    youtube_url = data.get('url', '').strip()
    
    if not youtube_url:
        return jsonify({'error': 'Please provide a YouTube URL'})
    
    video_id = extract_video_id(youtube_url)
    if not video_id:
        return jsonify({'error': 'Invalid YouTube URL'})
    
    result = get_m3u8_links(youtube_url)
    return jsonify(result)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
