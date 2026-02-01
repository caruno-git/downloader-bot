import asyncio
import logging
import os
import sys
import json
import time
import re
from dotenv import load_dotenv
import pyrogram
from pyrogram import Client, filters, enums
from pyrogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    InputMediaVideo,
    InputMediaDocument,
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    BotCommand,
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultVideo,
    InlineQueryResultCachedVideo,
    InputTextMessageContent
)
from downloader import download_video, get_video_info, get_direct_link
from text_content import TEXTS
load_dotenv()
BYTES_IN_MB = 1024 * 1024
FILE_LIMIT = 4000 * BYTES_IN_MB # 4GB
download_queue = asyncio.Queue()
processing_urls = set() # Track actively processing URLs to prevent dupes
WORKER_COUNT = 2 # Process 2 videos continuously
USER_DATA_FILE = "user_data.json"
DOWNLOADS_DIR = "downloads"
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
if not BOT_TOKEN or not API_ID or not API_HASH:
    print("Error: BOT_TOKEN, API_ID, or API_HASH is not set in .env file.")
    sys.exit(1)
app = Client(
    "downloader_bot_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)
def load_user_data():
    if os.path.exists(USER_DATA_FILE):
        try:
            with open(USER_DATA_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}
def save_user_data(data):
    with open(USER_DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)
user_data = load_user_data()
def get_text(user_id, key, **kwargs):
    lang = user_data.get(str(user_id), "en")
    if lang not in TEXTS:
        lang = "en"
    text = TEXTS.get(lang, TEXTS["en"]).get(key, "")
    if kwargs:
        try:
            return text.format(**kwargs)
        except KeyError:
            return text # Return unformatted string if keys missing
    return text
def get_settings_keyboard():
    keys = list(TEXTS.keys())
    kb = []
    row = []
    for lang in keys:
        btn_text = TEXTS[lang].get("btn_name", lang)
        row.append(InlineKeyboardButton(btn_text, callback_data=f"set_lang_{lang}"))
        if len(row) == 3: # 3 columns looks good on mobile
            kb.append(row)
            row = []
    if row:
        kb.append(row)
    return InlineKeyboardMarkup(kb)
@app.on_message(filters.command("start"))
async def start_handler(client: Client, message: Message):
    logging.info(f"Start command received from {message.from_user.id} in {message.chat.type}")
    user_id = str(message.from_user.id)
    if user_id not in user_data:
        detected_lang = (message.from_user.language_code or "en")[:2]
        if detected_lang in TEXTS:
             user_data[user_id] = detected_lang
        else:
             user_data[user_id] = "en"
        save_user_data(user_data)
    text = get_text(user_id, "welcome", name=message.from_user.first_name)
    logging.info(f"Sending welcome text: {text}")
    try:
        await message.reply_text(text)
    except Exception as e:
        logging.error(f"Error sending start reply: {e}")
@app.on_message(filters.command("language"))
async def language_command_handler(client: Client, message: Message):
    logging.info(f"Language command received from {message.from_user.id}")
    user_id = str(message.from_user.id)
    try:
        await message.reply_text(
            get_text(user_id, "choose_language"),
            reply_markup=get_settings_keyboard()
        )
    except Exception as e:
        logging.error(f"Error sending language menu: {e}")
@app.on_callback_query(filters.regex(r"^set_lang_"))
async def language_callback(client: Client, callback_query: CallbackQuery):
    user_id = str(callback_query.from_user.id)
    lang_code = callback_query.data.split("_")[2]
    if lang_code in TEXTS:
        user_data[user_id] = lang_code
        save_user_data(user_data)
        new_text = TEXTS[lang_code].get("language_selected", "Language set!")
        await callback_query.edit_message_text(new_text)
    await callback_query.answer()
async def upload_progress(current, total, client, message, user_id, start_time):
    now = time.time()
    diff = now - start_time.get('last_update', 0)
    if diff < 3 and current != total:
        return
    start_time['last_update'] = now
    start_ts = start_time.get('start', now)
    elapsed = now - start_ts
    speed = "0 MB/s"
    if elapsed > 0:
        speed_val = (current / BYTES_IN_MB) / elapsed
        speed = f"{speed_val:.2f} MB/s"
    percent = f"{current * 100 / total:.1f}%"
    total_mb = f"{total / BYTES_IN_MB:.2f} MB"
    try:
        text = get_text(user_id, "download_progress", default="Upload: {percent}").format(
                 percent=percent,
                 total=total_mb,
                 speed=speed
             )
        await message.edit_text(text)
    except Exception as e:
        logging.error(f"Error updating progress: {e}")
@app.on_message(filters.text & ~filters.command("start"))
async def video_handler(client: Client, message: Message):
    user_id = str(message.from_user.id)
    text = message.text.strip()
    logging.info(f"Received text message: {text} from {user_id} (via_bot: {message.via_bot.id if message.via_bot else 'None'})")
    pattern = r'(https?://)?(?:[\w-]+\.)*(youtube|youtu|tiktok|instagram)\.(com|be)/.+'
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        logging.info("Regex didn't match.")
        return
    url = match.group(0)
    if not url.startswith("http"):
        url = "https://" + url
    is_inline = (message.via_bot is not None)
    is_tiktok = 'tiktok.com' in url.lower()
    if is_inline or is_tiktok:
        if url in processing_urls:
             return
        processing_urls.add(url)
        processing_msg = await message.reply_text(get_text(user_id, "processing"))
        await download_queue.put({
            'url': url,
            'message': message,
            'user_id': user_id,
            'processing_msg': processing_msg,
            'audio_only': False,
            'quality': 'best'
        })
        return
    user_data[user_id + "_pending"] = url
    analyzing_msg = await message.reply_text(get_text(user_id, "analyzing"))
    info = await asyncio.get_event_loop().run_in_executor(None, lambda: get_video_info(url))
    if not info:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(get_text(user_id, "btn_video"), callback_data="fmt_best")],
            [InlineKeyboardButton(get_text(user_id, "btn_audio"), callback_data="fmt_audio")]
        ])
        await analyzing_msg.edit_text(get_text(user_id, "select_format").replace("{title}", "Unknown").replace("{duration}", "?"), reply_markup=keyboard)
        return
    title = info.get('title', 'Video')
    duration = info.get('duration', 0)
    minutes = duration // 60
    seconds = duration % 60
    dur_str = f"{minutes} min {seconds} sec"
    caption = get_text(user_id, "select_format").format(title=title, duration=dur_str)
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(get_text(user_id, "btn_video"), callback_data="fmt_best"),
            InlineKeyboardButton(get_text(user_id, "btn_audio"), callback_data="fmt_audio")
        ]
    ])
    try:
        thumb = info.get('thumbnail')
        if thumb and thumb.startswith('http'):
             await message.reply_photo(
                 photo=thumb,
                 caption=caption,
                 reply_markup=keyboard,
                 reply_to_message_id=message.id
             )
             await analyzing_msg.delete()
        else:
             await analyzing_msg.edit_text(caption, reply_markup=keyboard)
    except Exception as e:
        logging.error(f"Error sending rich menu: {e}")
        await analyzing_msg.edit_text(caption, reply_markup=keyboard)
