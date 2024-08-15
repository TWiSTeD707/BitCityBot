from aiogram import types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from loader import dp
from parser import get_crypto_rate
import random
from datetime import datetime, timedelta
import sqlite3

# Комиссионные ставки
commission_rates = {
    "btc_card": [
        {"threshold": 50000, "rate": 0.07},
        {"threshold": 100000, "rate": 0.05},
        {"threshold": float('inf'), "rate": 0.04}
    ],
    "btc_sbp": [
        {"threshold": 150000, "rate": 0.05},
        {"threshold": 500000, "rate": 0.04},
        {"threshold": float('inf'), "rate": 0.035}
    ],
    "btc_tinkoff_qr": [
        {"threshold": 100000, "rate": 0.06}
    ],
    "btc_cash_msk_mo": [
        {"threshold": 1000000, "rate": 0.05},
        {"threshold": float('inf'), "rate": 0.04}
    ],
    "exchange": [
        {"threshold": 50000, "rate": 0.06},
        {"threshold": 100000, "rate": 0.04},
        {"threshold": 1000000, "rate": 0.03},
        {"threshold": float('inf'), "rate": 0.02}
    ],
    "btc_btc": [
        {"threshold": float('inf'), "rate": 0.025}
    ]
}


# Состояния FSM
class TransactionStates(StatesGroup):
    waiting_for_btc_amount = State()
    waiting_for_card_number = State()
    waiting_for_confirmation = State()


# Функция для генерации уникального ID заявки
def generate_order_id():
    return f"{random.randint(1, 500)}{random.randint(1, 500)}{random.randint(1, 500)}"


# Функция для расчета суммы с учетом комиссии
def calculate_received_amount(btc_amount, commission_rate):
    return round(btc_amount * (1 - commission_rate), 8)


def get_commission_text(option):
    """ Возвращает текст с комиссионными ставками для выбранного способа оплаты или обмена, округляя до десятых. """
    text = ""
    for commission in commission_rates[option]:
        rounded_rate = round(commission['rate'] * 100, 1)  # Округляем до десятых
        if commission['threshold'] == float('inf'):
            if option == "exchange":
                text += f"Свыше {int(commission_rates[option][-2]['threshold'])} руб - {rounded_rate}%\n"
            else:
                text += f"От {int(commission_rates[option][-2]['threshold'])} руб и выше - {rounded_rate}%\n"
        else:
            if option == "btc_btc":
                text = f"BTC - BTC - {rounded_rate}% любые суммы\n"
            elif option == "exchange":
                text += f"До {int(commission['threshold'])} руб - {rounded_rate}%\n"
            else:
                text += f"До {int(commission['threshold'])} руб - {rounded_rate}%\n"
    return text



# Создание подключения к базе данных
def create_connection():
    conn = sqlite3.connect('clients.db')
    return conn


def create_table():
    conn = create_connection()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT UNIQUE NOT NULL,
            user_id INTEGER NOT NULL,
            amount_btc REAL NOT NULL,
            card_number TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


# Сохранение заявки в базу данных
def save_transaction_to_db(request_id, user_id, amount_btc, card_number, status='pending'):
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO transactions (request_id, user_id, amount_btc, card_number, status)
        VALUES (?, ?, ?, ?, ?)
    ''', (request_id, user_id, amount_btc, card_number, status))
    conn.commit()
    conn.close()


# Получение всех заявок пользователя
def get_user_transactions(user_id):
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT request_id FROM transactions WHERE user_id = ?
    ''', (user_id,))
    transactions = cursor.fetchall()
    conn.close()
    return transactions


