import logging
import os

from lyricsgenius import Genius
from telegram import InlineQueryResultArticle, InputTextMessageContent, Update
from telegram.constants import ParseMode
from telegram.ext import Application, InlineQueryHandler, ChosenInlineResultHandler, ContextTypes

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
        search = genius.search_songs(query, per_page=5)

        for hit in search.get("hits", [])[:5]:
            song = hit["result"]
            song_id = song["id"]
            full_title = f"{song['title']} — {song['primary_artist']['name']}"

            song_cache[song_id] = {"title": full_title, "lyrics": None}

            results.append(
                InlineQueryResultArticle(
                    id=str(song_id),
                    title=full_title,
                    description="Получить текст песни",
                    input_message_content=InputTextMessageContent(full_title),
                )
            )

        await update.inline_query.answer(results, cache_time=60, is_personal=True)
        logger.info(f"Answered inline for: {query}")

    except Exception as e:
        logger.error(f"Inline error: {e}")


async def chosen_inline_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("=== CHOSEN INLINE RESULT RECEIVED ===")
    user_id = update.chosen_inline_result.from_user.id
    song_id = int(update.chosen_inline_result.result_id)

    try:
        if song_id not in song_cache or song_cache[song_id]["lyrics"] is None:
            song_obj = genius.song(song_id)
            full_title = f"{song_obj.title} — {song_obj.primary_artist.name}"
            lyrics = song_obj.lyrics or "Текст не найден."
            song_cache[song_id] = {"title": full_title, "lyrics": lyrics}
        else:
            d = song_cache[song_id]
            full_title = d["title"]
            lyrics = d["lyrics"]

        await context.bot.send_message(
            chat_id=user_id,
            text=f"🎵 <b>{full_title}</b>\n\n{lyrics}",
            parse_mode=ParseMode.HTML
        )
        logger.info(f"Successfully sent lyrics for song {song_id} to {user_id}")

    except Exception as e:
        logger.error(f"Failed to send lyrics: {e}")


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(InlineQueryHandler(inline_query))
    app.add_handler(ChosenInlineResultHandler(chosen_inline_result))

    logger.info("Bot started. Test inline now.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
