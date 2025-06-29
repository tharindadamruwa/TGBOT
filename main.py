import os
import asyncio
import logging
from yt_dlp import YoutubeDL
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
import humanize

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise RuntimeError("TOKEN environment variable not set")

# In-memory storage to map user to current download info
user_data = {}

# Helper function to format progress bar and info
def progress_bar(percentage, length=20):
    filled_len = int(length * percentage // 100)
    bar = "█" * filled_len + "—" * (length - filled_len)
    return f"[{bar}] {percentage:.1f}%"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send me a YouTube video link and I'll help you download it!")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not ("youtube.com/watch" in text or "youtu.be/" in text):
        await update.message.reply_text("Please send a valid YouTube video link.")
        return

    msg = await update.message.reply_text("Fetching video info...")

    # Get video info & qualities using yt-dlp
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(text, download=False)
    except Exception as e:
        await msg.edit_text(f"Failed to extract info: {e}")
        return

    # Filter only video formats with height and filesize
    formats = [
        f
        for f in info.get("formats", [])
        if f.get("vcodec") != "none" and f.get("acodec") != "none" and f.get("filesize") and f.get("height")
    ]

    if not formats:
        await msg.edit_text("No downloadable video formats found.")
        return

    # Prepare quality buttons - unique by height + fps + format id
    qualities = {}
    buttons = []
    for f in formats:
        label = f"{f['height']}p"
        if f.get("fps"):
            label += f" {f['fps']}fps"
        label += f" ({humanize.naturalsize(f['filesize'], binary=True)})"
        qualities[label] = f["format_id"]

    # Deduplicate buttons by label keeping highest filesize
    filtered = {}
    for label, fid in qualities.items():
        # keep latest only
        filtered[label] = fid

    # Create inline buttons
    for label, fid in filtered.items():
        buttons.append([InlineKeyboardButton(label, callback_data=f"dl:{fid}")])

    user_data[update.effective_user.id] = {
        "url": text,
        "title": info.get("title", "video"),
        "formats": {v: k for k, v in filtered.items()},  # format_id -> label
        "message": msg,
    }

    await msg.edit_text(
        f"Select quality for:\n*{info.get('title','')}*",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown",
    )


async def download_progress_hook(update, context, user_id, progress_message, d):
    # d is yt-dlp progress dict
    status = d.get("status")
    if status == "downloading":
        total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate") or 1
        downloaded_bytes = d.get("downloaded_bytes") or 0
        percent = downloaded_bytes / total_bytes * 100
        speed = d.get("speed") or 0
        eta = d.get("eta") or 0

        bar = progress_bar(percent)
        speed_str = humanize.naturalsize(speed, binary=True) + "/s" if speed else "N/A"
        eta_str = f"{int(eta)}s" if eta else "N/A"
        text = (
            f"Downloading:\n{bar}\n"
            f"Downloaded: {humanize.naturalsize(downloaded_bytes, binary=True)} / {humanize.naturalsize(total_bytes, binary=True)}\n"
            f"Speed: {speed_str} | ETA: {eta_str}"
        )

        try:
            # Edit progress message every 1 second approx
            # Use asyncio.ensure_future to not block
            await progress_message.edit_text(text)
        except Exception:
            pass  # ignore edit failures

    elif status == "finished":
        await progress_message.edit_text("Download finished, sending file...")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    if user_id not in user_data:
        await query.edit_message_text("Session expired. Please send the YouTube link again.")
        return

    format_id = query.data.split(":")[1]
    data = user_data[user_id]
    url = data["url"]
    title = data["title"]
    format_label = data["formats"].get(format_id, "unknown quality")

    # Send a message for progress updates
    progress_message = await query.edit_message_text(
        f"Starting download of *{title}* in quality: *{format_label}* ...",
        parse_mode="Markdown",
    )

    # yt-dlp download options
    ydl_opts = {
        "format": format_id,
        "outtmpl": f"{title}.%(ext)s",
        "quiet": True,
        "progress_hooks": [lambda d: asyncio.create_task(download_progress_hook(update, context, user_id, progress_message, d))],
        "no_warnings": True,
    }

    try:
        # Run download in thread to not block event loop
        loop = asyncio.get_event_loop()
        with YoutubeDL(ydl_opts) as ydl:
            info_dict = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=True))
            filename = ydl.prepare_filename(info_dict)

        await progress_message.edit_text("Uploading video to Telegram...")

        # Send video as document
        async with context.bot:
            await context.bot.send_document(
                chat_id=user_id,
                document=open(filename, "rb"),
                filename=f"{title}.mp4",
                caption=title,
            )

        await progress_message.delete()
        os.remove(filename)
        del user_data[user_id]

    except Exception as e:
        await progress_message.edit_text(f"Error during download/upload:\n{e}")


async def main():
    application = (
        ApplicationBuilder()
        .token(TOKEN)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_handler, pattern=r"^dl:"))

    print("Bot started...")
    await application.run_polling()


if __name__ == "__main__":
    asyncio.run(main())
