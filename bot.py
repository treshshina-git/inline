import logging
import os

from lyricsgenius import Genius
from telegram import InlineQueryResultArticle, InputTextMessageContent, Update
from telegram.constants import ParseMode
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

            song_cache[song_id] = full_title

            results.append(
                InlineQueryResultArticle(
                    id=str(song_id),
                    title=full_title,
                    description="Получить текст",
                    input_message_content=InputTextMessageContent(full_title),
                )
            )

        await update.inline_query.answer(results, cache_time=60, is_personal=True)
        logger.info(f"Answered for: {query}")

    except Exception as e:
        logger.error(f"Inline error: {e}")


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message.via_bot or message.via_bot.username != context.bot.username:
        return

    text = message.text.strip()
    logger.info(f"Caught selection: {text}")

    try:
        # Ищем заново по названию
        search = genius.search_songs(text, per_page=1)
        if search.get("hits"):
            song_data = search["hits"][0]["result"]
            song_id = song_data["id"]
            
            song_obj = genius.song(song_id)
            
            # Безопасное получение данных
            title = song_obj.title if hasattr(song_obj, 'title') else song_data.get("title", "Unknown")
            artist = song_obj.primary_artist.name if hasattr(song_obj.primary_artist, 'name') else song_data.get("primary_artist", {}).get("name", "Unknown")
            full_title = f"{title} — {artist}"
            lyrics = song_obj.lyrics if hasattr(song_obj, 'lyrics') else "Текст не найден."

            await message.reply_text(
                f"🎵 <b>{full_title}</b>\n\n{lyrics}",
                parse_mode=ParseMode.HTML
            )
            logger.info("Lyrics sent!")
    except Exception as e:
        logger.error(f"Failed to get lyrics: {e}")
        await message.reply_text("Не удалось загрузить текст. Попробуй другой запрос.")


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(InlineQueryHandler(inline_query))
    app.add_handler(MessageHandler(filters.VIA_BOT, message_handler))

    logger.info("Bot ready")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
