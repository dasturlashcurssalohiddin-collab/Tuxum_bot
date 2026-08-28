"""
Tuxum Market — Telegram bot (bitta faylda, Vercel Python Serverless Function)
=============================================================================

DEPLOY QO'LLANMASI (VERCEL):
1) Ushbu faylni  api/index.py  yo'lida saqlang (papka nomi aynan "api" bo'lishi shart,
   fayl nomi aynan "index.py" bo'lishi kerak — Vercel shu nomlarni avtomatik taniydi).
2) Loyihaning ILDIZ papkasiga  requirements.txt  faylini qo'shing:
       requests

3) Vercel loyiha sozlamalarida (Settings -> Environment Variables) quyidagilarni kiriting:
       BOT_TOKEN        -> Telegram bot tokeni (@BotFather)
       ADMIN_CHAT_ID     -> Sizning Telegram chat ID'ingiz (yangi buyurtma va e'lon uchun)
       FIREBASE_URL      -> Firebase Realtime Database URL, oxirida "/" bo'lmasin
                             (masalan: https://tuxum-market-default-rtdb.firebaseio.com)
       WEBHOOK_SECRET    -> o'zingiz o'ylab topgan maxfiy so'z (ixtiyoriy, xavfsizlik uchun)

4) BOT QANDAY ISHLAYDI:
   Botda pastki (doimiy) menyu tugmalari YO'Q. Foydalanuvchi /start bilan tilni
   tanlaydi (O'zbek / Rus / English / Deutsch), keyin faqat E'LONLAR orqali botdan
   foydalanadi: har bir e'lon ostida (admin tanlagan) "Buyurtma", "Narx", "Ma'lumot",
   "Joylashuv", "Aloqa" tugmalari chiqadi. "Buyurtma" tugmasi buyurtma jarayonini
   boshlaydi (miqdor -> manzil -> telefon), qolgan tugmalar admin oldindan yozib
   qo'ygan matnni ko'rsatadi.

5) E'LON YARATISH — bosqichma-bosqich: ADMIN_CHAT_ID sifatida ko'rsatilgan chatdan
   botga "/elon" (yoki "/e'lon") yuboring. Bot ketma-ket so'raydi:
     1) Rasm yuborasiz
     2) Qaysi tugmalar bo'lsin — Buyurtma, Narx, Ma'lumot, Joylashuv, Aloqa (bir
        nechtasini tanlash mumkin), so'ng "✅ Tayyor" tugmasini bosasiz
     3) "Buyurtma"dan tashqari har bir tanlangan tugma uchun matn kiritasiz
   Shundan so'ng e'lon (rasm + tugmalar) barcha ro'yxatdan o'tgan foydalanuvchilarga
   yuboriladi. Tugma nomlari har foydalanuvchining o'z tiliga (uz/ru/en/de) qarab
   avtomatik tarjima qilinadi.

6) Deploy qilgandan so'ng, Telegram webhookni shu manzilga ulang (brauzerda oching):
   https://api.telegram.org/bot<BOT_TOKEN>/setWebhook?url=https://<vercel-domeningiz>/api/index

Eslatma: Vercel serverless funksiyalari statesiz (har chaqiriqda "tozadan" ishga
tushadi), shuning uchun foydalanuvchi holati (til, buyurtma bosqichi, e'lon
jarayoni) Firebase Realtime Database orqali saqlanadi.
"""

import os
import json
import time
import random
import re
import string
from http.server import BaseHTTPRequestHandler

import requests

# ----------------------------------------------------------------------------
# SOZLAMALAR
# ----------------------------------------------------------------------------

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "")
FIREBASE_URL = os.environ.get("FIREBASE_URL", "").rstrip("/")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
EGG_PRICE = 1500  # 1 dona tuxum narxi (so'm) — xohlasangiz o'zgartiring

