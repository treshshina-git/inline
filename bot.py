import html
from uuid import uuid4
import os
import aiohttp
from telegram import (
    Update,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from telegram.ext import (
    Application,
    InlineQueryHandler,
    ContextTypes,
)

TOKEN = os.getenv("BOT_TOKEN")

async def wikipedia_search(query: str):
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "utf8": "1",
        "format": "json",
        "srlimit": 20,
    }
    
    print(params)

    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://ru.wikipedia.org/w/api.php",
            params=params,
        ) as response:
            data = await response.json()

    print(data)
    return data["query"]["search"]


async def inline_query(update: Update,
                       context: ContextTypes.DEFAULT_TYPE):

    query = update.inline_query.query.strip()

    if not query:
        await update.inline_query.answer([])
        return

    pages = await wikipedia_search(query)

    results = []

    for page in pages:
        title = page["title"]
        pageid = page["pageid"]

        snippet = html.unescape(page["snippet"])
        snippet = snippet.replace("<span class=\"searchmatch\">", "")
        snippet = snippet.replace("</span>", "")

        url = (
            "https://ru.wikipedia.org/wiki/"
            + title.replace(" ", "_")
        )

        results.append(
            InlineQueryResultArticle(
                id=str(pageid),
                title=title,
                description=snippet[:100],

                input_message_content=InputTextMessageContent(
                    message_text=(
                        f"<b>{title}</b>\n\n"
                        f"{snippet}\n\n"
                        f"<a href='{url}'>Open article</a>"
                    ),
                    parse_mode="HTML"
                ),

                url=url,
                hide_url=False,
            )
        )

    await update.inline_query.answer(
        results=results,
        cache_time=300,
        is_personal=True
    )



async def error_handler(update, context):
    print("ERROR:", context.error)



def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(
        InlineQueryHandler(inline_query)
    )
    app.add_error_handler(error_handler)

    print("Bot started")

    app.run_polling()


if __name__ == "__main__":
    main()