@app.on_callback_query(filters.regex(r"^fmt_"))
async def format_callback(client: Client, callback_query: CallbackQuery):
    user_id = str(callback_query.from_user.id)
    choice = callback_query.data.split("_")[1] # low, medium, high, audio, best
    url = user_data.get(user_id + "_pending")
    if not url:
        await callback_query.answer("Link expired.", show_alert=True)
        try: await callback_query.message.delete()
        except: pass
        return
    del user_data[user_id + "_pending"]
    if url in processing_urls:
         await callback_query.answer("Already processing!", show_alert=True)
         return
    await callback_query.answer("Queued!")
    processing_urls.add(url)
    try:
        await callback_query.message.delete()
    except:
        pass
    processing_msg = await callback_query.message.reply_text(get_text(user_id, "processing"))
    audio_only = (choice == "audio")
    quality = choice if choice in ['low', 'medium', 'high'] else 'best'
    await download_queue.put({
        'url': url,
        'message': callback_query.message.reply_to_message or callback_query.message, # Use original link message
        'user_id': user_id,
        'processing_msg': processing_msg,
        'audio_only': audio_only,
        'quality': quality
    })
async def download_progress_hook(d, client, message, user_id, start_time):
    if d['status'] == 'downloading':
        try:
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            current = d.get('downloaded_bytes', 0)
            now = time.time()
            diff = now - start_time.get('last_update', 0)
            if diff < 3 and current != total:
                return
            start_time['last_update'] = now
            speed_val = d.get('speed', 0)
            speed = "0 MB/s"
            if speed_val:
                speed = f"{speed_val / BYTES_IN_MB:.2f} MB/s"
            percent = d.get('_percent_str', '0%').strip()
            total_mb = f"{total / BYTES_IN_MB:.2f} MB"
            text = get_text(user_id, "download_progress", default="DL: {percent}").format(
                     percent=percent,
                     total=total_mb,
                     speed=speed
                 )
            await message.edit_text(text)
        except Exception as e:
            pass
