print("🚀 SCRIPT STARTING...")

import os
print("✅ OS imported")

print("🔍 Getting environment variables...")
BOT_TOKEN = os.getenv('BOT_TOKEN')
print(f"BOT_TOKEN length: {len(BOT_TOKEN) if BOT_TOKEN else 'None'}")

ETHERSCAN_API_KEY = os.getenv('ETHERSCAN_API_KEY')
print(f"ETHERSCAN_API_KEY length: {len(ETHERSCAN_API_KEY) if ETHERSCAN_API_KEY else 'None'}")

if not BOT_TOKEN:
    print("❌ BOT_TOKEN is missing!")
    exit(1)

if not ETHERSCAN_API_KEY:
    print("❌ ETHERSCAN_API_KEY is missing!")
    exit(1)

print("✅ Both variables found!")

import requests
print("✅ Requests imported")

try:
    from telegram import Update
    from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
    print("✅ Telegram imported")
except Exception as e:
    print(f"❌ Telegram import error: {e}")
    exit(1)

print("🤖 Creating simple bot...")

try:
    application = Application.builder().token(BOT_TOKEN).build()
    print("✅ Application created")
    
    async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        print("📨 Start command received!")
        await update.message.reply_text("🤖 Bot is working!")
    
    application.add_handler(CommandHandler("start", start_command))
    print("✅ Handler added")
    
    print("🚀 Starting bot polling...")
    application.run_polling()
    
except Exception as e:
    print(f"❌ Bot creation error: {e}")
    import traceback
    traceback.print_exc()
