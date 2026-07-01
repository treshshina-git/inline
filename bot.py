import logging
import os

from lyricsgenius import Genius
from telegram import Update
from telegram.ext import Application, InlineQueryHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.DEBUG)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GENIUS_TOKEN = os.getenv("GENIUS_TOKEN")

genius = Genius(GENIUS_TOKEN, skip_non_songs=True, remove_section_headers=True)
song_cache = {}

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query.strip()
    if not query:
        return

    try:
        results = []
        search = genius.search_songs(query, per_page=6)

        for hit in search.get("hits", [])[:6]:
            song = hit["result"]
            song_id = song["id"]
            full_title = f"{song['title']} — {song['primary_artist']['name']}"

            song_cache[song_id] = full_title  # сохраняем только название

            results.append(
                InlineQueryResultArticle(
                    id=str(song_id),
                    title=full_title,
                    description="Получить текст",
                    input_message_content=InputTextMessageContent(full_title),
                )
            )

        await update.inline_query.answer(results, cache_time=60, is_personal=True)
    except Exception as e:
        logger.error(f"Inline error: {e}")


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ловим сообщение, которое пришло после выбора inline"""
    message = update.message
    if not message.via_bot or message.via_bot.username != context.bot.username:
        return

    text = message.text.strip()
    logger.info(f"Caught inline message: {text}")

    # Простой поиск по названию (можно улучшить)
    try:
        search = genius.search_songs(text, per_page=1)
        if search.get("hits"):
            song = search["hits"][0]["result"]
            song_obj = genius.song(song["id"])
            full_title = f"{song_obj.title} — {song_obj.primary_artist.name}"
            lyrics = song_obj.lyrics or "Текст не найден."

            await message.reply_text(f"🎵 <b>{full_title}</b>\n\n{lyrics}", parse_mode=ParseMode.HTML)
            logger.info("Lyrics sent successfully")
    except Exception as e:
        logger.error(f"Message handler error: {e}")
        await message.reply_text("Не удалось найти текст песни.")


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(InlineQueryHandler(inline_query))
    app.add_handler(MessageHandler(filters.VIA_BOT, message_handler))  # Главный фикс

    logger.info("Bot started with VIA_BOT handler")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
