"""
Tuxum Market — Telegram bot (bitta faylda, Vercel Python Serverless Function)
=============================================================================

DEPLOY QO'LLANMASI (VERCEL):
1) Ushbu faylni  api/bot.py  yo'lida saqlang (papka nomi aynan "api" bo'lishi shart).
2) Loyihaning ILDIZ papkasiga quyidagi ikkita faylni ham qo'shing:

   requirements.txt:
       requests
       groq

   vercel.json:
       {
         "functions": { "api/bot.py": { "runtime": "python3.12" } }
       }

3) Vercel loyiha sozlamalarida (Settings -> Environment Variables) quyidagilarni kiriting:
       BOT_TOKEN        -> Telegram bot tokeni (@BotFather)
       GROQ_API_KEY      -> Groq API kaliti (TuxumAI uchun)
       ADMIN_CHAT_ID     -> Sizning Telegram chat ID'ingiz (yangi buyurtma xabarlari uchun)
       FIREBASE_URL      -> Firebase Realtime Database URL, oxirida "/" bo'lmasin
                             (masalan: https://tuxum-market-default-rtdb.firebaseio.com)
       WEBHOOK_SECRET    -> o'zingiz o'ylab topgan maxfiy so'z (ixtiyoriy, xavfsizlik uchun)

4) Deploy qilgandan so'ng, Telegram webhookni shu manzilga ulang (brauzerda oching):
   https://api.telegram.org/bot<BOT_TOKEN>/setWebhook?url=https://<vercel-domeningiz>/api/bot

   Masalan:
   https://api.telegram.org/bot123456:ABC/setWebhook?url=https://tuxum-market.vercel.app/api/bot

Eslatma: Vercel serverless funksiyalari statesiz (har chaqiriqda "tozadan" ishga tushadi),
shuning uchun foydalanuvchi holati (til, savat, buyurtma bosqichi) Firebase Realtime
Database orqali saqlanadi. edge-tts ovozli javob ixtiyoriy — TTS_ENABLED=False qilib
o'chirib qo'yish mumkin (Vercel'da ffmpeg yo'qligi sababli mp3 audio fayl sifatida
yuboriladi, ovozli xabar "voice bubble" sifatida emas).
"""

import os
import json
import time
import random
import string
import urllib.request
import urllib.parse
from http.server import BaseHTTPRequestHandler

import requests

# ----------------------------------------------------------------------------
# SOZLAMALAR
# ----------------------------------------------------------------------------

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "")
FIREBASE_URL = os.environ.get("FIREBASE_URL", "").rstrip("/")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
EGG_PRICE = 1500  # 1 dona tuxum narxi (so'm) — xohlasangiz o'zgartiring

