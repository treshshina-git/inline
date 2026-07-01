import logging
import os
from collections import defaultdict, deque

from lyricsgenius import Genius
from telegram import InlineQueryResultArticle, InputTextMessageContent, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, InlineQueryHandler, ChosenInlineResultHandler, CallbackQueryHandler, ContextTypes
from telegram.error import BadRequest

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GENIUS_TOKEN = os.getenv("GENIUS_TOKEN")

genius = Genius(GENIUS_TOKEN, skip_non_songs=True, excluded_terms=["(Remix)", "(Live)"], remove_section_headers=True)

song_cache = defaultdict(dict)
user_history = defaultdict(lambda: deque(maxlen=10))

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query_text = update.inline_query.query.strip()
    if not query_text:
        return

    user_id = update.inline_query.from_user.id
    user_history[user_id].appendleft(query_text)

    try:
        per_page = 8
        offset = int(update.inline_query.offset or 0)
        page = offset // per_page + 1

        search = genius.search_songs(query_text, per_page=per_page + 1, page=page)
        results = []
        hits = search.get("hits", [])[:per_page]

        for hit in hits:
            song = hit.get("result", {})
            song_id = song.get("id")
            title = song.get("title", "Unknown")
            artist = song.get("primary_artist", {}).get("name", "Unknown Artist")
            full_title = f"{title} — {artist}"

            if song_id not in song_cache:
                song_cache[song_id] = {"title": full_title, "lyrics": None}

            results.append(
                InlineQueryResultArticle(
                    id=str(song_id),
                    title=full_title,
                    description="Нажми, чтобы получить полный текст",
                    input_message_content=InputTextMessageContent(full_title),
                )
            )

        next_offset = str(offset + per_page) if len(hits) >= per_page else ""

        await update.inline_query.answer(
            results, cache_time=300, is_personal=True, next_offset=next_offset
        )

    except Exception as e:
        logger.error(f"Inline error: {e}")


async def chosen_inline_result(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Главный обработчик выбора песни"""
    user_id = update.chosen_inline_result.from_user.id
    song_id_str = update.chosen_inline_result.result_id

    try:
        song_id = int(song_id_str)

        if song_id not in song_cache or song_cache[song_id].get("lyrics") is None:
            logger.info(f"Fetching full lyrics for song {song_id}")
            song_obj = genius.song(song_id)
            full_title = f"{song_obj.title} — {song_obj.primary_artist.name}"
            lyrics = song_obj.lyrics or "Текст не найден."
            song_cache[song_id] = {"title": full_title, "lyrics": lyrics}
        else:
            d = song_cache[song_id]
            full_title, lyrics = d["title"], d["lyrics"]

        keyboard = [
            [InlineKeyboardButton("📤 Отправить в этот чат", callback_data=f"share_{song_id}")],
            [InlineKeyboardButton("📜 История поиска", callback_data="history")]
        ]
        markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_message(
            chat_id=user_id,
            text=f"🎵 <b>{full_title}</b>\n\n{lyrics}",
            parse_mode=ParseMode.HTML,
            reply_markup=markup
        )
        logger.info(f"Successfully sent lyrics to user {user_id}")

    except Exception as e:
        logger.error(f"ChosenInlineResult error: {e}")
        await context.bot.send_message(chat_id=user_id, text="❌ Ошибка при загрузке текста песни. Попробуй ещё раз.")


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if query.data.startswith("share_"):
        song_id = int(query.data.split("_")[1])
        if song_id in song_cache and song_cache[song_id]["lyrics"]:
            d = song_cache[song_id]
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"🎵 <b>{d['title']}</b>\n\n{d['lyrics']}",
                parse_mode=ParseMode.HTML
            )
    elif query.data == "history":
        hist = "\n".join([f"• {q}" for q in list(user_history[query.from_user.id])])
        await query.edit_message_text(f"📜 Последние запросы:\n{hist}" if hist else "История пуста.")


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(InlineQueryHandler(inline_query))
    app.add_handler(ChosenInlineResultHandler(chosen_inline_result))
    app.add_handler(CallbackQueryHandler(callback_handler))

    logger.info("✅ Бот запущен — выбранная песня должна приходить")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
