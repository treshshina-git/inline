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

song_cache = defaultdict(dict)           # song_id -> {"title": , "lyrics": }
user_history = defaultdict(lambda: deque(maxlen=10))

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Чистый поиск: только при наличии запроса"""
    query_text = update.inline_query.query.strip()
    offset = update.inline_query.offset or "0"

    if not query_text:   # Пустой запрос — ничего не показываем
        return

    user_id = update.inline_query.from_user.id
    user_history[user_id].appendleft(query_text)
    print(f"User {user_id} chose song ID {song_id}")
    try:
        per_page = 8
        offset_int = int(offset)
        page = offset_int // per_page + 1

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
                    description="Нажми для получения текста песни",
                    input_message_content=InputTextMessageContent(full_title),
                )
            )

        next_offset = str(offset_int + per_page) if len(hits) >= per_page else ""

        await update.inline_query.answer(
            results,
            cache_time=360,
            is_personal=True,
            next_offset=next_offset
        )

    except Exception as e:
        logger.error(f"Inline error: {e}")


async def chosen_inline_result(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.chosen_inline_result.from_user.id
    song_id = int(update.chosen_inline_result.result_id)

    try:
        if song_id not in song_cache or song_cache[song_id].get("lyrics") is None:
            song_obj = genius.song(song_id)
            full_title = f"{song_obj.title} — {song_obj.primary_artist.name}"
            lyrics = song_obj.lyrics or "Текст не найден."
            song_cache[song_id] = {"title": full_title, "lyrics": lyrics}
        else:
            d = song_cache[song_id]
            full_title, lyrics = d["title"], d["lyrics"]

        keyboard = [
            [InlineKeyboardButton("📤 Отправить в чат", callback_data=f"share_{song_id}")],
            [InlineKeyboardButton("📜 История поиска", callback_data="history")]
        ]
        markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_message(
            chat_id=user_id,
            text=f"🎵 <b>{full_title}</b>\n\n{lyrics}",
            parse_mode=ParseMode.HTML,
            reply_markup=markup
        )
    except Exception as e:
        logger.error(f"Chosen error: {e}")
        await context.bot.send_message(chat_id=user_id, text="❌ Не удалось загрузить текст.")


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("share_"):
        song_id = int(data.split("_")[1])
        if song_id in song_cache and song_cache[song_id]["lyrics"]:
            d = song_cache[song_id]
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"🎵 <b>{d['title']}</b>\n\n{d['lyrics']}",
                parse_mode=ParseMode.HTML
            )
    elif data == "history":
        hist = "\n".join([f"• {q}" for q in list(user_history[query.from_user.id])])
        await query.edit_message_text(f"📜 История:\n{hist}" if hist else "Пока пусто.")


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(InlineQueryHandler(inline_query))
    app.add_handler(ChosenInlineResultHandler(chosen_inline_result))
    app.add_handler(CallbackQueryHandler(callback_handler))

    logger.info("✅ Чистый бот запущен (без превью и топ-треков)")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
