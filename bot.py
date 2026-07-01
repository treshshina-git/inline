import logging
import os
import time
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
user_rate_limit = defaultdict(list)

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

        # Быстрый поиск
        search = genius.search_songs(query_text or "popular", per_page=per_page + 2, page=page)

        results = []
        hits = search.get("hits", [])[:per_page]

        for hit in hits:
            song = hit.get("result", {})
            song_id = song.get("id")
            title = song.get("title", "Unknown")
            artist = song.get("primary_artist", {}).get("name", "Unknown")
            full_title = f"{title} - {artist}"

            # Кэш
            if song_id not in song_cache:
                try:
                    song_obj = genius.song(song_id)
                    lyrics = song_obj.lyrics[:1500] or "Текст не найден."  # ограничиваем
                    song_cache[song_id] = {"title": full_title, "lyrics": lyrics}
                except:
                    lyrics = "Текст недоступен"
            else:
                lyrics = song_cache[song_id]["lyrics"]

            preview = (lyrics[:240] + "...") if len(lyrics) > 240 else lyrics

            results.append(
                InlineQueryResultArticle(
                    id=str(song_id),
                    title=full_title,
                    description=preview[:90],
                    input_message_content=InputTextMessageContent(
                        f"🎵 <b>{full_title}</b>\n\n{preview}", parse_mode=ParseMode.HTML
                    ),
                )
            )

        next_offset = str(offset_int + per_page) if len(hits) >= per_page else ""

        await update.inline_query.answer(
            results, 
            cache_time=300,           # сильно кэшируем
            is_personal=True,
            next_offset=next_offset
        )

    except BadRequest as e:
        if "Query is too old" in str(e):
            logger.warning("Inline query timeout - user typed too fast")
        else:
            logger.error(f"BadRequest: {e}")
    except Exception as e:
        logger.error(f"Inline error: {e}")
        try:
            await update.inline_query.answer([])
        except:
            pass


async def chosen_inline_result(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.chosen_inline_result.from_user.id
    try:
        song_id = int(update.chosen_inline_result.result_id)
        if song_id not in song_cache:
            song_obj = genius.song(song_id)
            full_title = f"{song_obj.title} — {song_obj.primary_artist.name}"
            lyrics = song_obj.lyrics or "Текст не найден."
            song_cache[song_id] = {"title": full_title, "lyrics": lyrics}
        else:
            d = song_cache[song_id]
            full_title, lyrics = d["title"], d["lyrics"]
            keyboard = [
            [InlineKeyboardButton("📤 Отправить в чат", callback_data=f"share_{song_id}")],
            [InlineKeyboardButton("📜 История", callback_data="history")]
        ]
        markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_message(
            chat_id=user_id,
            text=f"🎵 <b>{full_title}</b>\n\n{lyrics[:3500]}",  # Telegram limit
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
        if song_id in song_cache:
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

    logger.info("✅ Bot started with fixes!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
