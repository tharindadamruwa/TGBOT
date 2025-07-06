import os
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

TOKEN = TOKEN = os.getenv("BOT_TOKEN")
user_data = {}  # user_id -> dict with url & formats

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send me a YouTube link to get started!")

def get_formats(url):
    ydl_opts = {}
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
        await update.message.reply_text("Failed to fetch video formats.")
        return

    keyboard = []
    buttons = []
    for f in formats:
        label = f"{f.get('format_note', '')} - {round(f.get('filesize', 0)/1024/1024, 1)} MB"
        if label.strip() == "- 0.0 MB":
            continue
        buttons.append(InlineKeyboardButton(label, callback_data=str(f['format_id'])))
        if len(buttons) == 2:
            keyboard.append(buttons)
            buttons = []
    if buttons:
        keyboard.append(buttons)

    user_data[user_id] = {'url': url, 'formats': formats, 'title': title}

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(f"Choose quality for: *{title}*", reply_markup=reply_markup, parse_mode='Markdown')

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    format_id = query.data
    data = user_data.get(user_id)
    if not data:
        await query.edit_message_text("Session expired. Please send the URL again.")
        return

    url = data['url']
    title = data['title']
    formats = data['formats']

    output_file = f"{title}.mp4".replace(" ", "_").replace("/", "_")

    await query.edit_message_text("Downloading video...")

    ydl_opts = {
        'format': format_id,
        'outtmpl': output_file,
        'quiet': True,
        'noplaylist': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        await query.edit_message_text("Download failed.")
        return

    await context.bot.send_document(
        chat_id=query.message.chat_id,
        document=open(output_file, 'rb'),
        filename=output_file
    )
    os.remove(output_file)

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
app.add_handler(CallbackQueryHandler(button))

if __name__ == '__main__':
    import asyncio
    asyncio.run(app.run_polling())
