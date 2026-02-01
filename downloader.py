import yt_dlp
import os
def download_video(url: str, output_path: str = "downloads", progress_hook=None, max_size_bytes: int = None, audio_only: bool = False, quality: str = "best") -> dict:
    if not os.path.exists(output_path):
        os.makedirs(output_path)
    if 'tiktok.com' in url and not audio_only:
         pass
    if 'tiktok.com' in url:
        ydl_opts = {
            'outtmpl': f'{output_path}/%(title)s.%(ext)s',
            'noplaylist': True,
            'writethumbnail': True,
            'progress_hooks': [progress_hook] if progress_hook else [],
        }
        print("DEBUG: Falling back to yt-dlp for TikTok")
        url = url.replace('/photo/', '/video/')
        if '?' in url:
             url = url.split('?')[0]
        ydl_opts['format'] = 'best'
    else:
        ydl_opts = {
            'outtmpl': f'{output_path}/%(title)s.%(ext)s',
            'noplaylist': True,
            'writethumbnail': True,
            'progress_hooks': [progress_hook] if progress_hook else [],
        }
        if audio_only:
             ydl_opts['format'] = 'bestaudio/best'
             ydl_opts['postprocessors'] = [{
                 'key': 'FFmpegExtractAudio',
                 'preferredcodec': 'opus',
                 'preferredquality': '192',
             }]
        else:
             ydl_opts['format'] = 'bestvideo[height<=1440][fps<=60]+bestaudio/best[height<=1440][fps<=60]/best'
             ydl_opts['merge_output_format'] = 'mp4'
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            if max_size_bytes:
                info = ydl.extract_info(url, download=False)
                if info.get('is_live'):
                    return {'error': 'is_live'}
                filesize = info.get('filesize') or info.get('filesize_approx')
                if filesize and filesize > max_size_bytes:
                    return {'error': 'file_too_large', 'size': filesize}
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            thumbnail_path = None
            base_filename = os.path.splitext(filename)[0]
            for ext in ['jpg', 'jpeg', 'png', 'webp']:
                possible_thumb = f"{base_filename}.{ext}"
                if os.path.exists(possible_thumb):
                    thumbnail_path = possible_thumb
                    break
            return {
                'path': filename,
                'title': info.get('title', 'Video'),
                'author': info.get('uploader') or info.get('uploader_id') or 'Unknown',
                'resolution': info.get('resolution') or f"{info.get('height', '?')}p",
                'thumbnail': thumbnail_path
            }
    except Exception as e:
        print(f"Error downloading video: {e}")
        return {'error': 'exception', 'details': str(e)}
def get_video_info(url: str) -> dict:
    ydl_opts = {
        'extract_flat': True, # Don't download
        'quiet': True,
        'no_warnings': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                'title': info.get('title', 'Video'),
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail', None),
                'author': info.get('uploader', 'Unknown'),
                'is_live': info.get('is_live', False)
            }
    except Exception as e:
        print(f"Metadata Error: {e}")
        return None
import logging
def get_direct_link(url: str) -> dict:
    logging.info(f"get_direct_link called for: {url}")
    try:
        ydl_opts = {
            'format': 'best[ext=mp4]/best',
            'quiet': True,
            'no_warnings': True,
            'extract_flat': 'in_playlist', # Extract full info for single video, flat for playlist
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            video_url = info.get('url')
            if not video_url and 'formats' in info:
                 video_url = info['formats'][-1].get('url')
            if not video_url:
                logging.warning(f"No URL found for {url}")
                return None
            logging.info(f"Direct link found: {video_url[:50]}...")
            return {
                'url': video_url,
                'title': info.get('title', 'Video'),
                'thumbnail': info.get('thumbnail'),
                'duration': info.get('duration')
            }
    except Exception as e:
        logging.error(f"Direct Link Error: {e}")
        return None