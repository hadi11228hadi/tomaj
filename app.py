import os
import time
import requests
import threading
from flask import Flask
import telebot
from datetime import datetime
from io import BytesIO

# تنظیمات از environment variables
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8107400983:AAFEasyG1_7CNKfoJHhpCWZOWMT9i641xYg')
CHAT_ID = os.environ.get('CHAT_ID', '-1003165080225')
PORT = int(os.environ.get('PORT', 5000))
UPDATE_INTERVAL = 300  # 5 دقیقه

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

def get_latest_transactions():
    """دریافت آخرین تراکنش‌ها"""
    url = "https://apilist.tronscan.org/api/transaction"
    params = {
        "sort": "-timestamp",
        "count": "true",
        "limit": 50
    }
    try:
        response = requests.get(url, params=params)
        data = response.json()
        return data.get('data', [])
    except Exception as e:
        print("Error fetching transactions:", e)
        return []

def filter_transactions(transactions):
    """فیلتر تراکنش‌های با مقدار بالاتر از صفر"""
    filtered = []
    for tx in transactions:
        amount = tx.get('amount', 0)
        try:
            if float(amount) > 0:
                filtered.append(tx)
        except (ValueError, TypeError):
            continue
    return filtered

def get_transaction_type(tx):
    """تعیین نوع تراکنش"""
    contract_type = tx.get('contractType', '')
    if contract_type == 1:
        return "Transfer"
    elif contract_type == 31:
        return "Smart Contract"
    else:
        return "Other"

def get_transaction_status(tx):
    """وضعیت تراکنش"""
    confirmed = tx.get('confirmed', False)
    revert = tx.get('revert', False)
    
    if confirmed and not revert:
        return "✅ Successful"
    elif revert:
        return "❌ Failed"
    else:
        return "⏳ Pending"

def format_transaction_content(transactions):
    """فرمت محتوای فایل"""
    if not transactions:
        return "No transactions found in the last 5 minutes\n"
    
    content = f"TRON Transactions Report\n"
    content += f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    content += f"Total transactions: {len(transactions)}\n"
    content += "=" * 60 + "\n\n"
    
    for i, tx in enumerate(transactions, 1):
        timestamp = tx.get('timestamp', '')
        if timestamp:
            time_str = datetime.fromtimestamp(timestamp/1000).strftime('%H:%M:%S')
        else:
            time_str = 'N/A'
        
        content += f"Transaction #{i}:\n"
        content += f"Hash: {tx.get('hash', 'N/A')}\n"
        content += f"From: {tx.get('ownerAddress', 'N/A')}\n"
        content += f"To: {tx.get('toAddress', 'N/A')}\n"
        content += f"Amount: {tx.get('amount', 0)} TRX\n"
        content += f"Type: {get_transaction_type(tx)}\n"
        content += f"Status: {get_transaction_status(tx)}\n"
        content += f"Time: {time_str}\n"
        content += "-" * 50 + "\n\n"
    
    return content

def create_and_send_file(transactions):
    """ایجاد و ارسال فایل - بدون استفاده از فایل فیزیکی"""
    if not transactions:
        print("No transactions to send")
        return
    
    try:
        # ایجاد فایل در حافظه
        content = format_transaction_content(transactions)
        file_buffer = BytesIO(content.encode('utf-8'))
        file_buffer.name = f"{len(transactions)}_transactions_{datetime.now().strftime('%H%M%S')}.txt"
        
        caption = f"📊 TRON Transactions Report\n⏰ {datetime.now().strftime('%H:%M:%S')}\n📈 {len(transactions)} transactions"
        bot.send_document(CHAT_ID, file_buffer, caption=caption)
        
        print(f"✅ File sent - {len(transactions)} transactions")
        
    except Exception as e:
        print(f"❌ Error sending file: {e}")

def send_periodic_updates():
    """ارسال دوره‌ای هر 5 دقیقه"""
    while True:
        try:
            print(f"🔄 Checking transactions at {datetime.now().strftime('%H:%M:%S')}")
            
            # دریافت و فیلتر تراکنش‌ها
            all_transactions = get_latest_transactions()
            filtered_transactions = filter_transactions(all_transactions)
            
            # ارسال فایل
            if filtered_transactions:
                create_and_send_file(filtered_transactions)
            else:
                print("⚠️ No transactions with amount > 0 found")
            
        except Exception as e:
            print(f"❌ Error in periodic update: {e}")
        
        # انتظار 5 دقیقه
        time.sleep(UPDATE_INTERVAL)

@app.route('/')
def home():
    return "🤖 TRON Transaction Bot is Running!"

@app.route('/health')
def health():
    return "✅ Bot is Healthy"

# اجرای ربات
if __name__ == "__main__":
    print("🤖 TRON Transaction Bot Started")
    print(f"⏰ Update interval: {UPDATE_INTERVAL} seconds")
    print("📁 Sending only TXT files")
    print("🔍 Filter: Amount > 0 TRX")
    
    # تست اولیه
    try:
        bot.send_message(CHAT_ID, "🤖 TRON Transaction Bot Started\n⏰ Updates every 5 minutes\n📁 Only TXT files with transactions > 0 TRX")
        print("✅ Channel access confirmed!")
    except Exception as e:
        print(f"❌ Channel access error: {e}")
    
    # شروع مانیتورینگ در thread جداگانه
    monitor_thread = threading.Thread(target=send_periodic_updates)
    monitor_thread.daemon = True
    monitor_thread.start()

    print("🚀 Monitoring started...")
    
    # اجرای Flask
    app.run(host='0.0.0.0', port=PORT, debug=False)