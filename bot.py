import logging
import os
from collections import defaultdict, deque
import time
from functools import wraps

from lyricsgenius import Genius
from telegram import (
    InlineQueryResultArticle, InputTextMessageContent, Update,
    InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application, InlineQueryHandler, ChosenInlineResultHandler,
    CallbackQueryHandler, ContextTypes
)

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GENIUS_TOKEN = os.getenv("GENIUS_TOKEN")

genius = Genius(GENIUS_TOKEN, skip_non_songs=True, excluded_terms=["(Remix)", "(Live)"], remove_section_headers=True)

# Кэши
song_cache = defaultdict(dict)                    # song_id -> data
user_history = defaultdict(lambda: deque(maxlen=10))  # user_id -> последние запросы
user_rate_limit = defaultdict(list)               # rate limiting

def rate_limit(seconds=2):
    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user_id = update.effective_user.id
            now = time.time()
            user_rate_limit[user_id] = [t for t in user_rate_limit[user_id] if now - t < 10]
            
            if len(user_rate_limit[user_id]) >= 5:  # max 5 запросов за 10 сек
                if isinstance(update, Update) and update.inline_query:
                    await update.inline_query.answer([], cache_time=1)
                return
            user_rate_limit[user_id].append(now)
            return await func(update, context)
        return wrapper
    return decorator

@rate_limit(seconds=2)
async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query_text = update.inline_query.query.strip()
    offset = update.inline_query.offset or "0"
    user_id = update.inline_query.from_user.id

    if query_text:
        user_history[user_id].appendleft(query_text)

    try:
        per_page = 6
        offset_int = int(offset)
        page = offset_int // per_page + 1

        search = genius.search_songs(query_text or "top", per_page=per_page + 1, page=page)

        results = []
        hits = search.get("hits", [])[:per_page]

        for hit in hits:
            song = hit.get("result", {})
            song_id = song.get("id")
            title = song.get("title", "Unknown")
            artist = song.get("primary_artist", {}).get("name", "Unknown")
            full_title = f"{title} - {artist}"

            if song_id not in song_cache:
                try:
                    song_obj = genius.song(song_id)
                    lyrics = song_obj.lyrics or "Текст не найден."
                    song_cache[song_id] = {"title": full_title, "lyrics": lyrics}
                except:
                    lyrics = "Текст недоступен"
            else:
                lyrics = song_cache[song_id]["lyrics"]

            preview = (lyrics[:250] + "...") if len(lyrics) > 250 else lyrics

            results.append(
                InlineQueryResultArticle(
                    id=str(song_id),
                    title=full_title,
                    description=preview[:100],
                    input_message_content=InputTextMessageContent(
                        f"🎵 <b>{full_title}</b>\n\n{preview}", parse_mode=ParseMode.HTML
                    ),
                )
            )

        next_offset = str(offset_int + per_page) if len(hits) == per_page else ""

        await update.inline_query.answer(results, cache_time=120, is_personal=True, next_offset=next_offset)

    except Exception as e:
        logger.error(f"Inline error: {e}")
        await update.inline_query.answer([])


async def chosen_inline_result(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.chosen_inline_result.from_user
    song_id = int(update.chosen_inline_result.result_id)
    original_chat_id = None  # можно улучшить через context
    try:
        if song_id not in song_cache:
            song_obj = genius.song(song_id)
            full_title = f"{song_obj.title} — {song_obj.primary_artist.name}"
            lyrics = song_obj.lyrics or "Текст не найден."
            song_cache[song_id] = {"title": full_title, "lyrics": lyrics}
        else:
            data = song_cache[song_id]
            full_title, lyrics = data["title"], data["lyrics"]

        keyboard = [
            [InlineKeyboardButton("📤 Отправить в группу/чат", callback_data=f"share_group_{song_id}")],
            [InlineKeyboardButton("❤️ Сохранить в Избранное", callback_data=f"favorite_{song_id}")],
            [InlineKeyboardButton("📜 История поиска", callback_data="history")]
        ]
        markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_message(
            chat_id=user.id,
            text=f"🎵 <b>{full_title}</b>\n\n{lyrics}",
            parse_mode=ParseMode.HTML,
            reply_markup=markup
        )
    except Exception as e:
        logger.error(f"Chosen error: {e}")


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data.startswith("share_group_"):
        song_id = int(data.split("_")[2])
        if song_id in song_cache:
            d = song_cache[song_id]
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"🎵 <b>{d['title']}</b>\n\n{d['lyrics']}",
                parse_mode=ParseMode.HTML
            )
            await query.edit_message_text("✅ Отправлено в чат!")
    elif data == "history":
        history = "\n".join([f"• {q}" for q in list(user_history[user_id])[:8]])
        await query.edit_message_text(f"📜 Последние поиски:\n{history}" if history else "История пуста.")
    # Можно добавить favorite позже

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(InlineQueryHandler(inline_query))
    app.add_handler(ChosenInlineResultHandler(chosen_inline_result))
    app.add_handler(CallbackQueryHandler(callback_handler))

    logger.info("🚀 Genius Bot с историей, группами и rate limit запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