TEXTS = {
    "uz": {
        "choose_lang": "Tilni tanlang / Choose language / Выберите язык:",
        "welcome": "Assalomu alaykum, {name}! 🥚\nTuxum Market botiga xush kelibsiz.\nQuyidagi menyudan birini tanlang:",
        "menu_order": "🛒 Buyurtma berish",
        "menu_price": "💰 Narxlar",
        "menu_ai": "🤖 TuxumAI bilan suhbat",
        "menu_contact": "📞 Aloqa",
        "menu_lang": "🌐 Tilni o'zgartirish",
        "ask_qty": "Nechta tuxum buyurtma qilmoqchisiz? (Sonini yozing, masalan: 30)",
        "invalid_qty": "Iltimos, faqat son kiriting (masalan: 30).",
        "ask_address": "Yetkazib berish manzilini yozing:",
        "ask_phone": "Telefon raqamingizni yuboring (masalan: +998901234567):",
        "order_done": "✅ Buyurtmangiz qabul qilindi!\n\n🥚 Miqdor: {qty} dona\n💵 Narx: {total} so'm\n📍 Manzil: {address}\n📱 Tel: {phone}\n\nTez orada operatorimiz siz bilan bog'lanadi!",
        "price_info": "💰 1 dona tuxum narxi: {price} so'm\n\nKo'p miqdorda buyurtma uchun chegirmalar mavjud, /buyurtma orqali murojaat qiling.",
        "contact_info": "📞 Biz bilan bog'lanish:\nTelefon: +998 90 000 00 00\nManzil: Toshkent shahri\n\nSavollaringiz bo'lsa, shu yerga yozishingiz mumkin — TuxumAI sizga yordam beradi 🤖",
        "ai_prompt": "TuxumAI bilan suhbatlashish uchun savolingizni yozing 👇",
        "ai_thinking": "TuxumAI o'ylanmoqda... 🤔",
        "new_order_admin": "🆕 Yangi buyurtma!\n👤 {name} (@{username})\n🥚 {qty} dona — {total} so'm\n📍 {address}\n📱 {phone}",
        "back": "⬅️ Orqaga",
        "unknown": "Kechirasiz, tushunmadim. Menyudan tanlang yoki savolingizni yozing.",
    },
    "ru": {
        "choose_lang": "Tilni tanlang / Choose language / Выберите язык:",
        "welcome": "Здравствуйте, {name}! 🥚\nДобро пожаловать в Tuxum Market.\nВыберите пункт меню:",
        "menu_order": "🛒 Заказать",
        "menu_price": "💰 Цены",
        "menu_ai": "🤖 Чат с TuxumAI",
        "menu_contact": "📞 Контакты",
        "menu_lang": "🌐 Изменить язык",
        "ask_qty": "Сколько яиц хотите заказать? (например: 30)",
        "invalid_qty": "Пожалуйста, введите число (например: 30).",
        "ask_address": "Введите адрес доставки:",
        "ask_phone": "Отправьте номер телефона (например: +998901234567):",
        "order_done": "✅ Ваш заказ принят!\n\n🥚 Количество: {qty} шт\n💵 Сумма: {total} сум\n📍 Адрес: {address}\n📱 Тел: {phone}\n\nНаш оператор скоро свяжется с вами!",
        "price_info": "💰 Цена 1 яйца: {price} сум\n\nПри заказе оптом действуют скидки, оформите заказ через /buyurtma.",
        "contact_info": "📞 Наши контакты:\nТелефон: +998 90 000 00 00\nАдрес: г. Ташкент\n\nЕсли есть вопросы — просто напишите, TuxumAI поможет 🤖",
        "ai_prompt": "Напишите ваш вопрос для TuxumAI 👇",
        "ai_thinking": "TuxumAI думает... 🤔",
        "new_order_admin": "🆕 Новый заказ!\n👤 {name} (@{username})\n🥚 {qty} шт — {total} сум\n📍 {address}\n📱 {phone}",
        "back": "⬅️ Назад",
        "unknown": "Извините, не понял. Выберите пункт меню или напишите вопрос.",
    },
    "en": {
        "choose_lang": "Tilni tanlang / Choose language / Выберите язык:",
        "welcome": "Hello, {name}! 🥚\nWelcome to Tuxum Market bot.\nChoose an option below:",
        "menu_order": "🛒 Place order",
        "menu_price": "💰 Prices",
        "menu_ai": "🤖 Chat with TuxumAI",
        "menu_contact": "📞 Contact",
        "menu_lang": "🌐 Change language",
        "ask_qty": "How many eggs would you like to order? (e.g. 30)",
        "invalid_qty": "Please enter a number (e.g. 30).",
        "ask_address": "Enter delivery address:",
        "ask_phone": "Send your phone number (e.g. +998901234567):",
        "order_done": "✅ Your order has been placed!\n\n🥚 Qty: {qty}\n💵 Total: {total} UZS\n📍 Address: {address}\n📱 Phone: {phone}\n\nOur operator will contact you soon!",
        "price_info": "💰 Price per egg: {price} UZS\n\nBulk discounts available, order via /buyurtma.",
        "contact_info": "📞 Contact us:\nPhone: +998 90 000 00 00\nAddress: Tashkent city\n\nHave questions? Just type them — TuxumAI will help 🤖",
        "ai_prompt": "Type your question for TuxumAI 👇",
        "ai_thinking": "TuxumAI is thinking... 🤔",
        "new_order_admin": "🆕 New order!\n👤 {name} (@{username})\n🥚 {qty} pcs — {total} UZS\n📍 {address}\n📱 {phone}",
        "back": "⬅️ Back",
        "unknown": "Sorry, I didn't understand. Choose a menu option or type a question.",
    },
}

