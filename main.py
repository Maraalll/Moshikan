import asyncio
import re
import gspread
from oauth2client.service_account import ServiceAccountCredentials

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# ======================================================
#                     CONFIG
# ======================================================

BOT_TOKEN = "8192699182:AAFI5QwrdgJo8HoS9eMRPLiU_bDJIANryvc"
CREDS_FILE = "marok03-e0cf4728a691.json"
PAYMENT_SHEET_ID = "1kHRGjFQe7I-ZOdvhPkDKqgjdPCbG3zbSYsVVDx_WMBo"
FORM_ANSWERS_SHEET_ID = "1gXsBBebkkkNSSOoAw_Ty_-wEaCUfcbOo5rkTg5aX7a8"
FORM_URL = "https://forms.gle/48LHKVj1vUwAQbyx8"  # ТВОЯ Google Form


# ======================================================
#                GOOGLE SHEETS CONNECT
# ======================================================

def gsheets_connect():
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, scope)
    client = gspread.authorize(creds)
    return client.open_by_key(PAYMENT_SHEET_ID).sheet1


payment_sheet = gsheets_connect()

def connect_form_answers():
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(FORM_ANSWERS_SHEET_ID).sheet1
    return sheet

form_sheet = connect_form_answers()


# ======================================================
#                IMPORT TEST QUESTIONS
# ======================================================

from questions import KZ_TEST, RU_TEST


# ======================================================
#                     FSM STATES
# ======================================================

class Quiz(StatesGroup):
    lang = State()
    fio = State()
    phone = State()
    ready = State()
    quiz = State()
    finish = State()


# ======================================================
#                     BOT INIT
# ======================================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


# ======================================================
#                     KEYBOARDS
# ======================================================

lang_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Қазақша"), KeyboardButton(text="Русский")]],
    resize_keyboard=True
)

def yes_no_kb(lang):
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Иә" if lang == "қазақша" else "Да"),
             KeyboardButton(text="Жоқ" if lang == "қазақша" else "Нет")]
        ],
        resize_keyboard=True
    )

def abcd_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="A"), KeyboardButton(text="B"),
                  KeyboardButton(text="C"), KeyboardButton(text="D")]],
        resize_keyboard=True
    )


# ======================================================
#                      START
# ======================================================

@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🇰🇿 Тілді таңдаңыз\n🇷🇺 Выберите язык:",
        reply_markup=lang_kb
    )
    await state.set_state(Quiz.lang)


# ======================================================
#                     LANGUAGE
# ======================================================

@dp.message(Quiz.lang)
async def choose_language(message: Message, state: FSMContext):
    lang = message.text.lower()
    if lang not in ["қазақша", "русский"]:
        return await message.answer("❗ Тілді дұрыс таңдаңыз / Выберите язык правильно.")

    await state.update_data(lang=lang)

    text = "✍️ Атыңызды енгізіңіз:" if lang == "қазақша" else "✍️ Введите ваше ФИО:"
    await message.answer(text, reply_markup=ReplyKeyboardRemove())
    await state.set_state(Quiz.fio)


# ======================================================
#                       FIO
# ======================================================

@dp.message(Quiz.fio)
async def get_fio(message: Message, state: FSMContext):
    await state.update_data(fio=message.text)
    data = await state.get_data()

    text = ("📞 Телефон нөмірін енгізіңіз (8XXXXXXXXXX):"
            if data["lang"] == "қазақша"
            else "📞 Введите номер телефона (8XXXXXXXXXX):")

    await message.answer(text)
    await state.set_state(Quiz.phone)


# ======================================================
#                    PHONE + PAYMENT CHECK
# ======================================================

