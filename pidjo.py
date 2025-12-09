import logging
import sqlite3
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters, ConversationHandler

# Константы для состояний разговора
(PURCHASE_DATE, PURCHASE_NAME, PURCHASE_COLOR, PURCHASE_SIZE, 
 PURCHASE_QUANTITY, PURCHASE_PRICE, SALE_PRICE, SALE_METHOD, PASSWORD_INPUT) = range(9)

# Константа для размера страницы
ITEMS_PER_PAGE = 50

# Пароль для доступа к боту
BOT_PASSWORD = "MaidanNavalny2018"

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def format_number(number):
    """Форматирование числа с разделителями тысяч"""
    if number is None:
        return "0"
    return f"{number:,.2f}".replace(",", " ").replace(".", ",")

def format_int(number):
    """Форматирование целого числа с разделителями тысяч"""
    if number is None:
        return "0"
    return f"{int(number):,}".replace(",", " ")

class BusinessBot:
    def __init__(self, token: str):
        self.token = token
        self.db_path = 'business_bot.db'
        self.init_database()

    def init_database(self):
        """Инициализация базы данных"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        
        # Таблица авторизованных пользователей
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS authorized_users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                authorized_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

# Таблица закупок
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                name TEXT NOT NULL,
                color TEXT NOT NULL,
                size TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                price_per_unit REAL NOT NULL,
                total_cost REAL NOT NULL,
                remaining_quantity INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Проверяем наличие таблицы sales и столбца sale_method
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sales'")
        table_exists = cursor.fetchone()

        if table_exists:
            cursor.execute("PRAGMA table_info(sales)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'sale_method' not in columns:
                # Добавляем столбец sale_method
                cursor.execute("ALTER TABLE sales ADD COLUMN sale_method TEXT NOT NULL DEFAULT 'delivery'")
        else:
            # Создаем таблицу sales с нуля
            cursor.execute("""
                CREATE TABLE sales (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    purchase_id INTEGER NOT NULL,
                    sale_date TEXT NOT NULL,
                    quantity_sold INTEGER NOT NULL,
                    sale_price_per_unit REAL NOT NULL,
                    total_sale REAL NOT NULL,
                    profit REAL NOT NULL,
                    days_to_sell INTEGER NOT NULL,
                    sale_method TEXT NOT NULL DEFAULT 'delivery',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (purchase_id) REFERENCES purchases (id)
                )
            """)

        conn.commit()
        conn.close()

    def is_user_authorized(self, user_id: int) -> bool:
        """Проверка авторизации пользователя"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM authorized_users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result is not None

    def authorize_user(self, user_id: int, username: str = None, first_name: str = None):
        """Авторизация пользователя"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO authorized_users (user_id, username, first_name)
            VALUES (?, ?, ?)
        """, (user_id, username, first_name))
        conn.commit()
        conn.close()

    def get_main_keyboard(self):
        """Главная клавиатура"""
        keyboard = [
            [KeyboardButton("📦 Добавить закупку"), KeyboardButton("💰 Добавить продажу")],
            [KeyboardButton("🛍 Продажи по вещам"), KeyboardButton("📊 Продажи")],
            [KeyboardButton("📋 Остатки"), KeyboardButton("⚡️ Ликвидность")],
            [KeyboardButton("🗑 Удалить запись"), KeyboardButton("📈 Статистика")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    def get_back_keyboard(self):
        """Клавиатура с кнопкой назад"""
        keyboard = [[KeyboardButton("◀️ Назад")]]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    def get_period_keyboard(self):
        """Клавиатура для выбора периода"""
        keyboard = [
            [InlineKeyboardButton("📅 Сегодня", callback_data="period_today")],
            [InlineKeyboardButton("📅 Неделя", callback_data="period_week")],
            [InlineKeyboardButton("📅 2 недели", callback_data="period_2weeks")],
            [InlineKeyboardButton("📅 Месяц", callback_data="period_month")],
            [InlineKeyboardButton("📅 Текущий месяц", callback_data="period_current_month")],
            [InlineKeyboardButton("📆 Выбрать месяц", callback_data="select_month")],
            [InlineKeyboardButton("📅 Всё время", callback_data="period_all")]
        ]
        return InlineKeyboardMarkup(keyboard)

    def get_month_keyboard(self):
        """Клавиатура для выбора месяца"""
        months = [
            ("Январь", 1), ("Февраль", 2), ("Март", 3),
            ("Апрель", 4), ("Май", 5), ("Июнь", 6),
            ("Июль", 7), ("Август", 8), ("Сентябрь", 9),
            ("Октябрь", 10), ("Ноябрь", 11), ("Декабрь", 12)
        ]

        keyboard = []
        row = []
        for name, num in months:
            row.append(InlineKeyboardButton(name, callback_data=f"month_{num}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_periods")])
        return InlineKeyboardMarkup(keyboard)

    def get_year_keyboard(self):
        """Клавиатура для выбора года"""
        current_year = datetime.now().year
        years = list(range(current_year, current_year - 3, -1))

        keyboard = []
        for year in years:
            keyboard.append([InlineKeyboardButton(str(year), callback_data=f"year_{year}")])

        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_months")])
        return InlineKeyboardMarkup(keyboard)

# Создаем экземпляр бота
bot = BusinessBot("8339672379:AAGzgFgA_Lj34sfwHn6NXLRYY0Fwlx25R4A")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user_id = update.effective_user.id
    if not bot.is_user_authorized(user_id):
        await update.message.reply_text("🔐 Для доступа к боту введите пароль:", parse_mode='HTML')
        return PASSWORD_INPUT
    welcome_text = "🤖 Бот учета бизнеса\n\nВыберите действие:"
    await update.message.reply_text(welcome_text, reply_markup=bot.get_main_keyboard(), parse_mode='HTML')
    return ConversationHandler.END

async def check_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка пароля"""
    user_id = update.effective_user.id
    password = update.message.text.strip()
    if password == BOT_PASSWORD:
        bot.authorize_user(user_id, update.effective_user.username, update.effective_user.first_name)
        await update.message.reply_text("✅ Доступ разрешен!\n\n🤖 Бот учета бизнеса\n\nВыберите действие:", reply_markup=bot.get_main_keyboard(), parse_mode='HTML')
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ Неверный пароль. Попробуйте еще раз:", parse_mode='HTML')
        return PASSWORD_INPUT

async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка главного меню"""
    user_id = update.effective_user.id
    if not bot.is_user_authorized(user_id):
        await update.message.reply_text("🔐 Для доступа к боту используйте команду /start", parse_mode='HTML')
        return
    text = update.message.text.lower()

    if "добавить закупку" in text:
        return await start_purchase(update, context)
    elif "добавить продажу" in text:
        return await start_sale(update, context)
    elif "продажи по вещам" in text:
        return await show_items_for_sales(update, context)
    elif "продажи" in text:
        return await show_sales_menu(update, context)
    elif "остатки" in text:
        return await show_inventory(update, context)
    elif "ликвидность" in text:
        return await show_liquidity(update, context)
    elif "удалить запись" in text:
        return await delete_record_menu(update, context)
    elif "статистика" in text:
        return await show_sales_statistics(update, context)
    elif "назад" in text:
        return await start(update, context)

# Обработчики для добавления закупки
async def start_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало добавления закупки"""
    await update.message.reply_text(
        "📦 Новая закупка\n\nВведите дату (ДД.ММ.ГГГГ) или 'сегодня':",
        reply_markup=bot.get_back_keyboard(),
        parse_mode='HTML'
    )
    return PURCHASE_DATE

async def purchase_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка даты закупки"""
    if "назад" in update.message.text.lower():
        await update.message.reply_text("🏠 Главное меню:", reply_markup=bot.get_main_keyboard())
        return ConversationHandler.END

    try:
        if update.message.text.lower() == "сегодня":
            date_str = datetime.now().strftime("%d.%m.%Y")
        else:
            date_obj = datetime.strptime(update.message.text, "%d.%m.%Y")
            date_str = update.message.text

        context.user_data['purchase_date'] = date_str
        await update.message.reply_text("🏷 Введите название товара:")
        return PURCHASE_NAME
    except ValueError:
        await update.message.reply_text("❌ Неверный формат. Используйте ДД.ММ.ГГГГ или 'сегодня':")
        return PURCHASE_DATE

async def purchase_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка названия товара"""
    if "назад" in update.message.text.lower():
        await update.message.reply_text("🏠 Главное меню:", reply_markup=bot.get_main_keyboard())
        return ConversationHandler.END

    context.user_data['purchase_name'] = update.message.text
    await update.message.reply_text("🎨 Введите цвет товара:")
    return PURCHASE_COLOR

async def purchase_color(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка цвета товара"""
    if "назад" in update.message.text.lower():
        await update.message.reply_text("🏠 Главное меню:", reply_markup=bot.get_main_keyboard())
        return ConversationHandler.END

    context.user_data['purchase_color'] = update.message.text
    await update.message.reply_text("📏 Введите размер товара:")
    return PURCHASE_SIZE

async def purchase_size(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка размера товара"""
    if "назад" in update.message.text.lower():
        await update.message.reply_text("🏠 Главное меню:", reply_markup=bot.get_main_keyboard())
        return ConversationHandler.END

    context.user_data['purchase_size'] = update.message.text
    await update.message.reply_text("🔢 Введите количество:")
    return PURCHASE_QUANTITY

async def purchase_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка количества товара"""
    if "назад" in update.message.text.lower():
        await update.message.reply_text("🏠 Главное меню:", reply_markup=bot.get_main_keyboard())
        return ConversationHandler.END

    try:
        quantity = int(update.message.text)
        if quantity <= 0:
            raise ValueError

        context.user_data['purchase_quantity'] = quantity
        await update.message.reply_text("💸 Введите цену за штуку:")
        return PURCHASE_PRICE
    except ValueError:
        await update.message.reply_text("❌ Введите корректное количество:")
        return PURCHASE_QUANTITY

async def purchase_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка цены товара и сохранение закупки"""
    if "назад" in update.message.text.lower():
        await update.message.reply_text("🏠 Главное меню:", reply_markup=bot.get_main_keyboard())
        return ConversationHandler.END

    try:
        price = float(update.message.text.replace(',', '.'))
        if price <= 0:
            raise ValueError

        conn = sqlite3.connect(bot.db_path)
        cursor = conn.cursor()

        total_cost = price * context.user_data['purchase_quantity']

        cursor.execute("""
            INSERT INTO purchases (date, name, color, size, quantity, price_per_unit, total_cost, remaining_quantity)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            context.user_data['purchase_date'],
            context.user_data['purchase_name'].lower(),
            context.user_data['purchase_color'].lower(),
            context.user_data['purchase_size'].lower(),
            context.user_data['purchase_quantity'],
            price,
            total_cost,
            context.user_data['purchase_quantity']
        ))

        conn.commit()
        conn.close()

        success_message = f"✅ Закупка добавлена\n\n📅 {context.user_data['purchase_date']}\n🏷 {context.user_data['purchase_name']} | {context.user_data['purchase_color']} | {context.user_data['purchase_size']}\n🔢 Количество: {context.user_data['purchase_quantity']} шт\n💸 Цена: {format_number(price)} ₽/шт\n💰 Общая стоимость: {format_number(total_cost)} ₽"

        await update.message.reply_text(
            success_message,
            reply_markup=bot.get_main_keyboard(),
            parse_mode='HTML'
        )

        context.user_data.clear()
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Введите корректную цену:")
        return PURCHASE_PRICE

