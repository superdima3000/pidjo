import logging
import sqlite3
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters, ConversationHandler

# Константы для состояний разговора
(PURCHASE_DATE, PURCHASE_NAME, PURCHASE_COLOR, PURCHASE_SIZE,
 PURCHASE_QUANTITY, PURCHASE_PRICE, SALE_PRICE, EXPORT_FORMAT) = range(8)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

class BusinessBot:
    def __init__(self, token: str):
        self.token = token
        self.db_path = 'business_bot.db'
        self.init_database()
    
    def init_database(self):
        """Инициализация базы данных"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Таблица закупок
        cursor.execute('''
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
        ''')
        
        # Таблица продаж
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                purchase_id INTEGER NOT NULL,
                sale_date TEXT NOT NULL,
                quantity_sold INTEGER NOT NULL,
                sale_price_per_unit REAL NOT NULL,
                total_sale REAL NOT NULL,
                profit REAL NOT NULL,
                days_to_sell INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (purchase_id) REFERENCES purchases (id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def get_main_keyboard(self):
        """Главная клавиатура"""
        keyboard = [
            [KeyboardButton("➕ Добавить закупку"), KeyboardButton("💰 Добавить продажу")],
            [KeyboardButton("📊 Прибыль"), KeyboardButton("📈 Продажи")],
            [KeyboardButton("📦 Остатки"), KeyboardButton("⚡ Ликвидность")],
            [KeyboardButton("🗑 Удалить запись"), KeyboardButton("💾 Экспорт данных")],
            [KeyboardButton("🧹 Очистить всё"), KeyboardButton("📋 Статистика")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    def get_back_keyboard(self):
        """Клавиатура с кнопкой назад"""
        keyboard = [[KeyboardButton("🔙 Назад")]]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    def get_period_keyboard(self):
        """Клавиатура для выбора периода"""
        keyboard = [
            [InlineKeyboardButton("📅 Сегодня", callback_data="period_today")],
            [InlineKeyboardButton("📅 Неделя", callback_data="period_week")],
            [InlineKeyboardButton("📅 Месяц", callback_data="period_month")],
            [InlineKeyboardButton("📅 3 месяца", callback_data="period_3months")],
            [InlineKeyboardButton("📅 Всё время", callback_data="period_all")]
        ]
        return InlineKeyboardMarkup(keyboard)

# Создаем экземпляр бота
bot = BusinessBot("8339672379:AAGzgFgA_Lj34sfwHn6NXLRYY0Fwlx25R4A")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    welcome_text = """
🏪 **Добро пожаловать в Бот Учета Бизнеса!**

Этот бот поможет вам:
• Вести учет закупок и продаж
• Анализировать прибыль и ликвидность
• Отслеживать остатки товаров
• Экспортировать данные

Используйте кнопки меню для навигации.
"""
    await update.message.reply_text(
        welcome_text,
        reply_markup=bot.get_main_keyboard(),
        parse_mode='Markdown'
    )

async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка главного меню"""
    text = update.message.text
    
    if text == "➕ Добавить закупку":
        return await start_purchase(update, context)
    elif text == "💰 Добавить продажу":
        return await start_sale(update, context)
    elif text == "📊 Прибыль":
        return await show_profit_menu(update, context)
    elif text == "📈 Продажи":
        return await show_sales_menu(update, context)
    elif text == "📦 Остатки":
        return await show_inventory(update, context)
    elif text == "⚡ Ликвидность":
        return await show_liquidity(update, context)
    elif text == "🗑 Удалить запись":
        return await delete_record_menu(update, context)
    elif text == "💾 Экспорт данных":
        return await export_menu(update, context)
    elif text == "🧹 Очистить всё":
        return await clear_all_confirm(update, context)
    elif text == "📋 Статистика":
        return await show_statistics(update, context)
    elif text == "🔙 Назад":
        return await start(update, context)

# Обработчики для добавления закупки
async def start_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало добавления закупки"""
    await update.message.reply_text(
        "📅 Введите дату закупки (в формате ДД.ММ.ГГГГ) или отправьте 'сегодня' для текущей даты:",
        reply_markup=bot.get_back_keyboard()
    )
    return PURCHASE_DATE

async def purchase_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка даты закупки"""
    if update.message.text == "🔙 Назад":
        await update.message.reply_text("Главное меню:", reply_markup=bot.get_main_keyboard())
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
        await update.message.reply_text(
            "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ (например, 27.02.2024) или напишите 'сегодня':"
        )
        return PURCHASE_DATE

async def purchase_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка названия товара"""
    if update.message.text == "🔙 Назад":
        await update.message.reply_text("Главное меню:", reply_markup=bot.get_main_keyboard())
        return ConversationHandler.END
    
    context.user_data['purchase_name'] = update.message.text
    await update.message.reply_text("🎨 Введите цвет товара:")
    return PURCHASE_COLOR

async def purchase_color(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка цвета товара"""
    if update.message.text == "🔙 Назад":
        await update.message.reply_text("Главное меню:", reply_markup=bot.get_main_keyboard())
        return ConversationHandler.END
    
    context.user_data['purchase_color'] = update.message.text
    await update.message.reply_text("📏 Введите размер товара:")
    return PURCHASE_SIZE

