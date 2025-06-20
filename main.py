print("🚀 SCRIPT STARTING...")

import os
print("✅ OS imported")

import requests
print("✅ Requests imported")

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
print("✅ Telegram imported")

print("🔍 Initializing bot...")

BOT_TOKEN = os.getenv('BOT_TOKEN')
ETHERSCAN_API_KEY = os.getenv('ETHERSCAN_API_KEY')

print(f"📋 Environment check:")
print(f"- BOT_TOKEN: {'✅ Set' if BOT_TOKEN else '❌ Missing'}")
print(f"- ETHERSCAN_API_KEY: {'✅ Set' if ETHERSCAN_API_KEY else '❌ Missing'}")

if not BOT_TOKEN or not ETHERSCAN_API_KEY:
    print("❌ Missing environment variables!")
    exit(1)

class ContractAnalyzer:
    def __init__(self, etherscan_api_key):
        self.etherscan_api_key = etherscan_api_key
        print("✅ ContractAnalyzer created")
    
    def get_contract_source(self, contract_address):
        print(f"🔍 Getting contract: {contract_address}")
        try:
            params = {
                'module': 'contract',
                'action': 'getsourcecode',
                'address': contract_address,
                'apikey': self.etherscan_api_key
            }
            
            response = requests.get("https://api.etherscan.io/api", params=params, timeout=10)
            data = response.json()
            
            if data['status'] != '1' or not data['result'][0]['SourceCode']:
                print("❌ No source code")
                return None
            
            print("✅ Source code found")
            return data['result'][0]['SourceCode']
            
        except Exception as e:
            print(f"❌ Error: {e}")
            return None

class TelegramBot:
    def __init__(self, bot_token, etherscan_api_key):
        print("🤖 Creating Telegram bot...")
        self.application = Application.builder().token(bot_token).build()
        self.analyzer = ContractAnalyzer(etherscan_api_key)
        self.setup_handlers()
        print("✅ Bot created successfully")
    
    def setup_handlers(self):
        print("📝 Setting up handlers...")
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_address))
        print("✅ Handlers ready")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        print("📨 Start command received")
        await update.message.reply_text(
            "🤖 Contract Analyzer\n\n"
            "Send me a contract address (0x...)"
        )
    
    async def handle_address(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text.strip()
        print(f"📨 Address received: {text}")
        
        if len(text) == 42 and text.startswith('0x'):
            await self.analyze_contract(update, text)
        else:
            await update.message.reply_text("❌ Send valid address (0x...)")
    
    async def analyze_contract(self, update: Update, contract_address):
        print(f"🔍 Analyzing: {contract_address}")
        msg = await update.message.reply_text("🔍 Analyzing...")
        
        try:
            source_code = self.analyzer.get_contract_source(contract_address)
            
            if not source_code:
                await msg.edit_text("❌ No source code found")
                return
            
            # Simple analysis
            result = "📊 Contract Analysis\n\n"
            
            if "transferDelayEnabled" in source_code and "true" in source_code:
                result += "⏱️ Transfer delay detected\n"
            
            if "blacklistCount" in source_code:
                result += "⚫ Blacklist mechanism detected\n"
            
            if "maxBuyTxsPerBlock" in source_code:
                result += "🚫 Block limits detected\n"
            
            if result == "📊 Contract Analysis\n\n":
                result += "✅ No antibot mechanisms detected"
            
            await msg.edit_text(result)
            print("✅ Analysis sent")
            
        except Exception as e:
            print(f"❌ Analysis error: {e}")
            await msg.edit_text("❌ Analysis failed")
    
    def run(self):
        print("🚀 Starting bot polling...")
        self.application.run_polling()

print("🚀 Creating bot instance...")
try:
    bot = TelegramBot(BOT_TOKEN, ETHERSCAN_API_KEY)
    print("✅ Bot instance created - starting...")
    bot.run()
except Exception as e:
    print(f"❌ Error creating bot: {e}")
    import traceback
    traceback.print_exc()