async def worker():
    logging.info("Worker started")
    while True:
        try:
            item = await download_queue.get()
            url = item['url']
            message = item['message']
            user_id = item['user_id']
            processing_msg = item['processing_msg']
            audio_only = item.get('audio_only', False)
            quality = item.get('quality', 'best')
            start_time = {'start': time.time(), 'last_update': 0}
            try:
                video_info = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: download_video(url, progress_hook=lambda d: asyncio.run_coroutine_threadsafe(download_progress_hook(d, app, processing_msg, user_id, start_time), loop), max_size_bytes=FILE_LIMIT, audio_only=audio_only, quality=quality)
                )
                if video_info:
                    if 'error' in video_info:
                        error = video_info['error']
                        if error == 'file_too_large':
                             size = video_info['size']
                             await processing_msg.edit_text(get_text(user_id, "video_too_large", size=size / BYTES_IN_MB))
                        elif error == 'is_live':
                             await processing_msg.edit_text(get_text(user_id, "error_live"))
                        elif error == 'exception':
                             details = video_info.get('details', '')
                             if 'sign in to confirm your age' in details.lower() or 'age restricted' in details.lower():
                                 await processing_msg.edit_text(get_text(user_id, "error_age"))
                             else:
                                 error_text = f"{get_text(user_id, 'error')}\n\nTechnical Details: {details}"
                                 await processing_msg.edit_text(error_text)
                        else:
                             await processing_msg.edit_text(get_text(user_id, "download_failed"))
                    else:
                        if video_info.get('type') == 'album':
                            files = video_info.get('files', [])
                            title = video_info.get('title', 'Slideshow')
                            author = video_info.get('author', 'Unknown')
                            if files:
                                caption = f"{title}\n\n👤 Author: {author}"
                                from pyrogram.types import InputMediaPhoto
                                chunks = [files[i:i + 10] for i in range(0, len(files), 10)]
                                for i, chunk in enumerate(chunks):
                                    media_group = []
                                    for j, file_path in enumerate(chunk):
                                        cap = caption if (i == 0 and j == 0) else ""
                                        media_group.append(InputMediaPhoto(file_path, caption=cap))
                                    await app.send_media_group(
                                        chat_id=message.chat.id,
                                        media=media_group,
                                        reply_to_message_id=message.id
                                    )
                                    if len(chunks) > 1:
                                        await asyncio.sleep(1)
                                for f in files:
                                    if os.path.exists(f):
                                        os.remove(f)
                                await processing_msg.delete()
                        elif video_info.get('path'):
                            file_path = video_info['path']
                            title = video_info.get('title', 'Video')
                            author = video_info.get('author', 'Unknown')
                            resolution = video_info.get('resolution', '?')
                            thumbnail_path = video_info.get('thumbnail')
                            caption = f"{title}\n\n👤 Author: {author}\n📺 Quality: {resolution}"
                            if os.path.exists(file_path):
                                start_time = {'last_update': 0, 'start': time.time()}
                                ext = os.path.splitext(file_path)[1].lower()
                                if ext in ['.jpg', '.jpeg', '.png', '.webp']:
                                    await app.send_photo(
                                        chat_id=message.chat.id,
                                        photo=file_path,
                                        caption=caption,
                                        reply_to_message_id=None,
                                        progress=upload_progress,
                                        progress_args=(app, processing_msg, user_id, start_time)
                                    )
                                elif audio_only or ext in ['.mp3', '.m4a', '.opus', '.flac']:
                                    await app.send_audio(
                                        chat_id=message.chat.id,
                                        audio=file_path,
                                        caption=caption,
                                        title=title,
                                        performer=author,
                                        reply_to_message_id=None,
                                        progress=upload_progress,
                                        progress_args=(app, processing_msg, user_id, start_time)
                                    )
                                else:
                                    await app.send_video(
                                        chat_id=message.chat.id,
                                        video=file_path,
                                        caption=caption,
                                        reply_to_message_id=None, # Don't reply, so we can delete the original safely without orphans? Or just reply.
                                        thumb=thumbnail_path if thumbnail_path and os.path.exists(thumbnail_path) else None,
                                        supports_streaming=True,
                                        progress=upload_progress,
                                        progress_args=(app, processing_msg, user_id, start_time)
                                    )
                                if os.path.exists(file_path):
                                    os.remove(file_path)
                                if thumbnail_path and os.path.exists(thumbnail_path):
                                    os.remove(thumbnail_path)
                                await processing_msg.delete()
                                try:
                                    await message.delete()
                                except:
                                    pass
                        else:
                            await processing_msg.edit_text(get_text(user_id, "download_failed"))
            except Exception as e:
                 logging.error(f"Worker logic failed: {e}")
            finally:
                if url in processing_urls:
                    processing_urls.remove(url)
                download_queue.task_done()
        except Exception as e:
             logging.error(f"Worker loop failed: {e}")
             await asyncio.sleep(1)
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    if os.path.exists(DOWNLOADS_DIR):
        try:
            for f in os.listdir(DOWNLOADS_DIR):
                path = os.path.join(DOWNLOADS_DIR, f)
                try:
                    if os.path.isfile(path):
                        os.remove(path)
                except Exception as e:
                    logging.error(f"Error deleting old file {path}: {e}")
        except Exception as e:
            logging.error(f"Error cleaning downloads dir: {e}")
    loop = asyncio.get_event_loop()
    for _ in range(WORKER_COUNT):
        loop.create_task(worker())
    app.start()
    try:
        from pyrogram.types import BotCommand
        app.set_bot_commands([
            BotCommand("start", "Start bot / Запустить бота"),
            BotCommand("language", "Change Language / Сменить язык")
        ])
        logging.info("Commands set successfully")
    except Exception as e:
        logging.error(f"Error setting commands: {e}")
    logging.info("Bot started.")
    pyrogram.idle()
    app.stop()