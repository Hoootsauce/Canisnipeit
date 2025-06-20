print("🚀 SCRIPT STARTING...")

import os
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.getenv('BOT_TOKEN')
ETHERSCAN_API_KEY = os.getenv('ETHERSCAN_API_KEY')

print("✅ Environment variables loaded")

class ContractAnalyzer:
    def __init__(self, etherscan_api_key):
        self.etherscan_api_key = etherscan_api_key
    
    def get_contract_source(self, contract_address):
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
                return None
            
            return data['result'][0]['SourceCode']
            
        except Exception as e:
            print(f"❌ Etherscan error: {e}")
            return None

application = Application.builder().token(BOT_TOKEN).build()
analyzer = ContractAnalyzer(ETHERSCAN_API_KEY)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Contract Antibot Analyzer\n\n"
        "Send me a contract address (0x...)"
    )

async def handle_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    if len(text) == 42 and text.startswith('0x'):
        msg = await update.message.reply_text("🔍 Analyzing...")
        
        try:
            source_code = analyzer.get_contract_source(text)
            
            if not source_code:
                await msg.edit_text("❌ No source code found")
                return
            
            # Analyze antibot mechanisms
            result = f"📊 Contract Analysis\n🔗 https://etherscan.io/address/{text}#code\n\n"
            
            mechanisms_found = False
            
            # Transfer delays
            if "transferDelayEnabled" in source_code and "true" in source_code:
                result += "⏱️ TRANSFER DELAYS:\n• Transfer delay enabled: true\n"
                if "holderLastTransferTimestamp" in source_code:
                    result += "• 1 TX per block per wallet: true\n"
                result += "\n"
                mechanisms_found = True
            
            # Block limits
            if "maxBuyTxsPerBlock" in source_code:
                result += "🚫 BLOCK LIMITS:\n"
                import re
                match = re.search(r'maxBuyTxsPerBlock.*?=.*?(\d+)', source_code)
                if match:
                    result += f"• Max TXs per block: {match.group(1)}\n"
                
                match = re.search(r'maxBuyTxsPerBlockPerOrigin.*?=.*?(\d+)', source_code)
                if match:
                    result += f"• Max wallets per block: {match.group(1)}\n"
                
                result += "\n"
                mechanisms_found = True
            
            # Blacklist mechanisms
            if "blacklistCount" in source_code:
                result += "⚫ BLACKLIST:\n"
                import re
                match = re.search(r'blacklistCount.*?=.*?(\d+)', source_code)
                if match:
                    result += f"• First {match.group(1)} buyers blacklisted\n"
                
                if "currentBuyCount" in source_code:
                    result += "• Buy count tracking: true\n"
                
                result += "\n"
                mechanisms_found = True
            
            # Initial taxes
            if "initialBuyTax" in source_code or "initialSellTax" in source_code:
                result += "💰 INITIAL TAXES:\n"
                import re
                
                match = re.search(r'initialBuyTax.*?=.*?(\d+)', source_code)
                if match:
                    result += f"• Initial buy tax: {match.group(1)}%\n"
                
                match = re.search(r'initialSellTax.*?=.*?(\d+)', source_code)
                if match:
                    result += f"• Initial sell tax: {match.group(1)}%\n"
                
                result += "\n"
                mechanisms_found = True
            
            if not mechanisms_found:
                result += "✅ No antibot mechanisms detected"
            
            await msg.edit_text(result)
            print(f"✅ Analysis completed for {text}")
            
        except Exception as e:
            print(f"❌ Analysis error: {e}")
            await msg.edit_text("❌ Analysis failed. Try again.")
    else:
        await update.message.reply_text("❌ Send valid address (0x...)")

application.add_handler(CommandHandler("start", start_command))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_address))

print("🚀 Starting bot...")
application.run_polling()