async def purchase_size(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка размера товара"""
    if update.message.text == "🔙 Назад":
        await update.message.reply_text("Главное меню:", reply_markup=bot.get_main_keyboard())
        return ConversationHandler.END
    
    context.user_data['purchase_size'] = update.message.text
    await update.message.reply_text("🔢 Введите количество:")
    return PURCHASE_QUANTITY

async def purchase_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка количества товара"""
    if update.message.text == "🔙 Назад":
        await update.message.reply_text("Главное меню:", reply_markup=bot.get_main_keyboard())
        return ConversationHandler.END
    
    try:
        quantity = int(update.message.text)
        if quantity <= 0:
            raise ValueError
        context.user_data['purchase_quantity'] = quantity
        await update.message.reply_text("💵 Введите цену за одну штуку:")
        return PURCHASE_PRICE
    except ValueError:
        await update.message.reply_text("❌ Введите корректное количество (целое положительное число):")
        return PURCHASE_QUANTITY

async def purchase_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка цены товара и сохранение закупки"""
    if update.message.text == "🔙 Назад":
        await update.message.reply_text("Главное меню:", reply_markup=bot.get_main_keyboard())
        return ConversationHandler.END
    
    try:
        price = float(update.message.text.replace(',', '.'))
        if price <= 0:
            raise ValueError
        
        # Сохранение в базу данных
        conn = sqlite3.connect(bot.db_path)
        cursor = conn.cursor()
        
        total_cost = price * context.user_data['purchase_quantity']
        
        cursor.execute('''
            INSERT INTO purchases (date, name, color, size, quantity, price_per_unit, total_cost, remaining_quantity)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            context.user_data['purchase_date'],
            context.user_data['purchase_name'],
            context.user_data['purchase_color'],
            context.user_data['purchase_size'],
            context.user_data['purchase_quantity'],
            price,
            total_cost,
            context.user_data['purchase_quantity']
        ))
        
        conn.commit()
        conn.close()
        
        # Формирование сообщения об успешном добавлении
        success_message = f"""
✅ **Закупка успешно добавлена!**

📅 Дата: {context.user_data['purchase_date']}
🏷 Название: {context.user_data['purchase_name']}
🎨 Цвет: {context.user_data['purchase_color']}
📏 Размер: {context.user_data['purchase_size']}
🔢 Количество: {context.user_data['purchase_quantity']}
💵 Цена за штуку: {price:,.2f} руб.
💰 Общая стоимость: {total_cost:,.2f} руб.
"""
        await update.message.reply_text(
            success_message,
            reply_markup=bot.get_main_keyboard(),
            parse_mode='Markdown'
        )
        
        # Очистка данных пользователя
        context.user_data.clear()
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Введите корректную цену (положительное число):")
        return PURCHASE_PRICE

# Обработчики для продаж
async def start_sale(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало процесса продажи"""
    conn = sqlite3.connect(bot.db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, date, name, color, size, remaining_quantity, price_per_unit
        FROM purchases
        WHERE remaining_quantity > 0
        ORDER BY date DESC, name ASC
    ''')
    
    items = cursor.fetchall()
    conn.close()
    
    if not items:
        await update.message.reply_text(
            "❌ Нет товаров в остатках для продажи.",
            reply_markup=bot.get_main_keyboard()
        )
        return
    
    keyboard = []
    for item in items:
        item_id, date, name, color, size, quantity, price = item
        button_text = f"{date} | {name} | {color} | {size} | остаток: {quantity}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"sell_{item_id}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")])
    
    await update.message.reply_text(
        "💰 Выберите товар для продажи:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_sale_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора товара для продажи"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "back_to_main":
        await query.edit_message_text("Главное меню:", reply_markup=None)
        await query.message.reply_text("Выберите действие:", reply_markup=bot.get_main_keyboard())
        return
    
    if query.data.startswith("sell_"):
        item_id = int(query.data.split("_")[1])
        context.user_data['sale_item_id'] = item_id
        
        # Получаем информацию о товаре
        conn = sqlite3.connect(bot.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT name, color, size, remaining_quantity, price_per_unit
            FROM purchases WHERE id = ?
        ''', (item_id,))
        item = cursor.fetchone()
        conn.close()
        
        if item:
            name, color, size, quantity, purchase_price = item
            context.user_data['purchase_price'] = purchase_price
            await query.edit_message_text(
                f"Выбран товар: {name} | {color} | {size}\n"
                f"Доступно: {quantity} шт.\n"
                f"Цена закупки: {purchase_price:,.2f} руб./шт.\n\n"
                f"💰 Введите цену продажи за одну штуку:"
            )
            return SALE_PRICE
    
    # Обработка выбора периода для аналитики
    if query.data.startswith("period_"):
        period = query.data.split("_")[1]
        if context.user_data.get('current_action') == 'profit':
            await show_profit_data(query, context, period)
        elif context.user_data.get('current_action') == 'sales':
            await show_sales_data(query, context, period)

async def sale_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка цены продажи"""
    try:
        sale_price = float(update.message.text.replace(',', '.'))
        if sale_price <= 0:
            raise ValueError
        
        item_id = context.user_data['sale_item_id']
        
        # Получаем информацию о товаре
        conn = sqlite3.connect(bot.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT date, name, color, size, remaining_quantity, price_per_unit
            FROM purchases WHERE id = ?
        ''', (item_id,))
        
        item = cursor.fetchone()
        
        if item:
            purchase_date, name, color, size, remaining_quantity, purchase_price = item
            
            if remaining_quantity > 0:
                # Вычисляем данные для продажи
                quantity_sold = 1  # Продаем по одной штуке
                total_sale = sale_price * quantity_sold
                profit = (sale_price - purchase_price) * quantity_sold
                
                # Вычисляем дни между закупкой и продажей
                purchase_date_obj = datetime.strptime(purchase_date, "%d.%m.%Y")
                sale_date = datetime.now().strftime("%d.%m.%Y")
                sale_date_obj = datetime.now()
                days_to_sell = (sale_date_obj - purchase_date_obj).days
                
                # Добавляем продажу
                cursor.execute('''
                    INSERT INTO sales (purchase_id, sale_date, quantity_sold, sale_price_per_unit,
                                     total_sale, profit, days_to_sell)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (item_id, sale_date, quantity_sold, sale_price, total_sale, profit, days_to_sell))
                
                # Обновляем остатки
                cursor.execute('''
                    UPDATE purchases SET remaining_quantity = remaining_quantity - ?
                    WHERE id = ?
                ''', (quantity_sold, item_id))
                
                conn.commit()
                
                # Формируем сообщение об успешной продаже
                profit_text = f"Прибыль: +{profit:,.2f} руб." if profit >= 0 else f"Убыток: {profit:,.2f} руб."
                margin_percent = ((sale_price - purchase_price) / purchase_price * 100) if purchase_price > 0 else 0
                
                success_message = f"""
✅ **Продажа успешно оформлена!**

🏷 Товар: {name} | {color} | {size}
💰 Цена продажи: {sale_price:,.2f} руб.
💵 Цена закупки: {purchase_price:,.2f} руб.
{profit_text}
📊 Маржинальность: {margin_percent:+.1f}%
📅 Время продажи: {days_to_sell} дней
📦 Осталось: {remaining_quantity - quantity_sold} шт.
"""
                await update.message.reply_text(
                    success_message,
                    reply_markup=bot.get_main_keyboard(),
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(
                    "❌ Товар закончился в остатках.",
                    reply_markup=bot.get_main_keyboard()
                )
        
        conn.close()
        context.user_data.clear()
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Введите корректную цену (положительное число):")
        return SALE_PRICE

# Аналитические функции
async def show_profit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ меню прибыли"""
    context.user_data['current_action'] = 'profit'
    await update.message.reply_text(
        "📊 Выберите период для анализа прибыли:",
        reply_markup=bot.get_period_keyboard()
    )

async def show_sales_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ меню продаж"""
    context.user_data['current_action'] = 'sales'
    await update.message.reply_text(
        "📈 Выберите период для анализа продаж:",
        reply_markup=bot.get_period_keyboard()
    )

async def show_profit_data(query, context: ContextTypes.DEFAULT_TYPE, period: str):
    """Показ данных о прибыли"""
    date_filter = get_date_filter(period)
    
    conn = sqlite3.connect(bot.db_path)
    
    # Создаем пользовательскую функцию для сравнения дат
    def date_compare(date_str, filter_str):
        try:
            d1 = datetime.strptime(date_str, "%d.%m.%Y")
            d2 = datetime.strptime(filter_str, "%d.%m.%Y")
            return 1 if d1 >= d2 else 0
        except:
            return 0
    
    conn.create_function("date_compare", 2, date_compare)
    cursor = conn.cursor()
    
    if period == "all":
        cursor.execute('''
            SELECT SUM(profit), COUNT(*), SUM(total_sale), AVG(profit),
                   MAX(profit), MIN(profit)
            FROM sales
        ''')
    else:
        cursor.execute('''
            SELECT SUM(profit), COUNT(*), SUM(total_sale), AVG(profit),
                   MAX(profit), MIN(profit)
            FROM sales
            WHERE date_compare(sale_date, ?) = 1
        ''', (date_filter,))
    
    result = cursor.fetchone()
    total_profit, sales_count, total_sales, avg_profit, max_profit, min_profit = result
    
    # Получаем детальную информацию
    if period == "all":
        cursor.execute('''
            SELECT s.sale_date, p.name, p.color, p.size, s.quantity_sold,
                   s.sale_price_per_unit, s.profit, s.days_to_sell, p.price_per_unit
            FROM sales s
            JOIN purchases p ON s.purchase_id = p.id
            ORDER BY s.sale_date DESC
            LIMIT 15
        ''')
    else:
        cursor.execute('''
            SELECT s.sale_date, p.name, p.color, p.size, s.quantity_sold,
                   s.sale_price_per_unit, s.profit, s.days_to_sell, p.price_per_unit
            FROM sales s
            JOIN purchases p ON s.purchase_id = p.id
            WHERE date_compare(s.sale_date, ?) = 1
            ORDER BY s.sale_date DESC
            LIMIT 15
        ''', (date_filter,))
    
    sales_details = cursor.fetchall()
    conn.close()
    
    period_name = get_period_name(period)
    
    if not total_profit:
        total_profit = 0
        sales_count = 0
        total_sales = 0
        avg_profit = 0
        max_profit = 0
        min_profit = 0
    
    message = f"""
📊 **Прибыль за {period_name}**

💰 Общая прибыль: {total_profit:,.2f} руб.
📈 Продаж: {sales_count} шт.
💵 Оборот: {total_sales:,.2f} руб.
📊 Средняя прибыль: {avg_profit:,.2f} руб.
📈 Максимальная: {max_profit:,.2f} руб.
📉 Минимальная: {min_profit:,.2f} руб.
"""
    
    if sales_details:
        message += "\n\n📋 **Последние продажи:**\n"
        for sale in sales_details:
            date, name, color, size, qty, sale_price, profit, days, purchase_price = sale
            profit_icon = "📈" if profit >= 0 else "📉"
            margin = ((sale_price - purchase_price) / purchase_price * 100) if purchase_price > 0 else 0
            message += f"\n{profit_icon} {date} | {name} | {color} | {size}"
            message += f"\n   💰 {sale_price:,.2f}р. | 📊 {profit:+.2f}р. ({margin:+.1f}%) | ⏱ {days}д.\n"
    
    await query.edit_message_text(message, parse_mode='Markdown')

async def show_sales_data(query, context: ContextTypes.DEFAULT_TYPE, period: str):
    """Показ данных о продажах"""
    date_filter = get_date_filter(period)
    
    conn = sqlite3.connect(bot.db_path)
    
    # Создаем пользовательскую функцию для сравнения дат
    def date_compare(date_str, filter_str):
        try:
            d1 = datetime.strptime(date_str, "%d.%m.%Y")
            d2 = datetime.strptime(filter_str, "%d.%m.%Y")
            return 1 if d1 >= d2 else 0
        except:
            return 0
    
    conn.create_function("date_compare", 2, date_compare)
    cursor = conn.cursor()
    
    if period == "all":
        cursor.execute('''
            SELECT s.sale_date, p.name, p.color, p.size, s.quantity_sold,
                   s.sale_price_per_unit, s.total_sale, s.profit, s.days_to_sell,
                   p.price_per_unit
            FROM sales s
            JOIN purchases p ON s.purchase_id = p.id
            ORDER BY s.sale_date DESC
        ''')
    else:
        cursor.execute('''
            SELECT s.sale_date, p.name, p.color, p.size, s.quantity_sold,
                   s.sale_price_per_unit, s.total_sale, s.profit, s.days_to_sell,
                   p.price_per_unit
            FROM sales s
            JOIN purchases p ON s.purchase_id = p.id
            WHERE date_compare(s.sale_date, ?) = 1
            ORDER BY s.sale_date DESC
        ''', (date_filter,))
    
    sales = cursor.fetchall()
    conn.close()
    
    period_name = get_period_name(period)
    
    if not sales:
        message = f"📈 **Продажи за {period_name}**\n\nПродаж не было."
    else:
        total_sales = sum(sale[6] for sale in sales)  # total_sale
        total_profit = sum(sale[7] for sale in sales)  # profit
        avg_days = sum(sale[8] for sale in sales) / len(sales)  # days_to_sell
        avg_margin = sum(((sale[5] - sale[9]) / sale[9] * 100) if sale[9] > 0 else 0 for sale in sales) / len(sales)
        
        message = f"""
📈 **Продажи за {period_name}**

📊 Всего продаж: {len(sales)}
💰 Общая сумма: {total_sales:,.2f} руб.
📈 Прибыль: {total_profit:,.2f} руб.
⏱ Среднее время продажи: {avg_days:.1f} дней
📊 Средняя маржинальность: {avg_margin:.1f}%

📋 **Детали:**
"""
        for sale in sales[:12]:  # Показываем последние 12
            (sale_date, name, color, size, qty_sold, sale_price,
             total_sale, profit, days_to_sell, purchase_price) = sale
            
            profit_icon = "📈" if profit >= 0 else "📉"
            margin = ((sale_price - purchase_price) / purchase_price * 100) if purchase_price > 0 else 0
            
            message += f"\n{profit_icon} {sale_date}"
            message += f"\n🏷 {name} | {color} | {size}"
            message += f"\n💰 {sale_price:,.2f}р. | 📊 {profit:+.2f}р. ({margin:+.1f}%) | ⏱ {days_to_sell}д.\n"
        
        if len(sales) > 12:
            message += f"\n... и ещё {len(sales) - 12} продаж"
    
    await query.edit_message_text(message, parse_mode='Markdown')

async def show_inventory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ остатков"""
    conn = sqlite3.connect(bot.db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT date, name, color, size, remaining_quantity, price_per_unit,
               (remaining_quantity * price_per_unit) as total_value
        FROM purchases
        WHERE remaining_quantity > 0
        ORDER BY date DESC, name ASC
    ''')
    
    inventory = cursor.fetchall()
    conn.close()
    
    if not inventory:
        await update.message.reply_text(
            "📦 **Остатки**\n\nНет товаров в остатках.",
            reply_markup=bot.get_back_keyboard(),
            parse_mode='Markdown'
        )
        return
    
    total_value = sum(item[6] for item in inventory)
    total_items = sum(item[4] for item in inventory)
    
    message = f"""
📦 **Остатки товаров**

📊 Всего позиций: {len(inventory)}
🔢 Общее количество: {total_items} шт.
💰 Общая стоимость: {total_value:,.2f} руб.

📋 **Детали:**
"""
    
    for item in inventory:
        date, name, color, size, quantity, price, value = item
        message += f"\n📅 {date}"
        message += f"\n🏷 {name} | {color} | {size}"
        message += f"\n📊 Количество: {quantity} шт. | Цена: {price:,.2f} руб./шт."
        message += f"\n💰 Стоимость: {value:,.2f} руб.\n"
    
    await update.message.reply_text(
        message,
        reply_markup=bot.get_back_keyboard(),
        parse_mode='Markdown'
    )

async def show_liquidity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ ликвидности товаров"""
    conn = sqlite3.connect(bot.db_path)
    cursor = conn.cursor()
    
    # Получаем данные о продажах для расчета ликвидности
    cursor.execute('''
        SELECT p.name, p.color, p.size,
               AVG(s.days_to_sell) as avg_days,
               AVG((s.sale_price_per_unit - p.price_per_unit) / p.price_per_unit * 100) as avg_profit_percent,
               SUM(s.quantity_sold) as total_sold,
               COUNT(s.id) as sales_count,
               AVG(s.profit) as avg_profit
        FROM purchases p
        JOIN sales s ON p.id = s.purchase_id
        GROUP BY p.name, p.color, p.size
        HAVING sales_count >= 1
        ORDER BY avg_days ASC, avg_profit_percent DESC, total_sold DESC
    ''')
    
    liquidity_data = cursor.fetchall()
    conn.close()
    
    if not liquidity_data:
        await update.message.reply_text(
            "⚡ **Ликвидность товаров**\n\nНедостаточно данных о продажах для анализа ликвидности.",
            reply_markup=bot.get_back_keyboard(),
            parse_mode='Markdown'
        )
        return
    
    message = """
⚡ **Ликвидность товаров**

(Отсортировано по скорости продажи, прибыльности и объему продаж)

📊 **Топ ликвидных позиций:**
"""
    
    for i, item in enumerate(liquidity_data[:10], 1):
        name, color, size, avg_days, avg_profit_percent, total_sold, sales_count, avg_profit = item
        
        # Определяем уровень ликвидности
        if avg_days <= 7:
            liquidity_icon = "🔥"
            liquidity_level = "Очень высокая"
        elif avg_days <= 30:
            liquidity_icon = "⚡"
            liquidity_level = "Высокая"
        elif avg_days <= 90:
            liquidity_icon = "📈"
            liquidity_level = "Средняя"
        else:
            liquidity_icon = "📉"
            liquidity_level = "Низкая"
        
        message += f"\n{i}. {liquidity_icon} {name} | {color} | {size}"
        message += f"\n   ⏱ Среднее время продажи: {avg_days:.1f} дней"
        message += f"\n   📊 Средняя прибыль: {avg_profit_percent:.1f}% ({avg_profit:+.2f} руб.)"
        message += f"\n   🔢 Продано: {total_sold} шт. ({sales_count} продаж)"
        message += f"\n   📈 Ликвидность: {liquidity_level}\n"
    
    await update.message.reply_text(
        message,
        reply_markup=bot.get_back_keyboard(),
        parse_mode='Markdown'
    )

async def delete_record_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню удаления записей"""
    keyboard = [
        [InlineKeyboardButton("🛒 Удалить закупку", callback_data="delete_purchase")],
        [InlineKeyboardButton("💰 Удалить продажу", callback_data="delete_sale")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ]
    
    await update.message.reply_text(
        "🗑 **Удаление записей**\n\nВыберите тип записи для удаления:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def export_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню экспорта данных"""
    keyboard = [
        [InlineKeyboardButton("📄 Текстовый файл (.txt)", callback_data="export_txt")],
        [InlineKeyboardButton("📊 CSV файл (.csv)", callback_data="export_csv")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ]
    
    await update.message.reply_text(
        "💾 **Экспорт данных**\n\nВыберите формат экспорта:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def export_data(update: Update, context: ContextTypes.DEFAULT_TYPE, format_type: str):
    """Экспорт данных в выбранном формате"""
    conn = sqlite3.connect(bot.db_path)
    cursor = conn.cursor()
    
    # Получаем все закупки
    cursor.execute('''
        SELECT date, name, color, size, quantity, price_per_unit, total_cost, remaining_quantity
        FROM purchases ORDER BY date DESC
    ''')
    purchases = cursor.fetchall()
    
    # Получаем все продажи
    cursor.execute('''
        SELECT s.sale_date, p.name, p.color, p.size, s.quantity_sold,
               s.sale_price_per_unit, s.total_sale, s.profit, s.days_to_sell,
               p.price_per_unit, p.date
        FROM sales s
        JOIN purchases p ON s.purchase_id = p.id
        ORDER BY s.sale_date DESC
    ''')
    sales = cursor.fetchall()
    
    conn.close()
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    if format_type == 'txt':
        filename = f"business_export_{timestamp}.txt"
        content = generate_txt_export(purchases, sales)
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content)
    elif format_type == 'csv':
        filename = f"business_export_{timestamp}.csv"
        generate_csv_export(purchases, sales, filename)
    
    # Отправляем файл пользователю
    try:
        with open(filename, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=filename,
                caption=f"📊 Экспорт данных в формате {format_type.upper()} выполнен успешно!"
            )
        
        # Удаляем временный файл
        os.remove(filename)
        
        await update.message.reply_text(
            "✅ Данные экспортированы!",
            reply_markup=bot.get_main_keyboard()
        )
    except Exception as e:
        await update.message.reply_text(
            f"❌ Ошибка при экспорте: {str(e)}",
            reply_markup=bot.get_main_keyboard()
        )

def generate_txt_export(purchases, sales):
    """Генерация текстового экспорта"""
    content = f"📊 ЭКСПОРТ ДАННЫХ - {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
    content += "="*50 + "\n\n"
    
    # Закупки
    content += "🛒 ЗАКУПКИ:\n"
    content += "-"*30 + "\n"
    total_purchase_cost = 0
    
    for purchase in purchases:
        date, name, color, size, quantity, price, total_cost, remaining = purchase
        total_purchase_cost += total_cost
        content += f"📅 {date} | {name} | {color} | {size}\n"
        content += f"   Количество: {quantity} шт. | Цена: {price:,.2f} руб./шт.\n"
        content += f"   Стоимость: {total_cost:,.2f} руб. | Остаток: {remaining} шт.\n\n"
    
    content += f"💰 Общая стоимость закупок: {total_purchase_cost:,.2f} руб.\n\n"
    
    # Продажи
    content += "💰 ПРОДАЖИ:\n"
    content += "-"*30 + "\n"
    total_sales_amount = 0
    total_profit = 0
    
    for sale in sales:
        (sale_date, name, color, size, qty_sold, sale_price,
         total_sale, profit, days_to_sell, purchase_price, purchase_date) = sale
        total_sales_amount += total_sale
        total_profit += profit
        margin = ((sale_price - purchase_price) / purchase_price * 100) if purchase_price > 0 else 0
        
        content += f"📅 {sale_date} | {name} | {color} | {size}\n"
        content += f"   Продано: {qty_sold} шт. | Цена продажи: {sale_price:,.2f} руб./шт.\n"
        content += f"   Цена закупки: {purchase_price:,.2f} руб./шт. | Закупка: {purchase_date}\n"
        content += f"   Сумма: {total_sale:,.2f} руб. | Прибыль: {profit:,.2f} руб. ({margin:+.1f}%)\n"
        content += f"   Время продажи: {days_to_sell} дней\n\n"
    
    content += f"📈 Общая сумма продаж: {total_sales_amount:,.2f} руб.\n"
    content += f"💰 Общая прибыль: {total_profit:,.2f} руб.\n\n"
    
    # Статистика
    if purchases and sales:
        roi = (total_profit / total_purchase_cost) * 100 if total_purchase_cost > 0 else 0
        content += "📊 ОБЩАЯ СТАТИСТИКА:\n"
        content += "-"*30 + "\n"
        content += f"🛒 Закупок: {len(purchases)}\n"
        content += f"💰 Продаж: {len(sales)}\n"
        content += f"📈 ROI: {roi:.1f}%\n"
        content += f"📦 Товаров в остатках: {sum(p[7] for p in purchases)} шт.\n"
    
    return content

def generate_csv_export(purchases, sales, filename):
    """Генерация CSV экспорта"""
    import csv
    
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile, delimiter=';')
        
        # Заголовок
        writer.writerow([f"Экспорт данных от {datetime.now().strftime('%d.%m.%Y %H:%M')}"])
        writer.writerow([])
        
        # Закупки
        writer.writerow(["ЗАКУПКИ"])
        writer.writerow(["Дата", "Название", "Цвет", "Размер", "Количество",
                        "Цена за шт", "Общая стоимость", "Остаток"])
        
        for purchase in purchases:
            writer.writerow(list(purchase))
        
        writer.writerow([])
        
        # Продажи
        writer.writerow(["ПРОДАЖИ"])
        writer.writerow(["Дата продажи", "Название", "Цвет", "Размер", "Продано",
                        "Цена продажи", "Сумма", "Прибыль", "Дней до продажи",
                        "Цена закупки", "Дата закупки"])
        
        for sale in sales:
            writer.writerow(list(sale))

async def clear_all_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение очистки всех данных"""
    keyboard = [
        [InlineKeyboardButton("✅ Да, очистить все", callback_data="confirm_clear_all")],
        [InlineKeyboardButton("❌ Отмена", callback_data="back_to_main")]
    ]
    
    await update.message.reply_text(
        "⚠️ **ВНИМАНИЕ!**\n\nВы действительно хотите удалить ВСЕ данные?\n"
        "Это действие нельзя отменить!\n\n"
        "Будут удалены:\n• Все закупки\n• Все продажи\n• Вся статистика",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def show_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ общей статистики"""
    conn = sqlite3.connect(bot.db_path)
    cursor = conn.cursor()
    
    # Общие данные
    cursor.execute('SELECT COUNT(*), SUM(total_cost), SUM(remaining_quantity) FROM purchases')
    purchase_stats = cursor.fetchone()
    total_purchases, total_purchase_cost, total_remaining = purchase_stats
    
    cursor.execute('SELECT COUNT(*), SUM(total_sale), SUM(profit) FROM sales')
    sales_stats = cursor.fetchone()
    total_sales_count, total_sales_amount, total_profit = sales_stats
    
    # Топ товары по прибыльности
    cursor.execute('''
        SELECT p.name, SUM(s.profit) as total_profit, COUNT(s.id) as sales_count,
               AVG(s.days_to_sell) as avg_days
        FROM purchases p
        JOIN sales s ON p.id = s.purchase_id
        GROUP BY p.name
        ORDER BY total_profit DESC
        LIMIT 5
    ''')
    top_profitable = cursor.fetchall()
    
    # Средняя маржинальность
    cursor.execute('''
        SELECT AVG((s.sale_price_per_unit - p.price_per_unit) / p.price_per_unit * 100) as avg_margin
        FROM sales s
        JOIN purchases p ON s.purchase_id = p.id
    ''')
    avg_margin = cursor.fetchone()[0] or 0
    
    # Средний срок продажи
    cursor.execute('SELECT AVG(days_to_sell) FROM sales')
    avg_sell_time = cursor.fetchone()[0] or 0
    
    conn.close()
    
    # Формируем статистику
    if not total_purchase_cost:
        total_purchase_cost = 0
    if not total_sales_amount:
        total_sales_amount = 0
    if not total_profit:
        total_profit = 0
    
    roi = (total_profit / total_purchase_cost * 100) if total_purchase_cost > 0 else 0
    
    message = f"""
📋 **Общая статистика бизнеса**

📊 **Основные показатели:**
🛒 Закупок: {total_purchases or 0}
💰 Продаж: {total_sales_count or 0}
📦 Товаров в остатках: {total_remaining or 0} шт.

💵 **Финансы:**
📉 Потрачено на закупки: {total_purchase_cost:,.2f} руб.
📈 Выручка с продаж: {total_sales_amount:,.2f} руб.
💰 Общая прибыль: {total_profit:,.2f} руб.
📊 ROI: {roi:.1f}%
📈 Средняя маржинальность: {avg_margin:.1f}%
⏱ Средний срок продажи: {avg_sell_time:.1f} дней
"""
    
    if top_profitable:
        message += "\n\n🏆 **Топ товары по прибыли:**"
        for i, (name, profit, sales_count, avg_days) in enumerate(top_profitable, 1):
            message += f"\n{i}. {name}: {profit:,.2f} руб. ({sales_count} продаж, {avg_days:.1f}д.)"
    
    await update.message.reply_text(
        message,
        reply_markup=bot.get_back_keyboard(),
        parse_mode='Markdown'
    )

# Вспомогательные функции
def get_date_filter(period: str) -> str:
    """Получить дату для фильтрации по периоду - возвращает начальную дату периода"""
    today = datetime.now()
    if period == "today":
        # Для сегодня берем последние 24 часа
        filter_date = today - timedelta(days=1)
    elif period == "week":
        # Последние 7 дней
        filter_date = today - timedelta(days=7)
    elif period == "month":
        # Последние 30 дней
        filter_date = today - timedelta(days=30)
    elif period == "3months":
        # Последние 90 дней
        filter_date = today - timedelta(days=90)
    else:  # all
        filter_date = datetime(2000, 1, 1)
    
    return filter_date.strftime("%d.%m.%Y")

def get_period_name(period: str) -> str:
    """Получить название периода"""
    period_names = {
        "today": "последние 24 часа",
        "week": "последнюю неделю",
        "month": "последний месяц",
        "3months": "последние 3 месяца",
        "all": "всё время"
    }
    return period_names.get(period, "всё время")

async def handle_callback_queries(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка callback запросов"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "back_to_main":
        await query.edit_message_text("Главное меню:")
        await query.message.reply_text("Выберите действие:", reply_markup=bot.get_main_keyboard())
        return
    
    if query.data == "confirm_clear_all":
        # Очистка всех данных
        conn = sqlite3.connect(bot.db_path)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM sales')
        cursor.execute('DELETE FROM purchases')
        conn.commit()
        conn.close()
        
        await query.edit_message_text("✅ Все данные успешно удалены!")
        await query.message.reply_text("Главное меню:", reply_markup=bot.get_main_keyboard())
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
    
    if query.data in ["export_txt", "export_csv"]:
        format_type = query.data.split("_")[1]
        await query.edit_message_text("📊 Генерирую экспорт данных...")
        await export_data(query, context, format_type)
        return
    
    # Обработка продаж и периодов
    await handle_sale_callback(update, context)

async def show_delete_purchases(query, context: ContextTypes.DEFAULT_TYPE):
    """Показ списка закупок для удаления"""
    conn = sqlite3.connect(bot.db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, date, name, color, size, quantity, price_per_unit, remaining_quantity
        FROM purchases ORDER BY date DESC LIMIT 20
    ''')
    
    purchases = cursor.fetchall()
    conn.close()
    
    if not purchases:
        await query.edit_message_text("❌ Нет закупок для удаления.")
        return
    
    keyboard = []
    for purchase in purchases:
        purchase_id, date, name, color, size, quantity, price, remaining = purchase
        status = f"({remaining}/{quantity})" if remaining < quantity else f"({remaining})"
        button_text = f"{date} | {name} | {color} | {size} | {status} | {price:,.2f}р."
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"delete_p_{purchase_id}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")])
    
    await query.edit_message_text(
        "🗑 **Удаление закупки**\n\nВыберите закупку для удаления:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def show_delete_sales(query, context: ContextTypes.DEFAULT_TYPE):
    """Показ списка продаж для удаления"""
    conn = sqlite3.connect(bot.db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT s.id, s.sale_date, p.name, p.color, p.size, s.quantity_sold,
               s.sale_price_per_unit, s.profit
        FROM sales s
        JOIN purchases p ON s.purchase_id = p.id
        ORDER BY s.sale_date DESC LIMIT 20
    ''')
    
    sales = cursor.fetchall()
    conn.close()
    
    if not sales:
        await query.edit_message_text("❌ Нет продаж для удаления.")
        return
    
    keyboard = []
    for sale in sales:
        sale_id, date, name, color, size, quantity, price, profit = sale
        profit_text = f"+{profit:,.2f}" if profit >= 0 else f"{profit:,.2f}"
        button_text = f"{date} | {name} | {color} | {size} | {price:,.2f}р. | {profit_text}р."
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"delete_s_{sale_id}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")])
    
    await query.edit_message_text(
        "🗑 **Удаление продажи**\n\nВыберите продажу для удаления:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def delete_purchase(query, context: ContextTypes.DEFAULT_TYPE, purchase_id: int):
    """Удаление закупки"""
    conn = sqlite3.connect(bot.db_path)
    cursor = conn.cursor()
    
    # Проверяем, есть ли продажи по этой закупке
    cursor.execute('SELECT COUNT(*) FROM sales WHERE purchase_id = ?', (purchase_id,))
    sales_count = cursor.fetchone()[0]
    
    if sales_count > 0:
        await query.edit_message_text(
            "❌ Нельзя удалить закупку, по которой уже есть продажи.\n"
            "Сначала удалите все связанные продажи.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]])
        )
    else:
        cursor.execute('DELETE FROM purchases WHERE id = ?', (purchase_id,))
        conn.commit()
        conn.close()
        
        await query.edit_message_text("✅ Закупка удалена!")
        await query.message.reply_text("Главное меню:", reply_markup=bot.get_main_keyboard())

async def delete_sale(query, context: ContextTypes.DEFAULT_TYPE, sale_id: int):
    """Удаление продажи"""
    conn = sqlite3.connect(bot.db_path)
    cursor = conn.cursor()
    
    # Получаем информацию о продаже
    cursor.execute('''
        SELECT purchase_id, quantity_sold FROM sales WHERE id = ?
    ''', (sale_id,))
    
    sale_info = cursor.fetchone()
    
    if sale_info:
        purchase_id, quantity_sold = sale_info
        
        # Возвращаем товар в остатки
        cursor.execute('''
            UPDATE purchases SET remaining_quantity = remaining_quantity + ?
            WHERE id = ?
        ''', (quantity_sold, purchase_id))
        
        # Удаляем продажу
        cursor.execute('DELETE FROM sales WHERE id = ?', (sale_id,))
        
        conn.commit()
    
    conn.close()
    
    await query.edit_message_text("✅ Продажа удалена, товар возвращен в остатки!")
    await query.message.reply_text("Главное меню:", reply_markup=bot.get_main_keyboard())

# Обработчик отмены разговора
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена текущего разговора"""
    context.user_data.clear()
    await update.message.reply_text(
        "❌ Операция отменена.",
        reply_markup=bot.get_main_keyboard()
    )
    return ConversationHandler.END

def main():
    """Запуск бота"""
    application = Application.builder().token(bot.token).build()
    
    # Обработчик добавления закупки
    purchase_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^➕ Добавить закупку$"), start_purchase)],
        states={
            PURCHASE_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, purchase_date)],
            PURCHASE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, purchase_name)],
            PURCHASE_COLOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, purchase_color)],
            PURCHASE_SIZE: [MessageHandler(filters.TEXT & ~filters.COMMAND, purchase_size)],
            PURCHASE_QUANTITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, purchase_quantity)],
            PURCHASE_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, purchase_price)],
        },
        fallbacks=[CommandHandler('cancel', cancel), MessageHandler(filters.Regex("^🔙 Назад$"), cancel)],
    )
    
    # Обработчик продаж
    sale_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_sale_callback, pattern="^sell_")],
        states={
            SALE_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, sale_price)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(purchase_handler)
    application.add_handler(sale_handler)
    application.add_handler(CallbackQueryHandler(handle_callback_queries))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_main_menu))
    
    print("🤖 Бот запущен! Нажмите Ctrl+C для остановки.")
    application.run_polling()

if __name__ == '__main__':
    main()
