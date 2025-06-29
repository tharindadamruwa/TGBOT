import os
import asyncio
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

TOKEN = "7896182510:AAHprQJ36Yuc0gqYUJeiwfT_DIZ8QqK-FRo"
user_data = {}
MAX_FILE_SIZE_MB = 2000  # Telegram document limit

def clean_filename(name):
    return "".join(c if c.isalnum() or c in " ._-" else "_" for c in name)

# âœ… Safe message editing
async def safe_edit_message(msg_obj, new_text):
    try:
        if msg_obj.text != new_text:
            await msg_obj.edit_text(new_text)
    except Exception as e:
        print(f"[EDIT ERROR] {e}")

# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ðŸ‘‹ Send a YouTube video link to download it.")

# When user sends YouTube link
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    chat_id = update.message.chat_id

    if "youtube.com" not in url and "youtu.be" not in url:
        await update.message.reply_text("âŒ Please send a valid YouTube link.")
        return

    user_data[chat_id] = {'url': url}
    await update.message.reply_text("ðŸ” Fetching video info...")

    try:
        with yt_dlp.YoutubeDL({'quiet': True, 'skip_download': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = info.get('formats', [])
            title = info.get('title', 'video')
    except Exception as e:
        await update.message.reply_text(f"âš ï¸ Error fetching info: {e}")
        print(f"[ERROR] Info fetch: {e}")
        return

    buttons = []
    seen = set()
    for f in formats:
        if f.get("vcodec") != "none" and f.get("acodec") != "none":
            size_bytes = f.get('filesize') or f.get('filesize_approx')
            size_str = f"{round(size_bytes / 1024 / 1024, 2)} MB" if size_bytes else "Unknown size"
            label = f"{f.get('format_note') or f.get('format')} - {size_str}"
            if label not in seen:
                seen.add(label)
                buttons.append([InlineKeyboardButton(label, callback_data=f"{f['format_id']}")])

    if not buttons:
        await update.message.reply_text("âš ï¸ No downloadable formats found.")
        return

    markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text(
        f"ðŸŽžï¸ *{title}*\nSelect quality:",
        parse_mode="Markdown",
        reply_markup=markup,
    )

# When user selects quality
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    format_id = query.data
    url = user_data.get(chat_id, {}).get('url')

    if not url:
        await query.edit_message_text("âŒ No URL found.")
        return

    progress_msg = await query.edit_message_text("â¬‡ï¸ Starting download...")
    filename_holder = {"name": None}

    def progress_hook(d):
        if d['status'] == 'downloading':
            percent = d.get('_percent_str', '').strip()
            speed = d.get('_speed_str', '').strip()
            eta = d.get('_eta_str', '').strip()
            msg = f"â¬‡ï¸ Downloading...\nðŸ“Š {percent} | âš¡ {speed} | â³ ETA: {eta}"
            asyncio.create_task(safe_edit_message(progress_msg, msg))
        elif d['status'] == 'finished':
            filename_holder["name"] = d['filename']

    ydl_opts = {
        'format': format_id,
        'outtmpl': 'video.%(ext)s',
        'progress_hooks': [progress_hook],
        'quiet': True,
        'noplaylist': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url)
            title = clean_filename(info.get('title', 'video'))
            filepath = filename_holder["name"]

        if not filepath or not os.path.exists(filepath):
            await safe_edit_message(progress_msg, "âŒ Download failed: File not found.")
            return

        file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
        print(f"[DEBUG] Downloaded: {filepath}, Size: {file_size_mb:.2f} MB")

        if file_size_mb > MAX_FILE_SIZE_MB:
            await safe_edit_message(progress_msg, f"âš ï¸ File too big to upload ({round(file_size_mb, 2)} MB). Telegram limit is 2 GB.")
            os.remove(filepath)
            return

        await safe_edit_message(progress_msg, "ðŸ“¤ Uploading to Telegram...")

        # â³ Tell Telegram to expect an upload (resets timeout clock)
        await context.bot.send_chat_action(chat_id=chat_id, action="upload_document")

        try:
            with open(filepath, "rb") as video:
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=video,
                    filename=title + os.path.splitext(filepath)[1],
                    caption=title,
                )
            await safe_edit_message(progress_msg, "âœ… Done!")
        except Exception as e:
            await safe_edit_message(progress_msg, f"âŒ Upload failed: {e}")
            print(f"[ERROR] Upload: {e}")

        if os.path.exists(filepath):
            os.remove(filepath)

    except Exception as e:
        await safe_edit_message(progress_msg, f"âŒ Error: {e}")
        print(f"[ERROR] General failure: {e}")
        if 'filepath' in locals() and filepath and os.path.exists(filepath):
            os.remove(filepath)

# Run bot
if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button))
    print("ðŸ¤– Bot is running...")
    app.run_polling()
