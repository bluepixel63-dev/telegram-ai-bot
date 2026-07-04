import asyncio
import requests
import base64
import edge_tts
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

TELEGRAM_TOKEN = "8981634641:AAF0OSEIdLBA5jxileqixfY0rIr_mjJx-uk"
GROQ_API_KEY = "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"
VOICE = "fa-IR-FaridNeural"

SYSTEM_PROMPT = "تو یک دستیار هوشمند و مفید فارسی‌زبان هستی. کوتاه (حداکثر ۲-۳ جمله) و دوستانه جواب بده."

memory = {}
MAX_HISTORY = 10

def get_history(chat_id):
    if chat_id not in memory:
        memory[chat_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    return memory[chat_id]

def add_message(chat_id, role, content):
    history = get_history(chat_id)
    history.append({"role": role, "content": content})
    if len(history) > MAX_HISTORY + 1:
        memory[chat_id] = [history[0]] + history[-MAX_HISTORY:]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    memory[chat_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    await update.message.reply_text("سلام! حافظه‌مو پاک کردم و آماده‌ام. تایپ کن، ویس بفرست یا عکس بفرست 🤖")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    memory[chat_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    await update.message.reply_text("حافظه پاک شد ✅ از اول شروع می‌کنیم.")

def call_groq_chat(chat_id, user_text):
    add_message(chat_id, "user", user_text)
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": get_history(chat_id)
    }
    r = requests.post(url, headers=headers, json=payload)
    reply = r.json()["choices"][0]["message"]["content"]
    add_message(chat_id, "assistant", reply)
    return reply

def call_groq_whisper(file_path):
    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    with open(file_path, "rb") as f:
        files = {"file": f}
        data = {"model": "whisper-large-v3", "language": "fa"}
        r = requests.post(url, headers=headers, files=files, data=data)
    return r.json()["text"]

def call_groq_vision(image_path, question):
    with open(image_path, "rb") as f:
        b64_image = base64.b64encode(f.read()).decode('utf-8')
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "meta-llama/llama-4-scout-17b-16e-instruct",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"به فارسی جواب بده. {question}"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}}
                ]
            }
        ]
    }
    r = requests.post(url, headers=headers, json=payload)
    return r.json()["choices"][0]["message"]["content"]

async def reply_with_voice(update, context, reply_text):
    chat_id = update.effective_chat.id
    communicate = edge_tts.Communicate(reply_text, VOICE)
    await communicate.save("reply.mp3")
    await update.message.reply_text(reply_text)
    with open("reply.mp3", "rb") as f:
        await context.bot.send_voice(chat_id=chat_id, voice=f)

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    reply_text = await asyncio.to_thread(call_groq_chat, chat_id, update.message.text)
    await reply_with_voice(update, context, reply_text)

async def voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    voice_file = await update.message.voice.get_file()
    await voice_file.download_to_drive("incoming.ogg")
    user_text = await asyncio.to_thread(call_groq_whisper, "incoming.ogg")
    reply_text = await asyncio.to_thread(call_groq_chat, chat_id, user_text)
    await reply_with_voice(update, context, reply_text)

async def photo_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    photo_file = await update.message.photo[-1].get_file()
    await photo_file.download_to_drive("incoming.jpg")
    question = update.message.caption if update.message.caption else "توی این عکس چی می‌بینی؟ کامل توضیح بده."
    reply_text = await asyncio.to_thread(call_groq_vision, "incoming.jpg", question)
    add_message(chat_id, "user", f"[عکس فرستاد] {question}")
    add_message(chat_id, "assistant", reply_text)
    await reply_with_voice(update, context, reply_text)

async def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    app.add_handler(MessageHandler(filters.VOICE, voice_message))
    app.add_handler(MessageHandler(filters.PHOTO, photo_message))
    print("ربات روشن شد...")
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
