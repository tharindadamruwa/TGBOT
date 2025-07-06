import os
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

TOKEN = os.getenv("BOT_TOKEN")
user_data = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎬 Send a YouTube link to download!")

def get_formats(url):
    ydl_opts = {
        'cookiefile': 'cookies.txt'
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        formats = [
            f for f in info['formats']
            if f.get('vcodec') != 'none' and f.get('acodec') != 'none'
        ]
        return info['title'], formats

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    user_id = update.effective_user.id

    try:
        title, formats = get_formats(url)
    except Exception as e:
        await update.message.reply_text("❌ Failed to fetch video details.")
        return

    keyboard = []
    for f in formats:
        fmt_note = f.get("format_note") or f.get("resolution") or "?"
        size_mb = f.get("filesize", 0)
        if size_mb:
            label = f"{fmt_note} - {round(size_mb / 1024 / 1024, 1)} MB"
        else:
            label = fmt_note
        keyboard.append([InlineKeyboardButton(label, callback_data=f["format_id"])])

    user_data[user_id] = {"url": url, "formats": formats, "title": title}

    await update.message.reply_text(
        f"🎞 *{title}*\nSelect a quality to download:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = user_data.get(user_id)

    if not data:
        await query.edit_message_text("⚠️ Session expired. Send the link again.")
        return

    url = data["url"]
    format_id = query.data
    title = data["title"]
    safe_title = title.replace(" ", "_").replace("/", "_")
    filename = f"{safe_title}.mp4"

    await query.edit_message_text("⬇️ Downloading...")

    try:
        ydl_opts = {
            "format": format_id,
            "outtmpl": filename,
            "cookiefile": "cookies.txt",
            "quiet": True,
            "noplaylist": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        await query.edit_message_text("❌ Download failed.")
        return

    await context.bot.send_document(
        chat_id=query.message.chat_id,
        document=open(filename, "rb"),
        filename=filename
    )

    os.remove(filename)

# Setup app
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
app.add_handler(CallbackQueryHandler(button))

if __name__ == "__main__":
    import asyncio
    asyncio.run(app.run_polling())