# ----------------------------------------------------------------------------
# FIREBASE YORDAMCHI FUNKSIYALARI (foydalanuvchi holati / buyurtmalar saqlash)
# ----------------------------------------------------------------------------

def fb_get(path):
    if not FIREBASE_URL:
        return None
    try:
        r = requests.get(f"{FIREBASE_URL}/{path}.json", timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def fb_set(path, data):
    if not FIREBASE_URL:
        return None
    try:
        r = requests.put(f"{FIREBASE_URL}/{path}.json", json=data, timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def fb_push(path, data):
    if not FIREBASE_URL:
        return None
    try:
        r = requests.post(f"{FIREBASE_URL}/{path}.json", json=data, timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def get_user_state(chat_id):
    state = fb_get(f"users/{chat_id}")
    if not state:
        state = {"lang": None, "step": None, "order": {}}
    return state


def set_user_state(chat_id, state):
    fb_set(f"users/{chat_id}", state)


# ----------------------------------------------------------------------------
# TELEGRAM YORDAMCHI FUNKSIYALARI
# ----------------------------------------------------------------------------

def tg_call(method, payload):
    try:
        r = requests.post(f"{TG_API}/{method}", json=payload, timeout=10)
        return r.json()
    except Exception as e:
        print("Telegram API error:", e)
        return None


def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return tg_call("sendMessage", payload)


def send_audio_bytes(chat_id, audio_bytes, filename="tuxumai.mp3"):
    try:
        files = {"audio": (filename, audio_bytes)}
        data = {"chat_id": chat_id}
        requests.post(f"{TG_API}/sendAudio", data=data, files=files, timeout=20)
    except Exception as e:
        print("sendAudio error:", e)


def lang_keyboard():
    return {
        "inline_keyboard": [
            [
                {"text": "🇺🇿 O'zbek", "callback_data": "lang_uz"},
                {"text": "🇷🇺 Русский", "callback_data": "lang_ru"},
                {"text": "🇬🇧 English", "callback_data": "lang_en"},
            ]
        ]
    }


def main_menu_keyboard(lang):
    t = TEXTS[lang]
    return {
        "keyboard": [
            [{"text": t["menu_order"]}, {"text": t["menu_price"]}],
            [{"text": t["menu_ai"]}, {"text": t["menu_contact"]}],
            [{"text": t["menu_lang"]}],
        ],
        "resize_keyboard": True,
    }


# ----------------------------------------------------------------------------
# TUXUM AI (Groq)
# ----------------------------------------------------------------------------

def ask_tuxum_ai(user_text, lang):
    if not GROQ_API_KEY:
        return "TuxumAI hozircha sozlanmagan (GROQ_API_KEY yo'q)."

    system_prompt = {
        "uz": "Sen TuxumAI — Tuxum Market kompaniyasining do'stona yordamchisisan. "
              "Tuxum sotib olish, yetkazib berish, narxlar va foyda haqida qisqa, "
              "aniq javob ber. O'zbek tilida javob ber.",
        "ru": "Ты TuxumAI — дружелюбный помощник компании Tuxum Market. "
              "Отвечай кратко и по делу на вопросы о покупке яиц, доставке и ценах. Отвечай на русском.",
        "en": "You are TuxumAI, a friendly assistant for Tuxum Market, an egg-selling business. "
              "Answer briefly and helpfully about eggs, delivery and prices. Reply in English.",
    }.get(lang, "uz")

    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_text},
                ],
                "temperature": 0.6,
                "max_tokens": 400,
            },
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print("Groq error:", e)
        return {
            "uz": "Kechirasiz, TuxumAI hozir javob bera olmadi. Birozdan so'ng qayta urinib ko'ring.",
            "ru": "Извините, TuxumAI сейчас не может ответить. Попробуйте позже.",
            "en": "Sorry, TuxumAI could not respond right now. Please try again later.",
        }.get(lang, "Xatolik yuz berdi.")


# ----------------------------------------------------------------------------
# ASOSIY UPDATE ISHLOVCHISI
# ----------------------------------------------------------------------------