@dp.message(Quiz.phone)
async def get_phone(message: Message, state: FSMContext):
    phone = re.sub(r"\D", "", message.text)

    if len(phone) < 10:
        return await message.answer("❗ Телефон форматы дұрыс емес.")

    await state.update_data(phone=phone)
    data = await state.get_data()

    # WAIT MESSAGE
    wait_msg = await message.answer(
        "⏳ Төлем тексерілуде..." if data["lang"] == "қазақша"
        else "⏳ Проверяем оплату..."
    )

    # ---- ЧТЕНИЕ СТОЛБЦА 'Мобильный' ----
    header = payment_sheet.row_values(2)
    normalized = [col.strip().replace("\xa0", "").lower() for col in header]

    try:
        col_index = normalized.index("мобильный") + 1
    except ValueError:
        await message.answer("❗ Қате: 'Мобильный' табылмады.")
        return

    mobiles = payment_sheet.col_values(col_index)[2:]  # начиная с 3 строки

    phone_clean = phone[-10:]

    paid = any(
        re.sub(r"\D", "", m).endswith(phone_clean) for m in mobiles
    )

    # удалить сообщение “подождите”
    try:
        await bot.delete_message(message.chat.id, wait_msg.message_id)
    except:
        pass

    # ---- РЕЗУЛЬТАТ ----
    if not paid:
        return await message.answer(
            "❌ Төлем табылмады." if data["lang"] == "қазақша"
            else "❌ Оплата не найдена."
        )

    # SUCCESS
    text = ("✔ Төлем расталды! Тестті бастауға дайынсыз ба?"
            if data["lang"] == "қазақша"
            else "✔ Оплата найдена! Вы готовы начать тест?")

    await message.answer(text, reply_markup=yes_no_kb(data["lang"]))
    await state.set_state(Quiz.ready)


# ======================================================
#                    READY TO START
# ======================================================

@dp.message(Quiz.ready)
async def ready_to_start(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data["lang"]

    txt = message.text.lower()

    yes = "иә" if lang == "қазақша" else "да"
    no = "жоқ" if lang == "қазақша" else "нет"

    if txt == no:
        return await message.answer(
            "Жарайды, дайын болғанда /start теріңіз."
            if lang == "қазақша"
            else "Хорошо, когда будете готовы — введите /start.",
            reply_markup=ReplyKeyboardRemove()
        )

    if txt != yes:
        return

    await state.update_data(q=0, correct=0)
    await state.set_state(Quiz.quiz)

    await send_question(message, state)


# ======================================================
#                    SEND QUESTION
# ======================================================

async def send_question(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data["lang"]
    idx = data["q"]

    test = KZ_TEST if lang == "қазақша" else RU_TEST

    if idx >= len(test):
        return await finish_quiz(message, state)

    q = test[idx]

    text = (
        f"❓ *{idx+1}-сұрақ*\n\n{q['q']}\n\nA) {q['A']}\nB) {q['B']}\nC) {q['C']}\nD) {q['D']}"
        if lang == "қазақша" else
        f"❓ *Вопрос {idx+1}*\n\n{q['q']}\n\nA) {q['A']}\nB) {q['B']}\nC) {q['C']}\nD) {q['D']}"
    )

    await message.answer(text, parse_mode="Markdown", reply_markup=abcd_kb())


# ======================================================
#                 PROCESS ANSWER
# ======================================================

@dp.message(Quiz.quiz)
async def process_answer(message: Message, state: FSMContext):
    ans = message.text.upper().strip()
    if ans not in ["A", "B", "C", "D"]:
        return

    data = await state.get_data()
    lang = data["lang"]
    idx = data["q"]
    test = KZ_TEST if lang == "қазақша" else RU_TEST

    if ans == test[idx]["correct"]:
        await state.update_data(correct=data["correct"] + 1)

    await state.update_data(q=idx + 1)

    await send_question(message, state)


# ======================================================
#                    FINISH QUIZ
# ======================================================

async def finish_quiz(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data["lang"]
    score = data["correct"]
    total = len(KZ_TEST) if lang=="қазақша" else len(RU_TEST)

    msg = (
        f"🎉 Тест аяқталды!\nДұрыс жауап: {score}/{total}\n\nСертификат алу үшңн форманы толтырыңыз:\n{FORM_URL}"
        if lang == "қазақша"
        else f"🎉 Тест завершён!\nПравильных ответов: {score}/{total}\n\nДля получение сертификата заполните форму:\n{FORM_URL}"
    )

    await message.answer(msg, reply_markup=ReplyKeyboardRemove())
    phone = data.get("phone", "")
    phone_clean = phone[-10:]  # последние 10 цифр
    
    # читаем строки формы
    rows = form_sheet.get_all_values()

    # ищем пользователя по телефону (колонка C = index 2)
    for i, row in enumerate(rows):
        if len(row) < 3:
            continue

        row_phone = re.sub(r"\D", "", row[2])
        if row_phone.endswith(phone_clean):
            # записываем баллы в колонку D (index 3)
            score_value = f"{score}/{total}"
            form_sheet.update_cell(i + 1, 4, score_value)
            print(f"Баллы {score_value} записаны в строку {i+1}")
            break
    await state.clear()


# ======================================================
#                        RUN BOT
# ======================================================

async def main():
    print("Бот запущен ✓")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
