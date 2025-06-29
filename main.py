import os
import asyncio
from pytube import YouTube
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

TOKEN = os.getenv("TOKEN")
user_data = {}
MAX_MB = 2000

def clean_filename(name):
    return "".join(c if c.isalnum() or c in " ._-" else "_" for c in name)

async def safe_edit_message(msg, new_text):
    try:
        if msg.text != new_text:
            await msg.edit_text(new_text)
    except Exception as e:
        print(f"[EDIT ERROR] {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📥 Send a YouTube video link.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    chat_id = update.message.chat_id

    if "youtube.com" not in url and "youtu.be" not in url:
        await update.message.reply_text("❌ Invalid YouTube URL.")
        return

    user_data[chat_id] = {"url": url}
    await update.message.reply_text("🔍 Getting video info...")

    try:
        yt = YouTube(url)
        title = clean_filename(yt.title)
        streams = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc()
    except Exception as e:
        await update.message.reply_text(f"⚠️ Failed to fetch: {e}")
        return

    buttons = []
    for s in streams:
        mb = round(s.filesize / (1024 * 1024), 2)
        label = f"{s.resolution} - {mb} MB"
        buttons.append([InlineKeyboardButton(label, callback_data=s.itag)])

    markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text(f"🎬 *{title}*\nSelect a quality:", parse_mode="Markdown", reply_markup=markup)

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    itag = int(query.data)
    url = user_data.get(chat_id, {}).get("url")
    if not url:
        await query.edit_message_text("❌ No video URL found.")
        return

    yt = YouTube(url)
    stream = yt.streams.get_by_itag(itag)
    title = clean_filename(yt.title)
    filename = stream.default_filename or f"{title}.mp4"

    progress_msg = await query.edit_message_text("⬇️ Downloading video...")
    await asyncio.to_thread(stream.download, filename=filename)

    size_mb = os.path.getsize(filename) / (1024 * 1024)
    if size_mb > MAX_MB:
        await safe_edit_message(progress_msg, f"⚠️ File too large: {round(size_mb, 2)} MB (limit 2 GB)")
        os.remove(filename)
        return

    await safe_edit_message(progress_msg, "📤 Uploading to Telegram...")
    await context.bot.send_chat_action(chat_id=chat_id, action="upload_document")

    try:
        with open(filename, "rb") as f:
            await context.bot.send_document(chat_id=chat_id, document=f, filename=filename, caption=title)
        await safe_edit_message(progress_msg, "✅ Sent!")
    except Exception as e:
        await safe_edit_message(progress_msg, f"❌ Upload failed: {e}")
    finally:
        if os.path.exists(filename):
            os.remove(filename)

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button))
    print("🤖 Bot running with pytube...")
    app.run_polling()