# Обработчики для продаж с пагинацией
async def start_sale(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    """Начало процесса продажи с пагинацией"""
    conn = sqlite3.connect(bot.db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, date, name, color, size, remaining_quantity, price_per_unit
        FROM purchases
        WHERE remaining_quantity > 0
        ORDER BY datetime(substr(date, 7, 4) || '-' || substr(date, 4, 2) || '-' || substr(date, 1, 2)) DESC, name ASC
    """)
    items = cursor.fetchall()
    conn.close()

    if not items:
        await update.message.reply_text(
            "❌ Нет товаров в остатках для продажи",
            reply_markup=bot.get_main_keyboard()
        )
        return

    # Пагинация
    total_items = len(items)
    total_pages = (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    start_idx = page * ITEMS_PER_PAGE
    end_idx = min(start_idx + ITEMS_PER_PAGE, total_items)

    keyboard = []
    for item in items[start_idx:end_idx]:
        item_id, date, name, color, size, quantity, price = item
        button_text = f"📦 {date} | {name} | {color} | {size} | {quantity}шт"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"sell_{item_id}")])

    # Кнопки навигации
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ Предыдущая", callback_data=f"sale_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Следующая ▶️", callback_data=f"sale_page_{page+1}"))

    if nav_buttons:
        keyboard.append(nav_buttons)

    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")])

    page_info = f" (стр. {page+1}/{total_pages})" if total_pages > 1 else ""
    await update.message.reply_text(
        f"💰 Новая продажа{page_info}\n\nВыберите товар:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def handle_sale_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора товара для продажи"""
    query = update.callback_query
    await query.answer()

    if query.data == "back_to_main":
        await query.edit_message_text("🏠 Главное меню:")
        await query.message.reply_text("Выберите действие:", reply_markup=bot.get_main_keyboard())
        return

    # Обработка пагинации для продаж
    if query.data.startswith("sale_page_"):
        page = int(query.data.split("_")[2])

        conn = sqlite3.connect(bot.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, date, name, color, size, remaining_quantity, price_per_unit
            FROM purchases
            WHERE remaining_quantity > 0
            ORDER BY datetime(substr(date, 7, 4) || '-' || substr(date, 4, 2) || '-' || substr(date, 1, 2)) DESC, name ASC
        """)
        items = cursor.fetchall()
        conn.close()

        # Пагинация
        total_items = len(items)
        total_pages = (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
        start_idx = page * ITEMS_PER_PAGE
        end_idx = min(start_idx + ITEMS_PER_PAGE, total_items)

        keyboard = []
        for item in items[start_idx:end_idx]:
            item_id, date, name, color, size, quantity, price = item
            button_text = f"📦 {date} | {name} | {color} | {size} | {quantity}шт"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"sell_{item_id}")])

        # Кнопки навигации
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("◀️ Предыдущая", callback_data=f"sale_page_{page-1}"))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("Следующая ▶️", callback_data=f"sale_page_{page+1}"))

        if nav_buttons:
            keyboard.append(nav_buttons)

        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")])

        page_info = f" (стр. {page+1}/{total_pages})" if total_pages > 1 else ""
        await query.edit_message_text(
            f"💰 Новая продажа{page_info}\n\nВыберите товар:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        return

    if query.data.startswith("sell_"):
        item_id = int(query.data.split("_")[1])
        context.user_data['sale_item_id'] = item_id

        conn = sqlite3.connect(bot.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT name, color, size, remaining_quantity, price_per_unit
            FROM purchases WHERE id = ?
        """, (item_id,))
        item = cursor.fetchone()
        conn.close()

        if item:
            name, color, size, quantity, purchase_price = item
            context.user_data['purchase_price'] = purchase_price

            await query.edit_message_text(
                f"🏷 {name} | {color} | {size}\n\n📦 Доступно: {quantity} шт\n💸 Цена закупки: {format_number(purchase_price)} ₽/шт\n\n💰 Введите цену продажи за штуку:",
                parse_mode='HTML'
            )
            return SALE_PRICE

    # Обработка выбора периода
    if query.data.startswith("period_"):
        period = query.data.split("_")[1]
        if len(query.data.split("_")) > 2:
            period = "_".join(query.data.split("_")[1:])

        if context.user_data.get('current_action') == 'item_sales':
            await show_item_sales_data(query, context, period)
        elif context.user_data.get('current_action') == 'sales':
            await show_sales_data(query, context, period)

    # Выбор месяца
    if query.data == "select_month":
        await query.edit_message_text(
            "📆 Выберите месяц:",
            reply_markup=bot.get_month_keyboard(),
            parse_mode='HTML'
        )

    # Обработка выбора месяца
    if query.data.startswith("month_"):
        month = int(query.data.split("_")[1])
        context.user_data['selected_month'] = month
        await query.edit_message_text(
            "📅 Выберите год:",
            reply_markup=bot.get_year_keyboard(),
            parse_mode='HTML'
        )

    # Обработка выбора года
    if query.data.startswith("year_"):
        year = int(query.data.split("_")[1])
        month = context.user_data.get('selected_month')

        if month:
            if context.user_data.get('current_action') == 'item_sales':
                await show_item_sales_data(query, context, f"custom_{month}_{year}")
            elif context.user_data.get('current_action') == 'sales':
                await show_sales_data(query, context, f"custom_{month}_{year}")

    # Навигация назад
    if query.data == "back_to_periods":
        action = context.user_data.get('current_action', 'sales')

        if action == 'item_sales':
            title = "🛍 Продажи по вещам"
        else:
            title = "📊 Анализ продаж"

        await query.edit_message_text(
            f"{title}\n\nВыберите период:",
            reply_markup=bot.get_period_keyboard(),
            parse_mode='HTML'
        )

    if query.data == "back_to_months":
        await query.edit_message_text(
            "📆 Выберите месяц:",
            reply_markup=bot.get_month_keyboard(),
            parse_mode='HTML'
        )

async def sale_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка цены продажи"""
    try:
        sale_price = float(update.message.text.replace(',', '.'))
        if sale_price <= 0:
            raise ValueError

        context.user_data['sale_price'] = sale_price

        keyboard = [
            [InlineKeyboardButton("🚚 Доставка", callback_data="method_delivery")],
            [InlineKeyboardButton("🤝 Личная встреча", callback_data="method_meeting")]
        ]

        await update.message.reply_text(
            "📮 Выберите способ продажи:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        return SALE_METHOD
    except ValueError:
        await update.message.reply_text("❌ Введите корректную цену:")
        return SALE_PRICE

async def sale_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка способа продажи и сохранение"""
    query = update.callback_query
    await query.answer()

    if query.data.startswith("method_"):
        method_emoji = "🚚" if query.data == "method_delivery" else "🤝"
        method = "Доставка" if query.data == "method_delivery" else "Личная встреча"
        method_db = "delivery" if query.data == "method_delivery" else "meeting"

        item_id = context.user_data['sale_item_id']
        sale_price = context.user_data['sale_price']

        conn = sqlite3.connect(bot.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT date, name, color, size, remaining_quantity, price_per_unit
            FROM purchases WHERE id = ?
        """, (item_id,))
        item = cursor.fetchone()

        if item:
            purchase_date, name, color, size, remaining_quantity, purchase_price = item

            if remaining_quantity > 0:
                quantity_sold = 1
                total_sale = sale_price * quantity_sold
                profit = (sale_price - purchase_price) * quantity_sold

                purchase_date_obj = datetime.strptime(purchase_date, "%d.%m.%Y")
                sale_date = datetime.now().strftime("%d.%m.%Y")
                sale_date_obj = datetime.now()
                days_to_sell = (sale_date_obj - purchase_date_obj).days

                cursor.execute("""
                    INSERT INTO sales (purchase_id, sale_date, quantity_sold, sale_price_per_unit, 
                                     total_sale, profit, days_to_sell, sale_method)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (item_id, sale_date, quantity_sold, sale_price, total_sale, profit, days_to_sell, method_db))

                cursor.execute("""
                    UPDATE purchases SET remaining_quantity = remaining_quantity - ?
                    WHERE id = ?
                """, (quantity_sold, item_id))

                conn.commit()

                margin_percent = ((sale_price - purchase_price) / purchase_price * 100) if purchase_price > 0 else 0
                profit_emoji = "📈" if profit >= 0 else "📉"
                profit_text = f"+{format_number(profit)}" if profit >= 0 else f"{format_number(profit)}"

                success_message = f"✅ Продажа оформлена\n\n🏷 {name} | {color} | {size}\n💰 Цена продажи: {format_number(sale_price)} ₽\n{profit_emoji} Прибыль: {profit_text} ₽ ({margin_percent:+.1f}%)\n{method_emoji} Способ: {method}\n⏱ Время продажи: {days_to_sell} дней\n📦 Осталось: {remaining_quantity - quantity_sold} шт"

                await query.edit_message_text(success_message, parse_mode='HTML')
                await query.message.reply_text("🏠 Главное меню:", reply_markup=bot.get_main_keyboard())
            else:
                await query.edit_message_text("❌ Товар закончился в остатках")
                await query.message.reply_text("🏠 Главное меню:", reply_markup=bot.get_main_keyboard())

        conn.close()
        context.user_data.clear()
        return ConversationHandler.END

# Новая функция: показ списка вещей для выбора
async def show_items_for_sales(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    """Показ списка вещей для просмотра продаж"""
    conn = sqlite3.connect(bot.db_path)
    cursor = conn.cursor()

    # Получаем все уникальные названия товаров, по которым были продажи
    cursor.execute("""
        SELECT DISTINCT p.name
        FROM purchases p
        JOIN sales s ON p.id = s.purchase_id
        ORDER BY p.name ASC
    """)
    items = cursor.fetchall()
    conn.close()

    if not items:
        await update.message.reply_text(
            "🛍 Продажи по вещам\n\n❌ Нет данных о продажах",
            reply_markup=bot.get_main_keyboard(),
            parse_mode='HTML'
        )
        return

    # Пагинация
    total_items = len(items)
    total_pages = (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    start_idx = page * ITEMS_PER_PAGE
    end_idx = min(start_idx + ITEMS_PER_PAGE, total_items)

    keyboard = []
    for item in items[start_idx:end_idx]:
        item_name = item[0]
        button_text = f"🏷 {item_name.upper()}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"item_sales_{item_name}")])

    # Кнопки навигации
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ Предыдущая", callback_data=f"items_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Следующая ▶️", callback_data=f"items_page_{page+1}"))

    if nav_buttons:
        keyboard.append(nav_buttons)

    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")])

    page_info = f" (стр. {page+1}/{total_pages})" if total_pages > 1 else ""
    await update.message.reply_text(
        f"🛍 Продажи по вещам{page_info}\n\nВыберите товар:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def show_item_sales_data(query, context: ContextTypes.DEFAULT_TYPE, period: str):
    """Показ данных о продажах конкретной вещи"""
    item_name = context.user_data.get('selected_item_name')

    if not item_name:
        await query.edit_message_text("❌ Ошибка: товар не выбран")
        return

    conn = sqlite3.connect(bot.db_path)
    cursor = conn.cursor()

    now = datetime.now()
    current_month = now.month
    current_year = now.year

    # Формируем SQL запрос в зависимости от периода
    base_query = """
        SELECT s.sale_date, p.color, p.size, s.sale_price_per_unit, s.profit
        FROM sales s
        JOIN purchases p ON s.purchase_id = p.id
        WHERE p.name = ?
    """

    stats_query = """
        SELECT SUM(s.profit), SUM(s.total_sale), COUNT(*)
        FROM sales s
        JOIN purchases p ON s.purchase_id = p.id
        WHERE p.name = ?
    """

    # Обработка кастомного периода (выбранный месяц)
    if period.startswith("custom_"):
        parts = period.split("_")
        selected_month = int(parts[1])
        selected_year = int(parts[2])

        base_query += """
            AND CAST(substr(s.sale_date, 4, 2) AS INTEGER) = ?
            AND CAST(substr(s.sale_date, 7, 4) AS INTEGER) = ?
        """
        stats_query += """
            AND CAST(substr(s.sale_date, 4, 2) AS INTEGER) = ?
            AND CAST(substr(s.sale_date, 7, 4) AS INTEGER) = ?
        """

        base_query += """
            ORDER BY datetime(substr(s.sale_date, 7, 4) || '-' || substr(s.sale_date, 4, 2) || '-' || substr(s.sale_date, 1, 2)) DESC
        """

        cursor.execute(base_query, (item_name, selected_month, selected_year))
        sales = cursor.fetchall()
        cursor.execute(stats_query, (item_name, selected_month, selected_year))

    elif period == "all":
        base_query += """
            ORDER BY datetime(substr(s.sale_date, 7, 4) || '-' || substr(s.sale_date, 4, 2) || '-' || substr(s.sale_date, 1, 2)) DESC
        """
        cursor.execute(base_query, (item_name,))
        sales = cursor.fetchall()
        cursor.execute(stats_query, (item_name,))

    elif period == "current_month":
        base_query += """
            AND CAST(substr(s.sale_date, 4, 2) AS INTEGER) = ?
            AND CAST(substr(s.sale_date, 7, 4) AS INTEGER) = ?
        """
        stats_query += """
            AND CAST(substr(s.sale_date, 4, 2) AS INTEGER) = ?
            AND CAST(substr(s.sale_date, 7, 4) AS INTEGER) = ?
        """

        base_query += """
            ORDER BY datetime(substr(s.sale_date, 7, 4) || '-' || substr(s.sale_date, 4, 2) || '-' || substr(s.sale_date, 1, 2)) DESC
        """

        cursor.execute(base_query, (item_name, current_month, current_year))
        sales = cursor.fetchall()
        cursor.execute(stats_query, (item_name, current_month, current_year))

    else:
        date_filter = get_date_filter(period)
        base_query += """
            AND datetime(substr(s.sale_date, 7, 4) || '-' || substr(s.sale_date, 4, 2) || '-' || substr(s.sale_date, 1, 2)) >=
            datetime(substr(?, 7, 4) || '-' || substr(?, 4, 2) || '-' || substr(?, 1, 2))
        """
        stats_query += """
            AND datetime(substr(s.sale_date, 7, 4) || '-' || substr(s.sale_date, 4, 2) || '-' || substr(s.sale_date, 1, 2)) >=
            datetime(substr(?, 7, 4) || '-' || substr(?, 4, 2) || '-' || substr(?, 1, 2))
        """

        base_query += """
            ORDER BY datetime(substr(s.sale_date, 7, 4) || '-' || substr(s.sale_date, 4, 2) || '-' || substr(s.sale_date, 1, 2)) DESC
        """

        cursor.execute(base_query, (item_name, date_filter, date_filter, date_filter))
        sales = cursor.fetchall()
        cursor.execute(stats_query, (item_name, date_filter, date_filter, date_filter))

    stats = cursor.fetchone()
    total_profit, total_sales_sum, sales_count = stats if stats else (0, 0, 0)

    conn.close()

    period_name = get_period_name(period)

    if not sales:
        message = f"🛍 {item_name.upper()}\n📊 Продажи за {period_name}\n\n❌ Продаж не было"
    else:
        profit_emoji = "📈" if total_profit and total_profit >= 0 else "📉"
        message = f"🛍 {item_name.upper()}\n📊 Продажи за {period_name}\n\n{profit_emoji} Прибыль: {format_number(total_profit or 0)} ₽\n📊 Оборот: {format_number(total_sales_sum or 0)} ₽\n💰 Всего продаж: {sales_count}\n\n"

        for sale in sales[:15]:
            sale_date, color, size, sale_price, profit = sale
            profit_emoji_item = "📈" if profit >= 0 else "📉"
            profit_text = f"+{format_number(profit)}" if profit >= 0 else f"{format_number(profit)}"
            message += f"📅 {sale_date}\n🏷 {color} | {size}\n💰 {format_number(sale_price)} ₽ | {profit_emoji_item} {profit_text} ₽\n\n"

    await query.edit_message_text(message, parse_mode='HTML')

# Аналитические функции
async def show_sales_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ меню продаж"""
    context.user_data['current_action'] = 'sales'
    await update.message.reply_text(
        "📊 Анализ продаж\n\nВыберите период:",
        reply_markup=bot.get_period_keyboard(),
        parse_mode='HTML'
    )

async def show_sales_data(query, context: ContextTypes.DEFAULT_TYPE, period: str):
    """Показ данных о продажах"""
    conn = sqlite3.connect(bot.db_path)
    cursor = conn.cursor()

    now = datetime.now()
    current_month = now.month
    current_year = now.year

    # Обработка кастомного периода (выбранный месяц)
    if period.startswith("custom_"):
        parts = period.split("_")
        selected_month = int(parts[1])
        selected_year = int(parts[2])

        cursor.execute("""
            SELECT s.sale_date, p.name, p.color, p.size, s.sale_price_per_unit, s.profit
            FROM sales s
            JOIN purchases p ON s.purchase_id = p.id
            WHERE CAST(substr(s.sale_date, 4, 2) AS INTEGER) = ?
              AND CAST(substr(s.sale_date, 7, 4) AS INTEGER) = ?
            ORDER BY datetime(substr(s.sale_date, 7, 4) || '-' || substr(s.sale_date, 4, 2) || '-' || substr(s.sale_date, 1, 2)) DESC
            LIMIT 15
        """, (selected_month, selected_year))

    elif period == "all":
        cursor.execute("""
            SELECT s.sale_date, p.name, p.color, p.size, s.sale_price_per_unit, s.profit
            FROM sales s
            JOIN purchases p ON s.purchase_id = p.id
            ORDER BY datetime(substr(s.sale_date, 7, 4) || '-' || substr(s.sale_date, 4, 2) || '-' || substr(s.sale_date, 1, 2)) DESC
            LIMIT 15
        """)

    elif period == "current_month":
        cursor.execute("""
            SELECT s.sale_date, p.name, p.color, p.size, s.sale_price_per_unit, s.profit
            FROM sales s
            JOIN purchases p ON s.purchase_id = p.id
            WHERE CAST(substr(s.sale_date, 4, 2) AS INTEGER) = ?
              AND CAST(substr(s.sale_date, 7, 4) AS INTEGER) = ?
            ORDER BY datetime(substr(s.sale_date, 7, 4) || '-' || substr(s.sale_date, 4, 2) || '-' || substr(s.sale_date, 1, 2)) DESC
            LIMIT 15
        """, (current_month, current_year))

    else:
        date_filter = get_date_filter(period)
        cursor.execute("""
            SELECT s.sale_date, p.name, p.color, p.size, s.sale_price_per_unit, s.profit
            FROM sales s
            JOIN purchases p ON s.purchase_id = p.id
            WHERE datetime(substr(s.sale_date, 7, 4) || '-' || substr(s.sale_date, 4, 2) || '-' || substr(s.sale_date, 1, 2)) >=
                  datetime(substr(?, 7, 4) || '-' || substr(?, 4, 2) || '-' || substr(?, 1, 2))
            ORDER BY datetime(substr(s.sale_date, 7, 4) || '-' || substr(s.sale_date, 4, 2) || '-' || substr(s.sale_date, 1, 2)) DESC
            LIMIT 15
        """, (date_filter, date_filter, date_filter))

    sales = cursor.fetchall()

    # Получаем также общую статистику для периода
    if period.startswith("custom_"):
        parts = period.split("_")
        selected_month = int(parts[1])
        selected_year = int(parts[2])

        cursor.execute("""
            SELECT SUM(profit), SUM(total_sale), COUNT(*)
            FROM sales
            WHERE CAST(substr(sale_date, 4, 2) AS INTEGER) = ?
              AND CAST(substr(sale_date, 7, 4) AS INTEGER) = ?
        """, (selected_month, selected_year))

    elif period == "all":
        cursor.execute("""
            SELECT SUM(profit), SUM(total_sale), COUNT(*)
            FROM sales
        """)

    elif period == "current_month":
        cursor.execute("""
            SELECT SUM(profit), SUM(total_sale), COUNT(*)
            FROM sales
            WHERE CAST(substr(sale_date, 4, 2) AS INTEGER) = ?
              AND CAST(substr(sale_date, 7, 4) AS INTEGER) = ?
        """, (current_month, current_year))

    else:
        date_filter = get_date_filter(period)
        cursor.execute("""
            SELECT SUM(profit), SUM(total_sale), COUNT(*)
            FROM sales
            WHERE datetime(substr(sale_date, 7, 4) || '-' || substr(sale_date, 4, 2) || '-' || substr(sale_date, 1, 2)) >=
                  datetime(substr(?, 7, 4) || '-' || substr(?, 4, 2) || '-' || substr(?, 1, 2))
        """, (date_filter, date_filter, date_filter))

    stats = cursor.fetchone()
    total_profit_period, total_sales_period, total_count = stats if stats else (0, 0, 0)

    conn.close()

    period_name = get_period_name(period)

    if not sales:
        message = f"📊 Продажи за {period_name}\n\n❌ Продаж не было"
    else:
        profit_emoji = "📈" if total_profit_period and total_profit_period >= 0 else "📉"
        message = f"📊 Продажи за {period_name}\n\n{profit_emoji} Прибыль: {format_number(total_profit_period or 0)} ₽\n📊 Оборот: {format_number(total_sales_period or 0)} ₽\n💰 Всего продаж: {total_count}\n\n"

        for sale in sales[:10]:
            sale_date, name, color, size, sale_price, profit = sale
            profit_emoji_item = "📈" if profit >= 0 else "📉"
            profit_text = f"+{format_number(profit)}" if profit >= 0 else f"{format_number(profit)}"
            message += f"📅 {sale_date}\n🏷 {name} | {color} | {size}\n💰 {format_number(sale_price)} ₽ | {profit_emoji_item} {profit_text} ₽\n\n"

    await query.edit_message_text(message, parse_mode='HTML')

async def show_inventory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ остатков с группировкой по названию"""
    conn = sqlite3.connect(bot.db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT name,
               GROUP_CONCAT(color || '|' || size || '|' || remaining_quantity || '|' || price_per_unit || '|' || date, ';') as variants,
               SUM(remaining_quantity) as total_qty,
               SUM(remaining_quantity * price_per_unit) as total_value
        FROM purchases
        WHERE remaining_quantity > 0
        GROUP BY name
        ORDER BY name ASC
    """)
    inventory = cursor.fetchall()
    conn.close()

    if not inventory:
        await update.message.reply_text(
            "📋 Остатки\n\n❌ Нет товаров в остатках",
            reply_markup=bot.get_back_keyboard(),
            parse_mode='HTML'
        )
        return

    total_value = sum(item[3] for item in inventory)
    total_items = sum(item[2] for item in inventory)

    message = f"📋 Остатки\n\n📦 Позиций: {len(inventory)}\n🔢 Количество: {format_int(total_items)} шт\n💰 Стоимость: {format_number(total_value)} ₽\n\n"

    for item in inventory:
        name, variants_str, total_qty, value = item
        message += f"━━━━━━━━━━━━━━━━━\n🏷 {name.upper()} ({total_qty} шт)\n"

        variants = variants_str.split(';')
        for variant in variants:
            color, size, qty, price, date = variant.split('|')
            message += f"  • {color} {size}: {qty}шт × {format_number(float(price))}₽ ({date})\n"

    await update.message.reply_text(
        message,
        reply_markup=bot.get_back_keyboard(),
        parse_mode='HTML'
    )

async def show_liquidity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ ликвидности товаров"""
    conn = sqlite3.connect(bot.db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT p.name, p.color, p.size,
               AVG(s.days_to_sell) as avg_days,
               AVG(s.profit) as avg_profit,
               COUNT(s.id) as sales_count
        FROM purchases p
        JOIN sales s ON p.id = s.purchase_id
        GROUP BY p.name, p.color, p.size
        HAVING sales_count >= 1
        ORDER BY avg_days ASC, avg_profit DESC
    """)
    liquidity_data = cursor.fetchall()
    conn.close()

    if not liquidity_data:
        await update.message.reply_text(
            "⚡️ Ликвидность товаров\n\n❌ Недостаточно данных для анализа",
            reply_markup=bot.get_back_keyboard(),
            parse_mode='HTML'
        )
        return

    message = "⚡️ Ликвидность товаров\n\n"

    for i, item in enumerate(liquidity_data[:10], 1):
        name, color, size, avg_days, avg_profit, sales_count = item

        if avg_days <= 7:
            level = "🔥 Очень высокая"
        elif avg_days <= 30:
            level = "✅ Высокая"
        elif avg_days <= 90:
            level = "🟡 Средняя"
        else:
            level = "🔻 Низкая"

        profit_emoji = "📈" if avg_profit >= 0 else "📉"
        profit_formatted = f"+{format_number(avg_profit)}" if avg_profit >= 0 else f"{format_number(avg_profit)}"

        message += f"{i}. {name} | {color} | {size}\n"
        message += f"⏱ Среднее время: {avg_days:.1f}д | {profit_emoji} {profit_formatted}₽\n"
        message += f"💰 Продано: {sales_count} | {level}\n\n"

    await update.message.reply_text(
        message,
        reply_markup=bot.get_back_keyboard(),
        parse_mode='HTML'
    )

async def show_sales_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ общей статистики бизнеса"""
    conn = sqlite3.connect(bot.db_path)
    cursor = conn.cursor()

    # Общая статистика по всем продажам
    cursor.execute("""
        SELECT
            COUNT(*) as total_sales,
            SUM(total_sale) as total_revenue,
            SUM(profit) as total_profit,
            AVG(profit) as avg_profit,
            AVG(days_to_sell) as avg_days
        FROM sales
    """)
    overall = cursor.fetchone()

    # Статистика по способам продажи
    cursor.execute("""
        SELECT
            sale_method,
            COUNT(*) as count,
            SUM(profit) as profit
        FROM sales
        GROUP BY sale_method
    """)
    methods = cursor.fetchall()

    # Самый прибыльный товар
    cursor.execute("""
        SELECT
            p.name,
            SUM(s.profit) as total_profit,
            COUNT(s.id) as sales_count
        FROM sales s
        JOIN purchases p ON s.purchase_id = p.id
        GROUP BY p.name
        ORDER BY total_profit DESC
        LIMIT 1
    """)
    best_product = cursor.fetchone()

    # Общая стоимость закупок
    cursor.execute("""
        SELECT SUM(total_cost) FROM purchases
    """)
    total_investment = cursor.fetchone()[0] or 0

    # Товары в остатках
    cursor.execute("""
        SELECT
            SUM(remaining_quantity) as total_items,
            SUM(remaining_quantity * price_per_unit) as stock_value
        FROM purchases
        WHERE remaining_quantity > 0
    """)
    stock_data = cursor.fetchone()

    conn.close()

    if not overall or not overall[0]:
        await update.message.reply_text(
            "📈 Статистика бизнеса\n\n❌ Нет данных для анализа",
            reply_markup=bot.get_back_keyboard(),
            parse_mode='HTML'
        )
        return

    total_sales, total_revenue, total_profit, avg_profit, avg_days = overall
    stock_items, stock_value = stock_data if stock_data else (0, 0)

    # ROI
    roi = ((total_profit / total_investment) * 100) if total_investment > 0 else 0

    # Средняя наценка
    avg_margin = ((total_revenue - (total_revenue - total_profit)) / (total_revenue - total_profit) * 100) if (total_revenue - total_profit) > 0 else 0

    profit_emoji = "📈" if total_profit >= 0 else "📉"
    roi_emoji = "🚀" if roi > 50 else "📈" if roi > 0 else "📉"

    message = f"📈 Статистика бизнеса\n\n"
    message += f"━━━━━━━━━━━━━━━━━\n"
    message += f"💼 Общие показатели:\n"
    message += f"💰 Продаж: {format_int(total_sales)}\n"
    message += f"📊 Оборот: {format_number(total_revenue)} ₽\n"
    message += f"{profit_emoji} Прибыль: {format_number(total_profit)} ₽\n"
    message += f"📈 Средняя прибыль: {format_number(avg_profit)} ₽/продажа\n"
    message += f"⏱ Средний срок продажи: {avg_days:.1f} дней\n"
    message += f"📊 Средняя наценка: {avg_margin:.1f}%\n"
    message += f"{roi_emoji} ROI: {roi:.1f}%\n\n"

    if best_product:
        best_name, best_profit, best_count = best_product
        message += f"🏆 Лучший товар:\n"
        message += f"  {best_name.upper()}\n"
        message += f"  💰 Прибыль: {format_number(best_profit)} ₽ ({best_count} продаж)\n\n"

    message += f"📦 Остатки на складе:\n"
    message += f"  Товаров: {format_int(stock_items or 0)} шт\n"
    message += f"  Стоимость: {format_number(stock_value or 0)} ₽\n\n"

    if methods:
        message += f"━━━━━━━━━━━━━━━━━\n"
        message += f"📮 По способам продажи:\n\n"
        for method_data in methods:
            method, count, profit = method_data
            method_emoji = "🚚" if method == "delivery" else "🤝"
            method_name = "Доставка" if method == "delivery" else "Личная встреча"
            percent = (count / total_sales * 100) if total_sales > 0 else 0
            profit_emoji_m = "📈" if profit >= 0 else "📉"

            message += f"{method_emoji} {method_name}\n"
            message += f"  Продаж: {format_int(count)} ({percent:.1f}%)\n"
            message += f"  {profit_emoji_m} Прибыль: {format_number(profit)} ₽\n\n"

    await update.message.reply_text(
        message,
        reply_markup=bot.get_back_keyboard(),
        parse_mode='HTML'
    )

# Меню удаления записей с пагинацией
async def delete_record_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню удаления записей"""
    keyboard = [
        [InlineKeyboardButton("📦 Удалить закупку", callback_data="delete_purchase")],
        [InlineKeyboardButton("💰 Удалить продажу", callback_data="delete_sale")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]
    ]

    await update.message.reply_text(
        "🗑 Удаление записей\n\nВыберите тип записи:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def show_delete_purchases(query, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    """Показ списка закупок для удаления с пагинацией"""
    conn = sqlite3.connect(bot.db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, date, name, color, size, remaining_quantity
        FROM purchases
        ORDER BY datetime(substr(date, 7, 4) || '-' || substr(date, 4, 2) || '-' || substr(date, 1, 2)) DESC
    """)
    purchases = cursor.fetchall()
    conn.close()

    if not purchases:
        await query.edit_message_text("❌ Нет закупок для удаления")
        return

    # Пагинация
    total_items = len(purchases)
    total_pages = (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    start_idx = page * ITEMS_PER_PAGE
    end_idx = min(start_idx + ITEMS_PER_PAGE, total_items)

    keyboard = []
    for purchase in purchases[start_idx:end_idx]:
        purchase_id, date, name, color, size, remaining = purchase
        button_text = f"📦 {date} | {name} | {color} | {size} | {remaining}шт"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"delete_p_{purchase_id}")])

    # Кнопки навигации
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ Предыдущая", callback_data=f"delp_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Следующая ▶️", callback_data=f"delp_page_{page+1}"))

    if nav_buttons:
        keyboard.append(nav_buttons)

    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")])

    page_info = f" (стр. {page+1}/{total_pages})" if total_pages > 1 else ""
    await query.edit_message_text(
        f"🗑 Выберите закупку для удаления{page_info}:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def show_delete_sales(query, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    """Показ списка продаж для удаления с пагинацией"""
    conn = sqlite3.connect(bot.db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT s.id, s.sale_date, p.name, p.color, p.size, s.profit
        FROM sales s
        JOIN purchases p ON s.purchase_id = p.id
        ORDER BY datetime(substr(s.sale_date, 7, 4) || '-' || substr(s.sale_date, 4, 2) || '-' || substr(s.sale_date, 1, 2)) DESC
    """)
    sales = cursor.fetchall()
    conn.close()

    if not sales:
        await query.edit_message_text("❌ Нет продаж для удаления")
        return

    # Пагинация
    total_items = len(sales)
    total_pages = (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    start_idx = page * ITEMS_PER_PAGE
    end_idx = min(start_idx + ITEMS_PER_PAGE, total_items)

    keyboard = []
    for sale in sales[start_idx:end_idx]:
        sale_id, date, name, color, size, profit = sale
        profit_emoji = "📈" if profit >= 0 else "📉"
        profit_text = f"+{format_number(profit)}" if profit >= 0 else f"{format_number(profit)}"
        button_text = f"💰 {date} | {name} | {color} | {size} | {profit_emoji} {profit_text}₽"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"delete_s_{sale_id}")])

    # Кнопки навигации
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ Предыдущая", callback_data=f"dels_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Следующая ▶️", callback_data=f"dels_page_{page+1}"))

    if nav_buttons:
        keyboard.append(nav_buttons)

    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")])

    page_info = f" (стр. {page+1}/{total_pages})" if total_pages > 1 else ""
    await query.edit_message_text(
        f"🗑 Выберите продажу для удаления{page_info}:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def delete_purchase(query, context: ContextTypes.DEFAULT_TYPE, purchase_id: int):
    """Удаление закупки"""
    conn = sqlite3.connect(bot.db_path)
    cursor = conn.cursor()

    cursor.execute('SELECT COUNT(*) FROM sales WHERE purchase_id = ?', (purchase_id,))
    sales_count = cursor.fetchone()[0]

    if sales_count > 0:
        await query.edit_message_text(
            "❌ Нельзя удалить закупку с продажами\n\nСначала удалите связанные продажи.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]]),
            parse_mode='HTML'
        )
    else:
        cursor.execute('DELETE FROM purchases WHERE id = ?', (purchase_id,))
        conn.commit()
        conn.close()

        await query.edit_message_text("✅ Закупка удалена")
        await query.message.reply_text("🏠 Главное меню:", reply_markup=bot.get_main_keyboard())

async def delete_sale(query, context: ContextTypes.DEFAULT_TYPE, sale_id: int):
    """Удаление продажи"""
    conn = sqlite3.connect(bot.db_path)
    cursor = conn.cursor()

    cursor.execute('SELECT purchase_id, quantity_sold FROM sales WHERE id = ?', (sale_id,))
    sale_info = cursor.fetchone()

    if sale_info:
        purchase_id, quantity_sold = sale_info

        cursor.execute("""
            UPDATE purchases SET remaining_quantity = remaining_quantity + ?
            WHERE id = ?
        """, (quantity_sold, purchase_id))

        cursor.execute('DELETE FROM sales WHERE id = ?', (sale_id,))

        conn.commit()

    conn.close()

    await query.edit_message_text("✅ Продажа удалена, товар возвращен в остатки")
    await query.message.reply_text("🏠 Главное меню:", reply_markup=bot.get_main_keyboard())

# Вспомогательные функции
def get_date_filter(period: str) -> str:
    """Получить дату для фильтрации по периоду"""
    today = datetime.now()

    if period == "today":
        filter_date = today
    elif period == "week":
        filter_date = today - timedelta(days=7)
    elif period == "2weeks":
        filter_date = today - timedelta(days=14)
    elif period == "month":
        filter_date = today - timedelta(days=30)
    else:
        filter_date = datetime(2000, 1, 1)

    return filter_date.strftime("%d.%m.%Y")

def get_period_name(period: str) -> str:
    """Получить название периода"""
    now = datetime.now()

    months_ru = {
        1: "январь", 2: "февраль", 3: "март", 4: "апрель",
        5: "май", 6: "июнь", 7: "июль", 8: "август",
        9: "сентябрь", 10: "октябрь", 11: "ноябрь", 12: "декабрь"
    }

    # Обработка кастомного периода
    if period.startswith("custom_"):
        parts = period.split("_")
        month = int(parts[1])
        year = int(parts[2])
        return f"{months_ru[month]} {year}"

    current_month_name = f"{months_ru[now.month]} {now.year}"

    period_names = {
        "today": "сегодня",
        "week": "неделю",
        "2weeks": "2 недели",
        "month": "месяц",
        "current_month": current_month_name,
        "all": "всё время"
    }

    return period_names.get(period, "всё время")

async def handle_callback_queries(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка callback запросов"""
    query = update.callback_query
    await query.answer()

    if query.data == "back_to_main":
        await query.edit_message_text("🏠 Главное меню:")
        await query.message.reply_text("Выберите действие:", reply_markup=bot.get_main_keyboard())
        return

    # Пагинация для списка вещей
    if query.data.startswith("items_page_"):
        page = int(query.data.split("_")[2])

        conn = sqlite3.connect(bot.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT DISTINCT p.name
            FROM purchases p
            JOIN sales s ON p.id = s.purchase_id
            ORDER BY p.name ASC
        """)
        items = cursor.fetchall()
        conn.close()

        # Пагинация
        total_items = len(items)
        total_pages = (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
        start_idx = page * ITEMS_PER_PAGE
        end_idx = min(start_idx + ITEMS_PER_PAGE, total_items)

        keyboard = []
        for item in items[start_idx:end_idx]:
            item_name = item[0]
            button_text = f"🏷 {item_name.upper()}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"item_sales_{item_name}")])

        # Кнопки навигации
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("◀️ Предыдущая", callback_data=f"items_page_{page-1}"))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("Следующая ▶️", callback_data=f"items_page_{page+1}"))

        if nav_buttons:
            keyboard.append(nav_buttons)

        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")])

        page_info = f" (стр. {page+1}/{total_pages})" if total_pages > 1 else ""
        await query.edit_message_text(
            f"🛍 Продажи по вещам{page_info}\n\nВыберите товар:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        return

    # Обработка выбора конкретной вещи
    if query.data.startswith("item_sales_"):
        item_name = query.data[11:]  # Убираем "item_sales_"
        context.user_data['selected_item_name'] = item_name
        context.user_data['current_action'] = 'item_sales'

        await query.edit_message_text(
            f"🛍 {item_name.upper()}\n\nВыберите период:",
            reply_markup=bot.get_period_keyboard(),
            parse_mode='HTML'
        )
        return

    # Пагинация для удаления закупок
    if query.data.startswith("delp_page_"):
        page = int(query.data.split("_")[2])
        await show_delete_purchases(query, context, page)
        return

    # Пагинация для удаления продаж
    if query.data.startswith("dels_page_"):
        page = int(query.data.split("_")[2])
        await show_delete_sales(query, context, page)
        return

    if query.data == "delete_purchase":
        await show_delete_purchases(query, context)
        return

    if query.data == "delete_sale":
        await show_delete_sales(query, context)
        return

    if query.data.startswith("delete_p_"):
        purchase_id = int(query.data.split("_")[2])
        await delete_purchase(query, context, purchase_id)
        return

    if query.data.startswith("delete_s_"):
        sale_id = int(query.data.split("_")[2])
        await delete_sale(query, context, sale_id)
        return

    if query.data.startswith("method_"):
        await sale_method(update, context)
        return

    await handle_sale_callback(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена текущего разговора"""
    context.user_data.clear()
    await update.message.reply_text(
        "❌ Операция отменена",
        reply_markup=bot.get_main_keyboard()
    )
    return ConversationHandler.END

def main():
    """Запуск бота"""
    application = Application.builder().token(bot.token).build()

    # Обработчик авторизации
    auth_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={PASSWORD_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_password)]},
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    # Обработчик добавления закупки
    purchase_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^(?i).*добавить закупку.*$"), start_purchase)],
        states={
            PURCHASE_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, purchase_date)],
            PURCHASE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, purchase_name)],
            PURCHASE_COLOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, purchase_color)],
            PURCHASE_SIZE: [MessageHandler(filters.TEXT & ~filters.COMMAND, purchase_size)],
            PURCHASE_QUANTITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, purchase_quantity)],
            PURCHASE_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, purchase_price)],
        },
        fallbacks=[CommandHandler('cancel', cancel), MessageHandler(filters.Regex("^(?i).*назад.*$"), cancel)],
    )

    # Обработчик продаж
    sale_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_sale_callback, pattern="^sell_")],
        states={
            SALE_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, sale_price)],
            SALE_METHOD: [CallbackQueryHandler(sale_method, pattern="^method_")],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    application.add_handler(auth_handler)
    application.add_handler(purchase_handler)
    application.add_handler(sale_handler)
    application.add_handler(CallbackQueryHandler(handle_callback_queries))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_main_menu))

    print("🚀 Бот запущен!")
    application.run_polling()

if __name__ == '__main__':
    main()
