import os
import aiohttp
import telebot
import sqlite3
import datetime
from telebot import types
from contextlib import contextmanager
from flask import Flask
from threading import Thread
import asyncio

# Flask app for Railway
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Bot is running successfully on Railway!"

@app.route('/health')
def health():
    return "✅ Bot is healthy and running!"

# Environment variables for Railway
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8060923799:AAFIp8yO6rFKIfSRVLIiTVfPmrhaTbZpHeg")
FASTCREATE_API = "https://api.fast-creat.ir/instagram"
API_KEY = os.environ.get("API_KEY", "6780138150:qgQpHUsr2EXJlde@Api_ManagerRoBot")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "8024516184"))

BASE_DOWNLOAD_PATH = os.path.join(os.getcwd(), "downloads")
os.makedirs(BASE_DOWNLOAD_PATH, exist_ok=True)

bot = telebot.TeleBot(BOT_TOKEN)
user_lang = {}
user_states = {}
broadcast_states = {}

# کلاس مدیریت دیتابیس
class DatabaseManager:
    def __init__(self, db_name="bot_database.db"):
        self.db_name = db_name
        self.init_database()
    
    def init_database(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    language TEXT DEFAULT 'fa',
                    join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    downloads_count INTEGER DEFAULT 0,
                    last_download TIMESTAMP,
                    is_banned INTEGER DEFAULT 0,
                    ban_reason TEXT
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS statistics (
                    date TEXT PRIMARY KEY,
                    total_users INTEGER DEFAULT 0,
                    total_downloads INTEGER DEFAULT 0,
                    new_users INTEGER DEFAULT 0
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS forced_channels (
                    channel_id TEXT PRIMARY KEY,
                    channel_username TEXT,
                    channel_title TEXT
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS channel_memberships (
                    user_id INTEGER,
                    channel_id TEXT,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, channel_id)
                )
            ''')
            
            conn.commit()
    
    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_name)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def add_user(self, user_id, username, first_name, last_name):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO users (user_id, username, first_name, last_name)
                VALUES (?, ?, ?, ?)
            ''', (user_id, username, first_name, last_name))
            conn.commit()
    
    def update_user_language(self, user_id, language):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users SET language = ? WHERE user_id = ?
            ''', (language, user_id))
            conn.commit()
    
    def increment_download_count(self, user_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users SET 
                downloads_count = downloads_count + 1,
                last_download = CURRENT_TIMESTAMP
                WHERE user_id = ?
            ''', (user_id,))
            conn.commit()
    
    def get_user_stats(self, user_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            return cursor.fetchone()
    
    def get_all_users(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users ORDER BY join_date DESC')
            return cursor.fetchall()
    
    def get_total_stats(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) as total_users FROM users')
            total_users = cursor.fetchone()['total_users']
            
            cursor.execute('SELECT COUNT(*) as active_today FROM users WHERE last_download >= date("now")')
            active_today = cursor.fetchone()['active_today']
            
            cursor.execute('SELECT SUM(downloads_count) as total_downloads FROM users')
            total_downloads = cursor.fetchone()['total_downloads'] or 0
            
            return {
                'total_users': total_users,
                'active_today': active_today,
                'total_downloads': total_downloads
            }
    
    def add_forced_channel(self, channel_id, channel_username, channel_title):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO forced_channels (channel_id, channel_username, channel_title)
                VALUES (?, ?, ?)
            ''', (channel_id, channel_username, channel_title))
            conn.commit()
    
    def get_forced_channels(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM forced_channels')
            return cursor.fetchall()
    
    def verify_membership(self, user_id, channel_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO channel_memberships (user_id, channel_id)
                VALUES (?, ?)
            ''', (user_id, channel_id))
            conn.commit()
    
    def check_user_membership(self, user_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            channels = self.get_forced_channels()
            
            if not channels:
                return True
                
            for channel in channels:
                cursor.execute('''
                    SELECT 1 FROM channel_memberships 
                    WHERE user_id = ? AND channel_id = ?
                ''', (user_id, channel['channel_id']))
                if not cursor.fetchone():
                    return False
            return True

# ایجاد نمونه دیتابیس
db = DatabaseManager()

# تابع بررسی عضویت
def check_membership(user_id, chat_id=None):
    if user_id == ADMIN_ID:
        return True
    
    forced_channels = db.get_forced_channels()
    if not forced_channels:
        return True
    
    return db.check_user_membership(user_id)

# تابع ایجاد کیبورد جوین اجباری
def create_membership_keyboard():
    channels = db.get_forced_channels()
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    
    for channel in channels:
        channel_link = f"https://t.me/{channel['channel_username']}" if channel['channel_username'] else f"https://t.me/c/{channel['channel_id']}"
        keyboard.add(
            types.InlineKeyboardButton(
                f"📢 Join {channel['channel_title']}",
                url=channel_link
            )
        )
    
    keyboard.add(
        types.InlineKeyboardButton("✅ I Joined - Check Membership", callback_data="check_membership")
    )
    return keyboard

# پیام جوین اجباری
def membership_required_message(lang="fa"):
    if lang == "fa":
        return (
            "🔒 **برای استفاده از ربات، باید در کانال‌های زیر عضو شوید:**\n\n"
            "لطفاً در کانال‌های بالا عضو شوید و سپس روی دکمه '✅ عضو شدم' کلیک کنید.\n\n"
            "⚠️ توجه: پس از عضویت، حتماً روی دکمه تأیید کلیک کنید."
        )
    else:
        return (
            "🔒 **To use the bot, you must join our channels:**\n\n"
            "Please join the channels above and then click the '✅ I Joined' button.\n\n"
            "⚠️ Note: After joining, make sure to click the verification button."
        )

# منوی اصلی
def main_menu(lang="fa"):
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    if lang == "fa":
        keyboard.add(
            types.InlineKeyboardButton("📥 دانلود پست اینستاگرام", callback_data="download"),
            types.InlineKeyboardButton("💬 پشتیبانی", url="https://t.me/twexity"),
            types.InlineKeyboardButton("📘 راهنما", callback_data="help"),
            types.InlineKeyboardButton("ℹ️ درباره ما", callback_data="about"),
            types.InlineKeyboardButton("📜 قوانین", callback_data="rules")
        )
    else:
        keyboard.add(
            types.InlineKeyboardButton("📥 Download Instagram Post", callback_data="download"),
            types.InlineKeyboardButton("💬 Support", url="https://t.me/twexity"),
            types.InlineKeyboardButton("📘 Help", callback_data="help"),
            types.InlineKeyboardButton("ℹ️ About Us", callback_data="about"),
            types.InlineKeyboardButton("📜 Rules", callback_data="rules")
        )
    return keyboard

# پنل ادمین
def admin_panel(lang="en"):
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    
    if lang == "fa":
        keyboard.add(
            types.InlineKeyboardButton("📊 آمار کلی", callback_data="admin_stats"),
            types.InlineKeyboardButton("👥 مدیریت کاربران", callback_data="admin_users"),
            types.InlineKeyboardButton("📨 ارسال همگانی", callback_data="admin_broadcast"),
            types.InlineKeyboardButton("📢 مدیریت کانال‌ها", callback_data="admin_channels"),
            types.InlineKeyboardButton("🔄 به‌روزرسانی آمار", callback_data="admin_refresh"),
            types.InlineKeyboardButton("❌ بستن", callback_data="admin_close")
        )
    else:
        keyboard.add(
            types.InlineKeyboardButton("📊 Statistics", callback_data="admin_stats"),
            types.InlineKeyboardButton("👥 Users Management", callback_data="admin_users"),
            types.InlineKeyboardButton("📨 Broadcast", callback_data="admin_broadcast"),
            types.InlineKeyboardButton("📢 Channels Management", callback_data="admin_channels"),
            types.InlineKeyboardButton("🔄 Refresh Stats", callback_data="admin_refresh"),
            types.InlineKeyboardButton("❌ Close", callback_data="admin_close")
        )
    
    return keyboard

# مدیریت کاربران
def users_management_panel(page=0):
    users = db.get_all_users()
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    
    start_idx = page * 10
    end_idx = start_idx + 10
    page_users = users[start_idx:end_idx]
    
    for user in page_users:
        username = f"@{user['username']}" if user['username'] else "No Username"
        keyboard.add(
            types.InlineKeyboardButton(
                f"{user['first_name']} - {username}",
                callback_data=f"user_detail_{user['user_id']}"
            )
        )
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(types.InlineKeyboardButton("⬅️ Previous", callback_data=f"users_page_{page-1}"))
    if end_idx < len(users):
        nav_buttons.append(types.InlineKeyboardButton("Next ➡️", callback_data=f"users_page_{page+1}"))
    
    if nav_buttons:
        keyboard.row(*nav_buttons)
    
    keyboard.add(types.InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_back"))
    return keyboard

# پنل ارسال همگانی
def broadcast_panel():
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("📝 Text Broadcast", callback_data="broadcast_text"),
        types.InlineKeyboardButton("🖼 Photo Broadcast", callback_data="broadcast_photo"),
        types.InlineKeyboardButton("🎥 Video Broadcast", callback_data="broadcast_video"),
        types.InlineKeyboardButton("🔙 Back", callback_data="admin_back")
    )
    return keyboard

# هندلر استارت
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    
    db.add_user(
        user_id,
        message.from_user.username,
        message.from_user.first_name,
        message.from_user.last_name
    )
    
    if not check_membership(user_id):
        lang = user_lang.get(user_id, "fa")
        bot.send_message(
            message.chat.id,
            membership_required_message(lang),
            reply_markup=create_membership_keyboard()
        )
        return
    
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    btn_fa = types.InlineKeyboardButton("🇮🇷 فارسی", callback_data="lang_fa")
    btn_en = types.InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")
    btn_close = types.InlineKeyboardButton("❌ Close", callback_data="close")
    keyboard.add(btn_fa, btn_en, btn_close)
    
    bot.send_message(
        message.chat.id,
        "لطفاً زبان خود را انتخاب کنید:\nPlease select your language:",
        reply_markup=keyboard
    )

# هندلر ادمین
@bot.message_handler(commands=['admin'])
def admin_command(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "⛔️ You are not authorized.")
        return
    
    stats = db.get_total_stats()
    admin_text = f"""
🛠 **Admin Panel** - Statistics

👥 Total Users: {stats['total_users']}
📥 Total Downloads: {stats['total_downloads']}
🔥 Active Today: {stats['active_today']}

Select an option below:
    """
    bot.reply_to(message, admin_text, reply_markup=admin_panel())

# هندلر افزودن کانال
@bot.message_handler(commands=['addchannel'])
def add_channel_command(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    if not message.reply_to_message or not message.reply_to_message.forward_from_chat:
        bot.reply_to(message, "❌ Please forward a message from the channel you want to add.")
        return
    
    channel = message.reply_to_message.forward_from_chat
    db.add_forced_channel(
        channel_id=channel.id,
        channel_username=channel.username,
        channel_title=channel.title
    )
    
    bot.reply_to(message, f"✅ Channel '{channel.title}' added to forced channels!")

# هندلر کلیک‌ها
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = call.from_user.id
    
    if call.data == "close":
        bot.edit_message_text(
            f"❈ Closed By {call.from_user.first_name}!",
            call.message.chat.id,
            call.message.message_id
        )
        return

    if call.data == "lang_fa":
        user_lang[user_id] = "fa"
        db.update_user_language(user_id, "fa")
        bot.edit_message_text(
            "✅ زبان شما روی فارسی تنظیم شد.",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=main_menu("fa")
        )
        return

    if call.data == "lang_en":
        user_lang[user_id] = "en"
        db.update_user_language(user_id, "en")
        bot.edit_message_text(
            "✅ Your language has been set to English.",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=main_menu("en")
        )
        return

    if call.data == "check_membership":
        forced_channels = db.get_forced_channels()
        all_joined = True
        
        for channel in forced_channels:
            try:
                chat_member = bot.get_chat_member(channel['channel_id'], user_id)
                if chat_member.status in ['member', 'administrator', 'creator']:
                    db.verify_membership(user_id, channel['channel_id'])
                else:
                    all_joined = False
            except Exception as e:
                print(f"Error checking membership: {e}")
                all_joined = False
        
        if all_joined:
            lang = user_lang.get(user_id, "fa")
            if lang == "fa":
                success_msg = "✅ عضویت شما تأیید شد! اکنون می‌توانید از ربات استفاده کنید."
            else:
                success_msg = "✅ Membership verified! You can now use the bot."
            
            bot.edit_message_text(
                success_msg,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=main_menu(lang)
            )
        else:
            bot.answer_callback_query(
                call.id,
                "❌ You haven't joined all channels yet!",
                show_alert=True
            )
        return

    lang = user_lang.get(user_id, "fa")

    if call.data == "download":
        if not check_membership(user_id):
            bot.edit_message_text(
                membership_required_message(lang),
                call.message.chat.id,
                call.message.message_id,
                reply_markup=create_membership_keyboard()
            )
            return
            
        if lang == "fa":
            text = "🤖 ربات آماده است!\nلینک پست اینستاگرام خود را ارسال بنمایید:"
        else:
            text = "🤖 Bot is ready!\nPlease send your Instagram post link:"
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id
        )
        return

    if call.data == "help":
        if lang == "fa":
            text = (
                "📘 **راهنمای ربات دانلودر اینستاگرام:**\n\n"
                "۱. ابتدا وارد اینستاگرام شوید و روی پست، استوری یا ریل مورد نظر بزنید.\n"
                "۲. گزینه Copy Link را انتخاب کنید.\n"
                "۳. لینک را برای ربات ارسال کنید.\n"
                "۴. چند ثانیه صبر کنید تا فایل دانلود و برای شما ارسال شود.\n\n"
                "⚙️ نکته: اگر پست خصوصی است، ربات قادر به دانلود نخواهد بود.\n"
                "🧩 برای هرگونه سوال از بخش پشتیبانی استفاده کنید."
            )
        else:
            text = (
                "📘 **Instagram Downloader Bot Guide:**\n\n"
                "1. Open Instagram and copy the link of the post, reel, or story.\n"
                "2. Send the copied link to the bot.\n"
                "3. Wait a few seconds for processing.\n"
                "4. The video or image will be sent automatically.\n\n"
                "⚙️ Note: Private posts cannot be downloaded.\n"
                "🧩 For any issues, contact support."
            )
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=main_menu(lang)
        )
        return

    if call.data == "about":
        text = "🤖 This bot is developed by @twexity\nDesigned to download Instagram media quickly and safely."
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=main_menu(lang)
        )
        return

    if call.data == "rules":
        if lang == "fa":
            text = (
                "📜 **قوانین استفاده از ربات:**\n\n"
                "1. از ربات برای اهداف غیرقانونی استفاده نکنید.\n"
                "2. هرگونه سوءاستفاده منجر به مسدودسازی خواهد شد.\n"
                "3. با استفاده از ربات، قوانین تلگرام و اینستاگرام را می‌پذیرید."
            )
        else:
            text = (
                "📜 **Bot Usage Rules:**\n\n"
                "1. Do not use this bot for illegal purposes.\n"
                "2. Misuse will result in a permanent ban.\n"
                "3. By using the bot, you agree to Telegram and Instagram terms."
            )
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=main_menu(lang)
        )
        return

    # هندلرهای ادمین
    if call.data.startswith("admin"):
        if user_id != ADMIN_ID:
            bot.answer_callback_query(call.id, "⛔️ Access denied!")
            return
        
        if call.data == "admin_stats":
            stats = db.get_total_stats()
            stats_text = f"""
📊 **Detailed Statistics**

👥 Users:
• Total: {stats['total_users']}
• Active Today: {stats['active_today']}

📥 Downloads:
• Total: {stats['total_downloads']}
• Average per User: {stats['total_downloads']/stats['total_users']:.1f if stats['total_users'] > 0 else 0}

🕒 Last Update: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            """
            bot.edit_message_text(
                stats_text,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=admin_panel()
            )
            return
        
        elif call.data == "admin_users":
            users = db.get_all_users()
            users_text = f"👥 **Users Management**\nTotal Users: {len(users)}\n\nSelect a user to manage:"
            bot.edit_message_text(
                users_text,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=users_management_panel()
            )
            return
        
        elif call.data == "admin_broadcast":
            bot.edit_message_text(
                "📨 **Broadcast Message**\nSelect message type:",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=broadcast_panel()
            )
            return
        
        elif call.data == "admin_channels":
            channels = db.get_forced_channels()
            channels_text = "📢 **Forced Channels Management**\n\n"
            
            if channels:
                for i, channel in enumerate(channels, 1):
                    channels_text += f"{i}. {channel['channel_title']} (@{channel['channel_username']})\n"
            else:
                channels_text += "No channels set.\n"
            
            channels_text += "\nUse /addchannel to add a new channel."
            
            bot.edit_message_text(
                channels_text,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=admin_panel()
            )
            return
        
        elif call.data == "admin_refresh":
            bot.answer_callback_query(call.id, "🔄 Statistics refreshed!")
            admin_command(call.message)
            return
        
        elif call.data == "admin_back":
            stats = db.get_total_stats()
            admin_text = f"""
🛠 **Admin Panel** - Statistics

👥 Total Users: {stats['total_users']}
📥 Total Downloads: {stats['total_downloads']}
🔥 Active Today: {stats['active_today']}

Select an option below:
            """
            bot.edit_message_text(
                admin_text,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=admin_panel()
            )
            return
        
        elif call.data == "admin_close":
            bot.delete_message(call.message.chat.id, call.message.message_id)
            return

    # هندلر صفحه‌بندی کاربران
    if call.data.startswith("users_page_"):
        page = int(call.data.split("_")[2])
        users = db.get_all_users()
        users_text = f"👥 **Users Management**\nTotal Users: {len(users)}\n\nSelect a user to manage:"
        bot.edit_message_text(
            users_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=users_management_panel(page)
        )
        return

    # هندلر جزئیات کاربر
    if call.data.startswith("user_detail_"):
        user_id = int(call.data.split("_")[2])
        user = db.get_user_stats(user_id)
        
        if user:
            user_text = f"""
👤 **User Details**

🆔 ID: `{user['user_id']}`
👤 Name: {user['first_name']} {user['last_name'] or ''}
📛 Username: @{user['username'] or 'No username'}
🌐 Language: {user['language']}
📥 Downloads: {user['downloads_count']}
📅 Joined: {user['join_date']}
🕒 Last Active: {user['last_download'] or 'Never'}
            """
            bot.answer_callback_query(call.id, "User details loaded!")
            bot.edit_message_text(
                user_text,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=users_management_panel()
            )
        return

    # هندلرهای ارسال همگانی
    if call.data.startswith("broadcast_"):
        if user_id != ADMIN_ID:
            bot.answer_callback_query(call.id, "⛔️ Access denied!")
            return
        
        broadcast_type = call.data.replace("broadcast_", "")
        user_states[user_id] = f"broadcast_{broadcast_type}"
        
        if broadcast_type == "text":
            bot.edit_message_text(
                "📝 **Text Broadcast**\n\nPlease send the text message you want to broadcast:",
                call.message.chat.id,
                call.message.message_id
            )
        elif broadcast_type == "photo":
            bot.edit_message_text(
                "🖼 **Photo Broadcast**\n\nPlease send the photo with caption you want to broadcast:",
                call.message.chat.id,
                call.message.message_id
            )
        elif broadcast_type == "video":
            bot.edit_message_text(
                "🎥 **Video Broadcast**\n\nPlease send the video with caption you want to broadcast:",
                call.message.chat.id,
                call.message.message_id
            )
        return