TEXTS = {
    "uz": {
        "choose_lang": "Tilni tanlang / Choose language / Выберите язык / Sprache wählen:",
        "welcome": "Assalomu alaykum, {name}! 🥚\nTuxum Market botiga xush kelibsiz.\nYangi e'lonlarni shu yerda ko'rasiz.",
        "ask_qty": "Nechta tuxum buyurtma qilmoqchisiz? (Sonini yozing, masalan: 30)",
        "invalid_qty": "Iltimos, faqat son kiriting (masalan: 30).",
        "ask_address": "Yetkazib berish manzilini yozing:",
        "ask_phone": "Telefon raqamingizni yuboring (masalan: +998901234567):",
        "order_done": "✅ Buyurtmangiz qabul qilindi!\n\n🥚 Miqdor: {qty} dona\n💵 Narx: {total} so'm\n📍 Manzil: {address}\n📱 Tel: {phone}\n\nTez orada operatorimiz siz bilan bog'lanadi!",
        "new_order_admin": "🆕 Yangi buyurtma!\n👤 {name} (@{username})\n🥚 {qty} dona — {total} so'm\n📍 {address}\n📱 {phone}",
        "unknown": "Kechirasiz, tushunmadim. Yangi e'lonni kuting yoki /start yozing.",
        "btn_buyurtma": "🛒 Buyurtma berish",
        "btn_narx": "💰 Narx",
        "btn_malumot": "ℹ️ Ma'lumot",
        "btn_joylashuv": "📍 Joylashuv",
        "btn_aloqa": "📞 Aloqa",
    },
    "ru": {
        "choose_lang": "Tilni tanlang / Choose language / Выберите язык / Sprache wählen:",
        "welcome": "Здравствуйте, {name}! 🥚\nДобро пожаловать в Tuxum Market.\nЗдесь вы будете видеть новые объявления.",
        "ask_qty": "Сколько яиц хотите заказать? (например: 30)",
        "invalid_qty": "Пожалуйста, введите число (например: 30).",
        "ask_address": "Введите адрес доставки:",
        "ask_phone": "Отправьте номер телефона (например: +998901234567):",
        "order_done": "✅ Ваш заказ принят!\n\n🥚 Количество: {qty} шт\n💵 Сумма: {total} сум\n📍 Адрес: {address}\n📱 Тел: {phone}\n\nНаш оператор скоро свяжется с вами!",
        "new_order_admin": "🆕 Новый заказ!\n👤 {name} (@{username})\n🥚 {qty} шт — {total} сум\n📍 {address}\n📱 {phone}",
        "unknown": "Извините, не понял. Ждите новое объявление или напишите /start.",
        "btn_buyurtma": "🛒 Заказать",
        "btn_narx": "💰 Цена",
        "btn_malumot": "ℹ️ Информация",
        "btn_joylashuv": "📍 Локация",
        "btn_aloqa": "📞 Контакты",
    },
    "en": {
        "choose_lang": "Tilni tanlang / Choose language / Выберите язык / Sprache wählen:",
        "welcome": "Hello, {name}! 🥚\nWelcome to Tuxum Market bot.\nYou'll see new announcements here.",
        "ask_qty": "How many eggs would you like to order? (e.g. 30)",
        "invalid_qty": "Please enter a number (e.g. 30).",
        "ask_address": "Enter delivery address:",
        "ask_phone": "Send your phone number (e.g. +998901234567):",
        "order_done": "✅ Your order has been placed!\n\n🥚 Qty: {qty}\n💵 Total: {total} UZS\n📍 Address: {address}\n📱 Phone: {phone}\n\nOur operator will contact you soon!",
        "new_order_admin": "🆕 New order!\n👤 {name} (@{username})\n🥚 {qty} pcs — {total} UZS\n📍 {address}\n📱 {phone}",
        "unknown": "Sorry, I didn't understand. Wait for a new announcement or type /start.",
        "btn_buyurtma": "🛒 Place order",
        "btn_narx": "💰 Price",
        "btn_malumot": "ℹ️ Info",
        "btn_joylashuv": "📍 Location",
        "btn_aloqa": "📞 Contact",
    },
    "de": {
        "choose_lang": "Tilni tanlang / Choose language / Выберите язык / Sprache wählen:",
        "welcome": "Hallo, {name}! 🥚\nWillkommen beim Tuxum Market Bot.\nNeue Ankündigungen finden Sie hier.",
        "ask_qty": "Wie viele Eier möchten Sie bestellen? (z. B. 30)",
        "invalid_qty": "Bitte geben Sie eine Zahl ein (z. B. 30).",
        "ask_address": "Geben Sie die Lieferadresse ein:",
        "ask_phone": "Senden Sie Ihre Telefonnummer (z. B. +998901234567):",
        "order_done": "✅ Ihre Bestellung wurde aufgegeben!\n\n🥚 Menge: {qty}\n💵 Summe: {total} UZS\n📍 Adresse: {address}\n📱 Telefon: {phone}\n\nUnser Operator wird sich bald bei Ihnen melden!",
        "new_order_admin": "🆕 Neue Bestellung!\n👤 {name} (@{username})\n🥚 {qty} Stk — {total} UZS\n📍 {address}\n📱 {phone}",
        "unknown": "Entschuldigung, das habe ich nicht verstanden. Warten Sie auf eine neue Ankündigung oder schreiben Sie /start.",
        "btn_buyurtma": "🛒 Bestellen",
        "btn_narx": "💰 Preis",
        "btn_malumot": "ℹ️ Info",
        "btn_joylashuv": "📍 Standort",
        "btn_aloqa": "📞 Kontakt",
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


def send_photo_by_file_id(chat_id, file_id, caption=""):
    payload = {"chat_id": chat_id, "photo": file_id}
    if caption:
        payload["caption"] = caption
    return tg_call("sendPhoto", payload)


def remove_keyboard():
    return {"remove_keyboard": True}


def lang_keyboard():
    return {
        "inline_keyboard": [
            [
                {"text": "🇺🇿 O'zbek", "callback_data": "lang_uz"},
                {"text": "🇷🇺 Русский", "callback_data": "lang_ru"},
            ],
            [
                {"text": "🇬🇧 English", "callback_data": "lang_en"},
                {"text": "🇩🇪 Deutsch", "callback_data": "lang_de"},
            ],
        ]
    }


def answer_callback_query(callback_query_id, text=None, show_alert=False):
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
        payload["show_alert"] = show_alert
    tg_call("answerCallbackQuery", payload)


def edit_message_reply_markup(chat_id, message_id, reply_markup):
    tg_call("editMessageReplyMarkup", {
        "chat_id": chat_id, "message_id": message_id, "reply_markup": reply_markup,
    })


# ----------------------------------------------------------------------------
# E'LON (BROADCAST) YARATISH — admin uchun bosqichma-bosqich oqim
# ----------------------------------------------------------------------------

# "buyurtma" — maxsus tugma: matn kiritilmaydi, bosilganda buyurtma jarayonini boshlaydi.
ANN_KEYS = ["buyurtma", "narx", "malumot", "joylashuv", "aloqa"]
ANN_ADMIN_LABELS = {
    "buyurtma": "🛒 Buyurtma berish",
    "narx": "💰 Narx",
    "malumot": "ℹ️ Ma'lumot",
    "joylashuv": "📍 Joylashuv",
    "aloqa": "📞 Aloqa",
}
ANN_ASK_TEXT = {
    "narx": "Narxni kiriting:",
    "malumot": "Ma'lumotni kiriting:",
    "joylashuv": "Joylashuvni kiriting:",
    "aloqa": "Aloqa ma'lumotini kiriting:",
}


def get_admin_broadcast(chat_id):
    return fb_get(f"admin_broadcast/{chat_id}") or {}


def set_admin_broadcast(chat_id, data):
    fb_set(f"admin_broadcast/{chat_id}", data)


def clear_admin_broadcast(chat_id):
    fb_set(f"admin_broadcast/{chat_id}", {})


def button_select_keyboard(selected):
    rows = []
    for key in ANN_KEYS:
        mark = "✅ " if key in selected else ""
        rows.append([{"text": f"{mark}{ANN_ADMIN_LABELS[key]}", "callback_data": f"elonbtn_{key}"}])
    rows.append([{"text": "✅ Tayyor", "callback_data": "elonbtn_done"}])
    return {"inline_keyboard": rows}


def announcement_view_keyboard(ann_id, selected_keys, lang):
    t = TEXTS[lang]
    label_map = {
        "buyurtma": t["btn_buyurtma"], "narx": t["btn_narx"], "malumot": t["btn_malumot"],
        "joylashuv": t["btn_joylashuv"], "aloqa": t["btn_aloqa"],
    }
    rows = [[{"text": label_map[key], "callback_data": f"annview_{ann_id}_{key}"}] for key in selected_keys]
    return {"inline_keyboard": rows}


# Arab/fors va boshqa unicode raqamlarni oddiy ASCII raqamlarga o'giradi
_DIGIT_MAP = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def parse_qty(text):
    """Matn ichidan butun sonni topib qaytaradi (masalan '30 dona' -> 30). Topilmasa None."""
    if not text:
        return None
    normalized = text.translate(_DIGIT_MAP)
    match = re.search(r"\d+", normalized)
    if not match:
        return None
    try:
        return int(match.group())
    except ValueError:
        return None


def start_order_flow(chat_id, state, lang):
    state["step"] = "await_qty"
    state["order"] = {}
    set_user_state(chat_id, state)
    send_message(chat_id, TEXTS[lang]["ask_qty"])


# ----------------------------------------------------------------------------
# ASOSIY UPDATE ISHLOVCHISI
# ----------------------------------------------------------------------------

def handle_update(update):
    if "callback_query" in update:
        cq = update["callback_query"]
        chat_id = cq["message"]["chat"]["id"]
        message_id = cq["message"]["message_id"]
        data = cq.get("data", "")
        cq_id = cq.get("id", "")

        if data.startswith("lang_"):
            lang = data.split("_", 1)[1]
            state = get_user_state(chat_id)
            state["lang"] = lang
            state["step"] = None
            set_user_state(chat_id, state)
            name = cq["from"].get("first_name", "")
            answer_callback_query(cq_id)
            send_message(chat_id, TEXTS[lang]["welcome"].format(name=name), remove_keyboard())
            return

        # --- Admin: e'lon uchun tugma tanlash (toggle) ---
        if data.startswith("elonbtn_") and ADMIN_CHAT_ID and str(chat_id) == str(ADMIN_CHAT_ID):
            bstate = get_admin_broadcast(chat_id)
            if bstate.get("step") != "wait_buttons":
                answer_callback_query(cq_id)
                return

            action = data[len("elonbtn_"):]
            selected = bstate.get("selected", [])

            if action == "done":
                if not selected:
                    answer_callback_query(cq_id, "Kamida bitta tugma tanlang!", show_alert=True)
                    return
                content_keys = [k for k in selected if k != "buyurtma"]
                bstate["content_keys"] = content_keys
                bstate["content_index"] = 0
                bstate["content"] = {}
                answer_callback_query(cq_id)
                if content_keys:
                    bstate["step"] = "wait_content"
                    set_admin_broadcast(chat_id, bstate)
                    send_message(chat_id, ANN_ASK_TEXT[content_keys[0]])
                else:
                    # Faqat "Buyurtma" tanlangan — matn kiritish shart emas, darhol yuboramiz
                    finalize_and_broadcast(chat_id, bstate, selected, {})
                return

            if action in selected:
                selected.remove(action)
            else:
                selected.append(action)
            bstate["selected"] = selected
            set_admin_broadcast(chat_id, bstate)
            edit_message_reply_markup(chat_id, message_id, button_select_keyboard(selected))
            answer_callback_query(cq_id)
            return

        # --- Har qanday foydalanuvchi: e'londagi tugmani bosganda ---
        if data.startswith("annview_"):
            rest = data[len("annview_"):]
            ann_id, _, key = rest.partition("_")
            answer_callback_query(cq_id)

            if key == "buyurtma":
                state = get_user_state(chat_id)
                lang = state.get("lang") or "uz"
                start_order_flow(chat_id, state, lang)
                return

            ann = fb_get(f"announcements/{ann_id}") or {}
            value = ann.get(key)
            if value:
                send_message(chat_id, value)
            return

        answer_callback_query(cq_id)
        return

    if "message" not in update:
        return

    msg = update["message"]
    chat_id = msg["chat"]["id"]
    text = msg.get("text", "")
    caption = msg.get("caption", "")
    photos = msg.get("photo")
    from_user = msg.get("from", {})
    name = from_user.get("first_name", "do'stim")
    username = from_user.get("username", "-")

    # --- ADMIN: E'lon yaratish oqimi ---
    if ADMIN_CHAT_ID and str(chat_id) == str(ADMIN_CHAT_ID):
        trigger_text = text if text else caption

        if trigger_text in ("/start", "/bekor", "/cancel"):
            clear_admin_broadcast(chat_id)
            # pastga tushib, oddiy foydalanuvchi oqimida /start qayta ishlanadi

        elif trigger_text.startswith("/elon") or trigger_text.startswith("/e'lon") or trigger_text.startswith("/e’lon"):
            clear_admin_broadcast(chat_id)
            set_admin_broadcast(chat_id, {"step": "wait_photo"})
            send_message(chat_id, "📸 E'lon uchun rasmni yuboring:")
            return

        else:
            bstate = get_admin_broadcast(chat_id)
            bstep = bstate.get("step")

            if bstep == "wait_photo":
                if photos:
                    bstate["photo_file_id"] = photos[-1]["file_id"]
                    bstate["step"] = "wait_buttons"
                    bstate["selected"] = []
                    set_admin_broadcast(chat_id, bstate)
                    send_message(chat_id, "Qaysi tugmalar bo'lsin? Kerakli tugmalarni bosing, so'ng \"Tayyor\"ni bosing:",
                                 button_select_keyboard([]))
                else:
                    send_message(chat_id, "Iltimos, rasm yuboring (jarayonni bekor qilish uchun /start yozing).")
                return

            if bstep == "wait_content":
                content_keys = bstate.get("content_keys", [])
                idx = bstate.get("content_index", 0)
                current_key = content_keys[idx]
                content = bstate.get("content", {})
                content[current_key] = text.strip()
                bstate["content"] = content
                idx += 1

                if idx < len(content_keys):
                    bstate["content_index"] = idx
                    set_admin_broadcast(chat_id, bstate)
                    send_message(chat_id, ANN_ASK_TEXT[content_keys[idx]])
                    return

                finalize_and_broadcast(chat_id, bstate, bstate.get("selected", []), content)
                return

    state = get_user_state(chat_id)
    lang = state.get("lang")

    # Til tanlanmagan bo'lsa — birinchi navbatda tilni so'raymiz
    if not lang:
        send_message(chat_id, TEXTS["uz"]["choose_lang"], lang_keyboard())
        return

    t = TEXTS[lang]
    step = state.get("step")

    # --- /start har doim joriy jarayonni bekor qilib, til tanlashni ko'rsatadi ---
    if text == "/start":
        state["step"] = None
        state["order"] = {}
        set_user_state(chat_id, state)
        send_message(chat_id, TEXTS["uz"]["choose_lang"], lang_keyboard())
        return

    if text in ("/bekor", "/cancel"):
        state["step"] = None
        state["order"] = {}
        set_user_state(chat_id, state)
        send_message(chat_id, t["welcome"].format(name=name), remove_keyboard())
        return

    if text == "/til":
        send_message(chat_id, TEXTS["uz"]["choose_lang"], lang_keyboard())
        return

    # --- Buyurtma bosqichlari ---
    if step == "await_qty":
        qty = parse_qty(text)
        if qty is not None and qty > 0:
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
        ))
        if ADMIN_CHAT_ID:
            send_message(ADMIN_CHAT_ID, t["new_order_admin"].format(
                name=name, username=username, qty=order["qty"],
                total=order["total"], address=order["address"], phone=order["phone"],
            ))
        state["step"] = None
        state["order"] = {}
        set_user_state(chat_id, state)
        return

    # --- Boshqa har qanday xabar ---
    send_message(chat_id, t["unknown"])


def finalize_and_broadcast(admin_chat_id, bstate, selected, content):
    """E'lonni Firebase'ga saqlaydi va barcha foydalanuvchilarga yuboradi."""
    ann_id = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    fb_set(f"announcements/{ann_id}", content)

    all_users = fb_get("users") or {}
    sent, failed = 0, 0
    for uid, ustate in all_users.items():
        ulang = (ustate or {}).get("lang") or "uz"
        kb = announcement_view_keyboard(ann_id, selected, ulang)
        res = send_photo_by_file_id(uid, bstate["photo_file_id"], caption="")
        if res and res.get("ok"):
            tg_call("sendMessage", {"chat_id": uid, "text": "👇", "reply_markup": kb})
            sent += 1
        else:
            failed += 1

    clear_admin_broadcast(admin_chat_id)
    send_message(admin_chat_id, f"✅ E'lon yuborildi.\nMuvaffaqiyatli: {sent}\nXato: {failed}")


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
