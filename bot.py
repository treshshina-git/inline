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

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query.strip()
    if not query:
        return

    try:
        results = []
        search = genius.search_songs(query, per_page=5)
        print(search)
        for hit in search.get("hits", [])[:5]:
            song = hit["result"]
            #print(song)
            full_title = f"{song['title']} — {song['primary_artist']}"

            results.append(
                InlineQueryResultArticle(
                    id=str(song["id"]),
                    title=full_title,
                    description="Получить текст",
                    input_message_content=InputTextMessageContent(full_title),
                )
            )

        await update.inline_query.answer(results, cache_time=60, is_personal=True)
    except Exception as e:
        logger.error(f"Inline error: {e}")


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message.via_bot or message.via_bot.username != context.bot.username:
        return

    text = message.text.strip()
    logger.info(f"Caught: {text}")

    try:
        search = genius.search_songs(text, per_page=1)
        if not search.get("hits"):
            await message.reply_text("Песня не найдена.")
            return

        song_data = search["hits"][0]["result"]
        song_id = song_data["id"]

        # Получаем полные данные
        song = genius.song(song_id)
        print(f"song: \n{song}")
        # Безопасное извлечение
        title = song.title if hasattr(song, 'title') else song_data.get("title", "Unknown")
        
        # Artist может быть dict
        if isinstance(song.primary_artist_names, dict):
            artist = song.primary_artist_names.get("name", "Unknown")
        else:
            artist = getattr(song.primary_artist, 'name', song_data.get("primary_artist_names").get("name", "Unknown"))
        lyrics = song.lyrics if hasattr(song, 'lyrics') else "Текст не найден."

        await message.reply_text(
            f"🎵 <b>{title} — {artist}</b>\n\n{lyrics}",
            parse_mode=ParseMode.HTML
        )
        logger.info("Lyrics sent!")
    except Exception as e:
        logger.error(f"Get lyrics error: {e}")
        await message.reply_text("Не удалось загрузить текст. Попробуй другой запрос.")


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(InlineQueryHandler(inline_query))
    app.add_handler(MessageHandler(filters.VIA_BOT, message_handler))

    logger.info("Bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
