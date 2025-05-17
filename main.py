from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler
import sqlite3
import jdatetime
from datetime import datetime

# 📌 اتصال به دیتابیس و ایجاد جدول‌ها
conn = sqlite3.connect("payments.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY, user_id INTEGER, amount REAL)")
cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, name TEXT, location TEXT, status TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS records (user_id INTEGER PRIMARY KEY, max_total REAL)")
conn.commit()

# 📌 لیست ماه‌های شمسی به فارسی
persian_months = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"
]

# 📌 بررسی و دریافت نام کاربر
async def handle_message(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    text = update.message.text.strip()

    cursor.execute("SELECT name, location, status FROM users WHERE user_id=?", (user_id,))
    user_data = cursor.fetchone()

    if user_data is None:
        context.user_data['temp_name'] = text

        await update.message.reply_text(
            f"آیا مطمئن هستید که می‌خواهید نام شما به عنوان «{text}» ثبت شود؟",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ بله", callback_data=f'confirm_name_{text}')],
                [InlineKeyboardButton("❌ خیر", callback_data='cancel_name')]
            ]))
    else:
        name, location, status = user_data
        if status == "waiting_for_payment":
            await add_payment(update, context, name, location)
        else:
            await update.message.reply_text(f"👋 خوش اومدی {name}!\nمبلغ واریزی رو بفرس تا ذخیره کنم.")
# 📌 ثبت و نمایش واریزی
async def add_payment(update: Update, context: CallbackContext, user_name: str, location: str) -> None:
  user_id = update.message.from_user.id
  text = update.message.text.strip()

  try:
      amount = float(text) * 1000  # 👈 ضرب مقدار ورودی در ۱۰۰۰
      cursor.execute("INSERT INTO payments (user_id, amount) VALUES (?, ?)", (user_id, amount))
      conn.commit()

      cursor.execute("SELECT SUM(amount) FROM payments WHERE user_id=?", (user_id,))
      total_amount = cursor.fetchone()[0] or 0.0  

      cursor.execute("SELECT max_total FROM records WHERE user_id=?", (user_id,))
      record_data = cursor.fetchone()
      max_record = record_data[0] if record_data else 0.0  

      if total_amount > max_record:
          cursor.execute("INSERT OR REPLACE INTO records (user_id, max_total) VALUES (?, ?)", (user_id, total_amount))
          conn.commit()
          max_record = total_amount

      if not location:
          cursor.execute("SELECT location FROM users WHERE user_id=?", (user_id,))
          location_data = cursor.fetchone()
          location = location_data[0] if location_data else ""

      shamsi_date = jdatetime.date.today()
      date_shamsi = shamsi_date.strftime("%d %m")
      day, month = date_shamsi.split()
      month_farsi = persian_months[int(month)-1]
      date_farsi = f"{day} {month_farsi}"

      message = f""" {user_name} 👑"""

      if location == "آبادان":
          message += f"\n📍 آبادان"

      message += f"""

واریزی: {amount:,.0f} تومن

جمع واریزی تا این لحظه: {total_amount:,.0f} تومن🔥

🏆 رکورد واریزی: (‼️{max_record:,.0f}‼️)

{date_farsi}
"""
      await update.message.reply_text(message)
  except ValueError:
      await update.message.reply_text("❌ لطفاً فقط مبلغ را به عدد ارسال کنید.")

# 📌 دریافت موقعیت کاربر (با دکمه‌ها)
async def button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    choice = query.data

    if choice.startswith('confirm_name_'):
        confirmed_name = choice.split('_')[2]
        cursor.execute("INSERT INTO users (user_id, name, location, status) VALUES (?, ?, ?, ?)", 
                      (user_id, confirmed_name, "", "waiting_for_location"))
        conn.commit()

        await query.edit_message_text(f"✅ نام شما با موفقیت ثبت شد: {confirmed_name}")
        await query.message.reply_text(
            "آیا در دفتر آبادان هستید؟",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("بله", callback_data='bale')],
                [InlineKeyboardButton("نه", callback_data='na')]
            ]))

    elif choice == 'cancel_name':
        await query.edit_message_text("❌ ثبت نام لغو شد. لطفاً دوباره اسم خود را ارسال کنید.")

    elif choice == 'bale':
        cursor.execute("UPDATE users SET location = ?, status = ? WHERE user_id = ?", 
                      ("آبادان", "waiting_for_payment", user_id))
        conn.commit()
        await query.answer("📍 موقعیت شما به آبادان تغییر یافت.")
        await query.message.reply_text("👋 حالا می‌تونید مبلغ واریزی رو ارسال کنید.")

    elif choice == 'na':
        cursor.execute("UPDATE users SET location = ?, status = ? WHERE user_id = ?", 
                      ("", "waiting_for_payment", user_id))
        conn.commit()
        await query.answer("📍 موقعیت شما به حالت پیش‌فرض تغییر یافت.")
        await query.message.reply_text("👋 حالا می‌تونید مبلغ واریزی رو ارسال کنید.")
    # دریافت مجدد اطلاعات کاربر برای نمایش صحیح موقعیت
    cursor.execute("SELECT name, location FROM users WHERE user_id=?", (user_id,))
    user_data = cursor.fetchone()

    if user_data:
        user_name, location = user_data
        message = f"👋 خوش اومدی {user_name}!"
        if location == "آبادان":
            message += "\n📍 آبادان"
        message += "\nمبلغ واریزی رو بفرس تا ذخیره کنم."
        await query.message.reply_text(message)