# Получение информации о конкретной заявке
def get_transaction_info(request_id):
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM transactions WHERE request_id = ?
    ''', (request_id,))
    transaction = cursor.fetchone()
    conn.close()
    return transaction


async def process_history(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    transactions = get_user_transactions(user_id)

    if not transactions:
        await callback_query.message.edit_text("У вас нет истории заявок.", reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="back")]]
        ))
        return

    history_text = "История ваших заявок:\n"
    for transaction in transactions:
        history_text += f"ID заявки: {transaction[0]}\n"

    await callback_query.message.edit_text(history_text, reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="back")]]
    ))


@dp.callback_query(lambda c: c.data in ["exchange", "history", "operator"])
async def process_option(callback_query: types.CallbackQuery):
    if callback_query.data == "exchange":
        exchange_menu = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Продать за рубли", callback_data="sell")],
            [InlineKeyboardButton(text="Чистка", callback_data="clean")],
            [InlineKeyboardButton(text="Назад", callback_data="back")]
        ])
        await callback_query.message.edit_text("Выберите нужное действие:", reply_markup=exchange_menu)
    elif callback_query.data == "history":
        await process_history(callback_query)
    elif callback_query.data == "operator":
        await callback_query.message.edit_text("Оператор: +123456789",
                                               reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                                   [InlineKeyboardButton(text="Назад", callback_data="back")]
                                               ]))


@dp.callback_query(lambda c: c.data == "sell")
async def process_sell(callback_query: types.CallbackQuery):
    payment_menu = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="BTC - банковская карта", callback_data="btc_card")],
        [InlineKeyboardButton(text="BTC - СБП", callback_data="btc_sbp")],
        [InlineKeyboardButton(text="BTC - Тинькофф QR", callback_data="btc_tinkoff_qr")],
        [InlineKeyboardButton(text="BTC - Наличные - МСК/МО", callback_data="btc_cash_msk_mo")],
        [InlineKeyboardButton(text="Назад", callback_data="back")]
    ])
    await callback_query.message.edit_text("Выберите нужный способ оплаты:", reply_markup=payment_menu)


@dp.callback_query(lambda c: c.data == "clean")
async def process_clean(callback_query: types.CallbackQuery):
    exchange_methods_menu = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="USDT TRC20", callback_data="usdt_trc20")],
        [InlineKeyboardButton(text="BTC", callback_data="btc")],
        [InlineKeyboardButton(text="LTC", callback_data="ltc")],
        [InlineKeyboardButton(text="XMR", callback_data="xmr")],
        [InlineKeyboardButton(text="ETH", callback_data="eth")],
        [InlineKeyboardButton(text="Оператор", callback_data="operator")],
        [InlineKeyboardButton(text="Назад", callback_data="back")]
    ])
    await callback_query.message.edit_text("Выберите нужный способ обмена:", reply_markup=exchange_methods_menu)


@dp.callback_query(lambda c: c.data in ["btc_card", "btc_sbp"])
async def process_currency_selection(callback_query: types.CallbackQuery):
    commission_text = get_commission_text(callback_query.data)
    currency_menu = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Bitcoin", callback_data="currency_btc")],
        [InlineKeyboardButton(text="Rub", callback_data="currency_rub")],
        [InlineKeyboardButton(text="Назад", callback_data="back_to_payment")]
    ])
    await callback_query.message.edit_text(f"В какой валюте Вы указываете сумму?\n\nКомиссия:\n{commission_text}",
                                           reply_markup=currency_menu)


@dp.callback_query(lambda c: c.data == "currency_btc")
async def process_btc_amount(callback_query: types.CallbackQuery, state: FSMContext):
    rate = get_crypto_rate("bitcoin", "rub")
    min_btc_amount = round(5000 / rate, 7)
    cancel_menu = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Отмена операции", callback_data="cancel_operation")],
        [InlineKeyboardButton(text="Назад", callback_data="back_to_payment")]
    ])
    await callback_query.message.edit_text(
        f"Введите сумму BTC, которую хотите продать.✅\n\n"
        f"❗Важно❗\n"
        f"Минимальная сумма обмена: {min_btc_amount} BTC на 5000 руб.\n\n"
        f"Пример: \n0.0135",
        reply_markup=cancel_menu
    )
    await state.set_state(TransactionStates.waiting_for_btc_amount)


@dp.message(StateFilter(TransactionStates.waiting_for_btc_amount))
async def process_btc_amount_input(message: types.Message, state: FSMContext):
    rate = get_crypto_rate("bitcoin", "rub")
    min_btc_amount = round(5000 / rate, 7)

    try:
        btc_amount = float(message.text)
        if btc_amount < min_btc_amount:
            await message.reply(f"Введите сумму больше минимальной ({min_btc_amount} BTC).")
            return
    except ValueError:
        await message.reply("Введите правильное число, как в примере: 0.0135")
        return

    await state.update_data(btc_amount=btc_amount)
    await message.answer("Введите номер карты, на которую хотите получить деньги.\nПример: 2200202520262027", reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="back_to_btc_amount")]]
    ))
    await state.set_state(TransactionStates.waiting_for_card_number)

@dp.message(StateFilter(TransactionStates.waiting_for_card_number))
async def process_card_number_input(message: types.Message, state: FSMContext):
    card_number = message.text.strip()

    if not card_number.isdigit() or len(card_number) < 16:
        await message.reply("Введите правильный номер карты, состоящий из минимум 16 цифр.")
        return

    await state.update_data(card_number=card_number)
    data = await state.get_data()
    btc_amount = data['btc_amount']
    selected_option = 'btc_card'  # For example, you can store this in the state during the flow
    commission_rate = commission_rates[selected_option][0]['rate']  # Example logic
    received_amount = calculate_received_amount(btc_amount, commission_rate)

    order_id = generate_order_id()
    expiration_time = (datetime.now() + timedelta(minutes=30)).strftime('%m-%d %H:%M:%S')

    order_text = (
        f"Заявка #{order_id}\n\n"
        f"Направление обмена: {selected_option.replace('_', ' ').upper()}\n\n"
        f"Отдаете: {btc_amount} BTC\n"
        f"Получаете: {received_amount} BTC\n\n"
        f"Ваши реквизиты:\n{card_number}\n\n"
        f"❗Важно:❗\n"
        f"На оплату обмена дается 30 минут.\n"
        f"Совершите перевод до {expiration_time}, в противном случае заявка будет отменена!\n\n"
        "- подтверждаю✅\n"
        "- отмена❌ (возврат на главную)"
    )

    confirmation_menu = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Подтверждаю", callback_data="confirm_transaction")],
        [InlineKeyboardButton(text="Отмена", callback_data="cancel_operation")]
    ])
    await message.answer(order_text, reply_markup=confirmation_menu)
    await state.set_state(TransactionStates.waiting_for_confirmation)


@dp.callback_query(lambda c: c.data == "confirm_transaction")
async def process_confirm_transaction(callback_query: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    order_id = generate_order_id()
    user_id = callback_query.from_user.id
    btc_amount = data['btc_amount']
    card_number = data['card_number']

    # Сохраняем заявку в базу данных
    save_transaction_to_db(order_id, user_id, btc_amount, card_number)

    # Сообщение об успешной заявке
    await callback_query.message.edit_text(
        f"Заявка #{order_id} успешно подтверждена!\n\n"
        f"Вы получите {calculate_received_amount(btc_amount, commission_rates['btc_card'][0]['rate'])} BTC на карту {card_number}.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Назад", callback_data="back")]
        ])
    )
    await state.clear()  # Очищаем состояние FSM после подтверждения заявки


@dp.callback_query(lambda c: c.data == "cancel_operation")
async def process_cancel_operation(callback_query: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback_query.message.edit_text("Операция отменена.", reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Назад в главное меню", callback_data="back")]]
    ))

@dp.callback_query(lambda c: c.data == "cancel_operation")
async def process_transaction_cancellation(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.message.edit_text("Операция отменена.")
    await state.clear()


@dp.callback_query(lambda c: c.data == "back_to_payment")
async def process_back_to_payment(callback_query: types.CallbackQuery, state: FSMContext):
    await process_sell(callback_query)  # Возвращаемся на экран выбора способа оплаты


@dp.callback_query(lambda c: c.data == "back_to_btc_amount")
async def process_back_to_btc_amount(callback_query: types.CallbackQuery, state: FSMContext):
    await process_btc_amount(callback_query, state)  # Возвращаемся на экран ввода суммы BTC


@dp.callback_query(lambda c: c.data == "cancel_operation")
async def process_cancel_operation(callback_query: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback_query.message.edit_text("Операция отменена.", reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Назад в главное меню", callback_data="back")]]
    ))


@dp.callback_query(lambda c: c.data == "back")
async def process_back_to_main(callback_query: types.CallbackQuery, state: FSMContext):
    main_menu = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Обмен", callback_data="exchange")],
        [InlineKeyboardButton(text="История заявок", callback_data="history")],
        [InlineKeyboardButton(text="Оператор", callback_data="operator")]
    ])
    await callback_query.message.edit_text("Привет! Выберите опцию:", reply_markup=main_menu)


# Запуск базы данных при старте
create_table()