# هندلر پیام‌ها
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.from_user.id
    
    if not check_membership(user_id):
        lang = user_lang.get(user_id, "fa")
        bot.reply_to(
            message,
            membership_required_message(lang),
            reply_markup=create_membership_keyboard()
        )
        return

    # هندلر ارسال همگانی
    if user_id == ADMIN_ID and user_id in user_states and user_states[user_id].startswith("broadcast_"):
        broadcast_type = user_states[user_id].replace("broadcast_", "")
        users = db.get_all_users()
        
        bot.reply_to(message, f"🚀 Starting broadcast to {len(users)} users...")
        
        success = 0
        failed = 0
        
        for user in users:
            try:
                if broadcast_type == "text":
                    bot.send_message(user['user_id'], message.text)
                elif broadcast_type == "photo" and message.photo:
                    bot.send_photo(user['user_id'], message.photo[-1].file_id, caption=message.caption)
                elif broadcast_type == "video" and message.video:
                    bot.send_video(user['user_id'], message.video.file_id, caption=message.caption)
                
                success += 1
            except Exception as e:
                failed += 1
                print(f"Failed to send to {user['user_id']}: {e}")
        
        del user_states[user_id]
        bot.reply_to(message, f"✅ Broadcast completed!\nSuccess: {success}\nFailed: {failed}")
        return

    url = message.text.strip() if message.text else None

    if not url or not url.startswith("http") or "instagram.com" not in url:
        bot.reply_to(message, "❌ Please send a valid Instagram link.")
        return

    bot.reply_to(message, "⏳ Downloading content, please wait...")
    db.increment_download_count(user_id)

    # استفاده از asyncio برای اجرای تابع دانلود
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(download_instagram_content(message.chat.id, url))
    loop.close()

# تابع دانلود اینستاگرام
async def download_instagram_content(chat_id, url):
    params = {"apikey": API_KEY, "type": "post", "url": url}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(FASTCREATE_API, params=params) as resp:
                data = await resp.json()

        if data.get("ok") and data["result"].get("result"):
            first_item = data["result"]["result"][0]
            caption = first_item.get("caption", "") + "\n\n This Bot has Open Source"

            if first_item.get("is_video") and first_item.get("video_url"):
                bot.send_video(chat_id, video=first_item["video_url"], caption=caption)
            elif first_item.get("display_url"):
                bot.send_photo(chat_id, photo=first_item["display_url"], caption=caption)
            else:
                bot.send_message(chat_id, "❌ No downloadable content found for this link.")
        else:
            bot.send_message(chat_id, "⛔️ Error fetching content. Please try again.")
    except Exception as e:
        bot.send_message(chat_id, f"❌ Error: {str(e)}")

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    # Run Flask in a separate thread
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    print("🤖 Bot is running with advanced features!")
    print("📊 Database initialized!")
    print("🔒 Membership system activated!")
    print("🚀 Deployed on Railway!")
    
    try:
        bot.infinity_polling()
    except Exception as e:
        print(f"Bot error: {e}")