# 📌 نمایش مجموع واریزی‌ها
async def get_total(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id

    cursor.execute("SELECT name, location FROM users WHERE user_id=?", (user_id,))
    user_data = cursor.fetchone()

    if not user_data:
        await update.message.reply_text("❗️ لطفاً اول اسمت رو بفرست تا ثبت بشه.")
        return

    user_name, location = user_data

    cursor.execute("SELECT SUM(amount) FROM payments WHERE user_id=?", (user_id,))
    total_amount = cursor.fetchone()[0] or 0.0  # اطمینان از اینکه عدد واقعی است

    cursor.execute("SELECT max_total FROM records WHERE user_id=?", (user_id,))
    record_data = cursor.fetchone()
    max_record = record_data[0] if record_data else 0.0  # اطمینان از اینکه عدد واقعی است

    # 📌 گرفتن تاریخ شمسی
    shamsi_date = jdatetime.date.today()
    date_shamsi = shamsi_date.strftime("%d %m")

    # تبدیل ماه به فارسی
    day, month = date_shamsi.split()
    month_farsi = persian_months[int(month)-1]
    date_farsi = f"{day} {month_farsi}"

    message = f""" {user_name} 👑"""

    if location == "آبادان":
        message += f"\n📍 آبادان"

    message += f"""

جمع واریزی تا این لحظه: {total_amount:,.0f} تومن🔥

🏆 رکورد واریزی: (‼️{max_record:,.0f}‼️)

{date_farsi}
"""

    await update.message.reply_text(message)

# 📌 ریست کردن واریزی‌ها (رکورد و نام کاربر حفظ می‌شود)
async def reset_payments(update: Update, context: CallbackContext) -> None:
    cursor.execute("DELETE FROM payments")
    conn.commit()
    await update.message.reply_text("🔄 مجموع واریزی‌ها ریست شد، اما رکورد و نام کاربر حفظ شده است.")

# 📌 ریست کامل اطلاعات
async def full_reset(update: Update, context: CallbackContext) -> None:
    cursor.execute("DELETE FROM payments")
    cursor.execute("DELETE FROM users")
    cursor.execute("DELETE FROM records")
    conn.commit()
    await update.message.reply_text("🚨 تمامی اطلاعات کاربران، واریزی‌ها و رکوردها حذف شدند! حالا از ابتدا شروع کنید.")

# 📌 شروع ربات
async def start(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id

    cursor.execute("SELECT name FROM users WHERE user_id=?", (user_id,))
    user_data = cursor.fetchone()

    if user_data:
        await update.message.reply_text(f"👋 خوش اومدی {user_data[0]}!\nمبلغ واریزی رو بفرس تا ذخیره کنم.")
    else:
        await update.message.reply_text("👋 سلام! لطفاً اسم خودت رو بفرست تا ثبت بشه.")

# 📌 اجرای ربات
def main():
    TOKEN = "7637205325:AAHT9CW8dQpWaJEYrZb73M-Kbfr5X6dRBeE"
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("total", get_total))
    application.add_handler(CommandHandler("reset", reset_payments))
    application.add_handler(CommandHandler("fullreset", full_reset))  # دستور fullreset اضافه شده
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button))  # دکمه‌ها

    print("🤖 ربات در حال اجرا است...")
    application.run_polling()

from flask import Flask
import threading

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run():
    app.run(host="0.0.0.0", port=8080)

threading.Thread(target=run).start()

if __name__ == '__main__':
    main()
