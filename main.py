import os
import re
import requests
import threading
import time
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

class ContractAnalyzer:
    def __init__(self, etherscan_api_key):
        self.etherscan_api_key = etherscan_api_key
        self.etherscan_base_url = "https://api.etherscan.io/api"
    
    def get_contract_source(self, contract_address):
        """Get contract source code from Etherscan"""
        try:
            params = {
                'module': 'contract',
                'action': 'getsourcecode',
                'address': contract_address,
                'apikey': self.etherscan_api_key
            }
            
            print(f"🔍 Fetching contract: {contract_address}")
            response = requests.get(self.etherscan_base_url, params=params, timeout=10)
            data = response.json()
            
            if data['status'] != '1' or not data['result'][0]['SourceCode']:
                print("❌ No source code found")
                return None
            
            print("✅ Source code retrieved")
            return data['result'][0]['SourceCode']
            
        except Exception as e:
            print(f"❌ Error: {e}")
            return None
    
    def analyze_antibot_mechanisms(self, source_code):
        """Analyze antibot mechanisms from source code"""
        if not source_code:
            return {}
        
        print("🔍 Analyzing mechanisms...")
        data = {
            'initial_taxes': self._extract_initial_taxes(source_code),
            'block_limits': self._extract_block_limits(source_code),
            'transfer_delays': self._extract_transfer_delays(source_code),
            'blacklist_mechanisms': self._extract_blacklist_mechanisms(source_code),
            'timing_restrictions': self._extract_timing_restrictions(source_code),
            'amount_limits': self._extract_amount_limits(source_code)
        }
        
        result = {k: v for k, v in data.items() if v}
        print(f"✅ Analysis complete - {len(result)} mechanisms found")
        return result
    
    def _extract_initial_taxes(self, source_code):
        """Extract initial tax data"""
        data = {}
        
        match = re.search(r'initialBuyTax.*?=.*?(\d+)', source_code, re.IGNORECASE)
        if match:
            data['initial_buy_tax'] = int(match.group(1))
        
        match = re.search(r'initialSellTax.*?=.*?(\d+)', source_code, re.IGNORECASE)
        if match:
            data['initial_sell_tax'] = int(match.group(1))
        
        match = re.search(r'buyCount.*?>=.*?(\d+).*?(?:buyTax|buyFee).*?=.*?(\d+)', source_code, re.IGNORECASE)
        if match:
            data['tax_reduces_after_buys'] = int(match.group(1))
            data['final_buy_tax'] = int(match.group(2))
        
        if re.search(r'buyCount.*?(?:buyTax|buyFee).*?=.*?0', source_code, re.IGNORECASE):
            data['taxes_go_to_zero'] = True
        
        return data
    
    def _extract_block_limits(self, source_code):
        """Extract block-based limitations"""
        data = {}
        
        match = re.search(r'maxBuyTxsPerBlock.*?=.*?(\d+)', source_code, re.IGNORECASE)
        if match:
            data['max_txs_per_block'] = int(match.group(1))
        
        match = re.search(r'maxBuyTxsPerBlockPerOrigin.*?=.*?(\d+)', source_code, re.IGNORECASE)
        if match:
            data['max_txs_per_origin_per_block'] = int(match.group(1))
        
        if re.search(r'mapping.*block.*uint256', source_code, re.IGNORECASE):
            data['has_block_tracking'] = True
        
        return data
    
    def _extract_transfer_delays(self, source_code):
        """Extract transfer delay mechanisms"""
        data = {}
        
        if re.search(r'transferDelayEnabled.*?=.*?true', source_code, re.IGNORECASE):
            data['transfer_delay_enabled'] = True
        
        if re.search(r'holderLastTransferTimestamp', source_code, re.IGNORECASE):
            data['one_tx_per_block_per_wallet'] = True
        
        match = re.search(r'cooldownTimer.*?=.*?(\d+)', source_code, re.IGNORECASE)
        if match:
            data['cooldown_timer_seconds'] = int(match.group(1))
        
        return data
    
    def _extract_blacklist_mechanisms(self, source_code):
        """Extract blacklist mechanisms"""
        data = {}
        
        match = re.search(r'blacklistCount.*?=.*?(\d+)', source_code, re.IGNORECASE)
        if match:
            data['first_buyers_blacklisted'] = int(match.group(1))
        
        if re.search(r'currentBuyCount', source_code, re.IGNORECASE):
            data['has_buy_count_tracking'] = True
        
        return data
    
    def _extract_timing_restrictions(self, source_code):
        """Extract timing-based restrictions"""
        data = {}
        
        match = re.search(r'protectedBlocks.*?=.*?(\d+)', source_code, re.IGNORECASE)
        if match:
            data['protected_blocks'] = int(match.group(1))
        
        return data
    
    def _extract_amount_limits(self, source_code):
        """Extract amount limitations as percentages"""
        data = {}
        
        # Simple percentage detection
        max_buy_match = re.search(r'maxBuyAmount.*?(\d+).*?\/.*?(\d+)', source_code, re.IGNORECASE)
        if max_buy_match:
            numerator = int(max_buy_match.group(1))
            denominator = int(max_buy_match.group(2))
            percentage = (numerator / denominator) * 100
            data['max_buy_percent'] = round(percentage, 2)
        
        max_wallet_match = re.search(r'maxWallet.*?(\d+).*?\/.*?(\d+)', source_code, re.IGNORECASE)
        if max_wallet_match:
            numerator = int(max_wallet_match.group(1))
            denominator = int(max_wallet_match.group(2))
            percentage = (numerator / denominator) * 100
            data['max_wallet_percent'] = round(percentage, 2)
        
        return data