def handle_update(update):
    if "callback_query" in update:
        cq = update["callback_query"]
        chat_id = cq["message"]["chat"]["id"]
        data = cq.get("data", "")
        if data.startswith("lang_"):
            lang = data.split("_", 1)[1]
            state = get_user_state(chat_id)
            state["lang"] = lang
            state["step"] = None
            set_user_state(chat_id, state)
            name = cq["from"].get("first_name", "")
            send_message(chat_id, TEXTS[lang]["welcome"].format(name=name), main_menu_keyboard(lang))
        return

    if "message" not in update:
        return

    msg = update["message"]
    chat_id = msg["chat"]["id"]
    text = msg.get("text", "")
    from_user = msg.get("from", {})
    name = from_user.get("first_name", "do'stim")
    username = from_user.get("username", "-")

    state = get_user_state(chat_id)
    lang = state.get("lang")

    # Til tanlanmagan bo'lsa — birinchi navbatda tilni so'raymiz
    if not lang:
        if text == "/start":
            send_message(chat_id, TEXTS["uz"]["choose_lang"], lang_keyboard())
        else:
            send_message(chat_id, TEXTS["uz"]["choose_lang"], lang_keyboard())
        return

    t = TEXTS[lang]
    step = state.get("step")

    # --- Buyurtma bosqichlari ---
    if step == "await_qty":
        if text.strip().isdigit():
            qty = int(text.strip())
            state["order"]["qty"] = qty
            state["order"]["total"] = qty * EGG_PRICE
            state["step"] = "await_address"
            set_user_state(chat_id, state)
            send_message(chat_id, t["ask_address"])
        else:
            send_message(chat_id, t["invalid_qty"])
        return

    if step == "await_address":
        state["order"]["address"] = text.strip()
        state["step"] = "await_phone"
        set_user_state(chat_id, state)
        send_message(chat_id, t["ask_phone"])
        return

    if step == "await_phone":
        state["order"]["phone"] = text.strip()
        order = state["order"]
        order_id = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        fb_push("orders", {
            "order_id": order_id,
            "chat_id": chat_id,
            "name": name,
            "username": username,
            "qty": order["qty"],
            "total": order["total"],
            "address": order["address"],
            "phone": order["phone"],
            "created_at": int(time.time()),
        })
        send_message(chat_id, t["order_done"].format(
            qty=order["qty"], total=order["total"],
            address=order["address"], phone=order["phone"],
        ), main_menu_keyboard(lang))
        if ADMIN_CHAT_ID:
            send_message(ADMIN_CHAT_ID, t["new_order_admin"].format(
                name=name, username=username, qty=order["qty"],
                total=order["total"], address=order["address"], phone=order["phone"],
            ))
        state["step"] = None
        state["order"] = {}
        set_user_state(chat_id, state)
        return

    # --- Menyu / buyruqlar ---
    if text in ("/start",):
        send_message(chat_id, t["welcome"].format(name=name), main_menu_keyboard(lang))
        return

    if text in (t["menu_lang"],) or text == "/til":
        send_message(chat_id, TEXTS["uz"]["choose_lang"], lang_keyboard())
        return

    if text in (t["menu_order"], "/buyurtma"):
        state["step"] = "await_qty"
        state["order"] = {}
        set_user_state(chat_id, state)
        send_message(chat_id, t["ask_qty"])
        return

    if text == t["menu_price"]:
        send_message(chat_id, t["price_info"].format(price=EGG_PRICE))
        return

    if text == t["menu_contact"]:
        send_message(chat_id, t["contact_info"])
        return

    if text == t["menu_ai"]:
        send_message(chat_id, t["ai_prompt"])
        return

    # --- Aks holda: TuxumAI bilan erkin suhbat ---
    if text:
        send_message(chat_id, t["ai_thinking"])
        reply = ask_tuxum_ai(text, lang)
        send_message(chat_id, reply, main_menu_keyboard(lang))
        return

    send_message(chat_id, t["unknown"], main_menu_keyboard(lang))


# ----------------------------------------------------------------------------
# VERCEL SERVERLESS HANDLER
# ----------------------------------------------------------------------------

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Tuxum Market bot is running.")

    def do_POST(self):
        if WEBHOOK_SECRET:
            secret_header = self.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if secret_header != WEBHOOK_SECRET:
                self.send_response(403)
                self.end_headers()
                return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length else b"{}"

        try:
            update = json.loads(body.decode("utf-8"))
            handle_update(update)
        except Exception as e:
            print("Update handling error:", e)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')
