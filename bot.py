import os
from telegram import InlineQueryResultArticle, InputTextMessageContent, Update
from telegram.ext import Application, InlineQueryHandler, ContextTypes
from fastapi import FastAPI, Request

BOT_TOKEN=os.getenv("BOT_TOKEN")
WEBHOOK_URL=os.getenv("APP_URL")
PORT=int(os.getenv("PORT"))
WEBHOOK_SECRET="secret"

app = FastAPI()

tg_app = setup_app()


@app.on_event("startup")
async def startup():

    validate_config()

    await tg_app.initialize()

    await tg_app.bot.set_webhook(
        url=WEBHOOK_URL,
        secret_token=WEBHOOK_SECRET
    )


@app.post("/webhook")
async def webhook(request: Request):

    data = await request.json()

    update = Update.de_json(data, tg_app.bot)

    await tg_app.process_update(update)

    return {"ok": True}


@app.get("/health")
def health():
    return {"status": "ok"}






async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query=update.inline_query.query.strip()
    if not query:
        return

    text=f"Вы искали: {query}"

    results=[InlineQueryResultArticle(
        id="1",
        title=f"Результат: {query}",
        description=text,
        input_message_content=InputTextMessageContent(text)
    )]

    await update.inline_query.answer(results, cache_time=1)

app=Application.builder().token(BOT_TOKEN).build()
app.add_handler(InlineQueryHandler(inline_query))

if __name__=="__main__":
    botik = BOT_TOKEN
    print(botik)
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=f"{APP_URL}",
        secret_token=BOT_TOKEN
    )