class TelegramBot:
    def __init__(self, bot_token, etherscan_api_key):
        self.application = Application.builder().token(bot_token).build()
        self.analyzer = ContractAnalyzer(etherscan_api_key)
        self.setup_handlers()
        self.start_keepalive()
    
    def start_keepalive(self):
        """Keep bot alive"""
        def keepalive():
            while True:
                time.sleep(600)
                print("🏓 Keepalive")
        
        threading.Thread(target=keepalive, daemon=True).start()
    
    def setup_handlers(self):
        """Setup bot handlers"""
        print("📝 Setting up handlers...")
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_address))
        print("✅ Handlers ready")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command"""
        await update.message.reply_text(
            "🤖 Contract Antibot Analyzer\n\n"
            "Send me a contract address (0x...) and I'll analyze:\n"
            "• Initial taxes\n"
            "• Block limitations\n"
            "• Transfer delays\n"
            "• Blacklist mechanisms\n"
            "• Amount limits"
        )
    
    async def handle_address(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle contract address"""
        text = update.message.text.strip()
        
        if len(text) == 42 and text.startswith('0x'):
            await self.analyze_contract(update, text)
        else:
            await update.message.reply_text("❌ Send valid address (0x...)")
    
    async def analyze_contract(self, update: Update, contract_address):
        """Analyze contract"""
        msg = await update.message.reply_text("🔍 Analyzing...")
        
        try:
            print(f"📋 Starting analysis for {contract_address}")
            
            source_code = self.analyzer.get_contract_source(contract_address)
            if not source_code:
                await msg.edit_text("❌ No source code found")
                return
            
            data = self.analyzer.analyze_antibot_mechanisms(source_code)
            response = self.build_response(contract_address, data)
            
            await msg.edit_text(response)
            print("✅ Analysis sent to user")
            
        except Exception as e:
            print(f"❌ Analysis error: {e}")
            await msg.edit_text("❌ Analysis failed. Try again.")
    
    def build_response(self, contract_address, data):
        """Build response message"""
        etherscan_link = f"https://etherscan.io/address/{contract_address}#code"
        response = f"📊 Contract Analysis\n🔗 Etherscan: {etherscan_link}\n\n"
        
        if not data:
            response += "✅ No antibot mechanisms detected"
            return response
        
        if 'initial_taxes' in data:
            response += "💰 INITIAL TAXES:\n"
            taxes = data['initial_taxes']
            for key, value in taxes.items():
                if key == 'initial_buy_tax':
                    response += f"• Initial buy tax: {value}%\n"
                elif key == 'initial_sell_tax':
                    response += f"• Initial sell tax: {value}%\n"
                elif key == 'tax_reduces_after_buys':
                    final = taxes.get('final_buy_tax', '?')
                    response += f"• Reduces to {final}% after {value} buys\n"
                elif key == 'taxes_go_to_zero':
                    response += f"• Taxes go to 0%: {value}\n"
            response += "\n"
        
        if 'block_limits' in data:
            response += "🚫 BLOCK LIMITS:\n"
            limits = data['block_limits']
            for key, value in limits.items():
                if key == 'max_txs_per_block':
                    response += f"• Max TXs per block: {value}\n"
                elif key == 'max_txs_per_origin_per_block':
                    response += f"• Max wallets per block: {value}\n"
                elif key == 'has_block_tracking':
                    response += f"• Has block tracking: {value}\n"
            response += "\n"
        
        if 'transfer_delays' in data:
            response += "⏱️ TRANSFER DELAYS:\n"
            delays = data['transfer_delays']
            for key, value in delays.items():
                if key == 'transfer_delay_enabled':
                    response += f"• Delay enabled: {value}\n"
                elif key == 'one_tx_per_block_per_wallet':
                    response += f"• 1 TX per block per wallet: {value}\n"
                elif key == 'cooldown_timer_seconds':
                    response += f"• Cooldown: {value} seconds\n"
            response += "\n"
        
        if 'blacklist_mechanisms' in data:
            response += "⚫ BLACKLIST:\n"
            blacklist = data['blacklist_mechanisms']
            for key, value in blacklist.items():
                if key == 'first_buyers_blacklisted':
                    response += f"• First {value} buyers blacklisted\n"
                elif key == 'has_buy_count_tracking':
                    response += f"• Buy count tracking: {value}\n"
            response += "\n"
        
        if 'timing_restrictions' in data:
            response += "⏰ TIMING:\n"
            timing = data['timing_restrictions']
            for key, value in timing.items():
                if key == 'protected_blocks':
                    response += f"• Protected blocks: {value}\n"
            response += "\n"
        
        if 'amount_limits' in data:
            response += "💎 AMOUNT LIMITS:\n"
            amounts = data['amount_limits']
            for key, value in amounts.items():
                if key == 'max_buy_percent':
                    response += f"• Max buy: {value}% of supply\n"
                elif key == 'max_wallet_percent':
                    response += f"• Max wallet: {value}% of supply\n"
            response += "\n"
        
        return response
    
    def run(self):
        """Start bot"""
        print("🤖 Bot starting...")
        self.application.run_polling()

if __name__ == "__main__":
    print("🔍 Initializing...")
    
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    ETHERSCAN_API_KEY = os.getenv('ETHERSCAN_API_KEY')
    
    print(f"📋 Environment:")
    print(f"- BOT_TOKEN: {'✅' if BOT_TOKEN else '❌'}")
    print(f"- ETHERSCAN_API_KEY: {'✅' if ETHERSCAN_API_KEY else '❌'}")
    
    if not all([BOT_TOKEN, ETHERSCAN_API_KEY]):
        print("❌ Missing variables!")
        exit(1)
    
    try:
        bot = TelegramBot(BOT_TOKEN, ETHERSCAN_API_KEY)
        bot.run()
    except Exception as e:
        print(f"❌ Error: {e}")
