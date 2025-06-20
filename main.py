import os
import re
import requests
import threading
import time
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from web3 import Web3

class ContractAnalyzer:
    def __init__(self, etherscan_api_key, web3_provider_url):
        self.etherscan_api_key = etherscan_api_key
        self.w3 = Web3(Web3.HTTPProvider(web3_provider_url))
        self.etherscan_base_url = "https://api.etherscan.io/api"
    
    def get_contract_info(self, contract_address):
        """Get contract source code and basic info from Etherscan"""
        params = {
            'module': 'contract',
            'action': 'getsourcecode',
            'address': contract_address,
            'apikey': self.etherscan_api_key
        }
        
        response = requests.get(self.etherscan_base_url, params=params)
        data = response.json()
        
        if data['status'] == '1' and data['result'][0]['SourceCode']:
            contract_info = {
                'source_code': data['result'][0]['SourceCode'],
                'contract_name': data['result'][0]['ContractName']
            }
            return contract_info
        return None
    
    def analyze_antibot_mechanisms(self, source_code):
        """Analyze antibot mechanisms - RAW DATA ONLY"""
        if not source_code:
            return {}
        
        data = {
            'initial_taxes': self._extract_initial_taxes(source_code),
            'block_limits': self._extract_block_limits(source_code),
            'transfer_delays': self._extract_transfer_delays(source_code),
            'blacklist_mechanisms': self._extract_blacklist_mechanisms(source_code),
            'timing_restrictions': self._extract_timing_restrictions(source_code),
            'amount_limits': self._extract_amount_limits(source_code)
        }
        
        return {k: v for k, v in data.items() if v}
    
    def _extract_initial_taxes(self, source_code):
        """Extract initial tax data"""
        data = {}
        
        # Initial buy tax
        match = re.search(r'initialBuyTax.*?=.*?(\d+)', source_code, re.IGNORECASE)
        if match:
            data['initial_buy_tax'] = int(match.group(1))
        
        # Initial sell tax
        match = re.search(r'initialSellTax.*?=.*?(\d+)', source_code, re.IGNORECASE)
        if match:
            data['initial_sell_tax'] = int(match.group(1))
        
        # Tax reduction after X buys
        match = re.search(r'buyCount.*?>=.*?(\d+).*?(?:buyTax|buyFee).*?=.*?(\d+)', source_code, re.IGNORECASE)
        if match:
            data['tax_reduces_after_buys'] = int(match.group(1))
            data['final_buy_tax'] = int(match.group(2))
        
        # Tax reduction after X blocks
        match = re.search(r'block\.number.*?>=.*?launchBlock.*?\+.*?(\d+).*?(?:buyTax|buyFee).*?=.*?(\d+)', source_code, re.IGNORECASE)
        if match:
            data['tax_reduces_after_blocks'] = int(match.group(1))
            data['final_buy_tax_after_blocks'] = int(match.group(2))
        
        # Detect if taxes reduce to zero specifically
        if re.search(r'buyCount.*?(?:buyTax|buyFee).*?=.*?0', source_code, re.IGNORECASE):
            data['taxes_go_to_zero'] = True
        
        return data
    
    def _extract_block_limits(self, source_code):
        """Extract block-based limitations"""
        data = {}
        
        # Max transactions per block
        match = re.search(r'maxBuyTxsPerBlock.*?=.*?(\d+)', source_code, re.IGNORECASE)
        if match:
            data['max_txs_per_block'] = int(match.group(1))
        
        # Max transactions per origin per block
        match = re.search(r'maxBuyTxsPerBlockPerOrigin.*?=.*?(\d+)', source_code, re.IGNORECASE)
        if match:
            data['max_txs_per_origin_per_block'] = int(match.group(1))
        
        # Block tracking mappings
        if re.search(r'mapping.*block.*uint256', source_code, re.IGNORECASE):
            data['has_block_tracking'] = True
        
        return data
    
    def _extract_transfer_delays(self, source_code):
        """Extract transfer delay mechanisms"""
        data = {}
        
        # Transfer delay enabled
        if re.search(r'transferDelayEnabled.*?=.*?true', source_code, re.IGNORECASE):
            data['transfer_delay_enabled'] = True
        
        # Holder last transfer timestamp (1 TX per block per wallet)
        if re.search(r'holderLastTransferTimestamp', source_code, re.IGNORECASE):
            data['one_tx_per_block_per_wallet'] = True
        
        # Cooldown timer
        match = re.search(r'cooldownTimer.*?=.*?(\d+)', source_code, re.IGNORECASE)
        if match:
            data['cooldown_timer_seconds'] = int(match.group(1))
        
        return data
    
    def _extract_blacklist_mechanisms(self, source_code):
        """Extract blacklist mechanisms - SIMPLIFIED"""
        data = {}
        
        # Blacklist count (most important)
        match = re.search(r'blacklistCount.*?=.*?(\d+)', source_code, re.IGNORECASE)
        if match:
            data['first_buyers_blacklisted'] = int(match.group(1))
        
        # Current buy count tracking
        if re.search(r'currentBuyCount', source_code, re.IGNORECASE):
            data['has_buy_count_tracking'] = True
        
        return data
    
    def _extract_timing_restrictions(self, source_code):
        """Extract timing-based restrictions"""
        data = {}
        
        # Launch block
        match = re.search(r'launchBlock.*?=.*?(\d+)', source_code, re.IGNORECASE)
        if match:
            data['launch_block'] = int(match.group(1))
        
        # Protected blocks
        match = re.search(r'protectedBlocks.*?=.*?(\d+)', source_code, re.IGNORECASE)
        if match:
            data['protected_blocks'] = int(match.group(1))
        
        return data
    
    def _extract_amount_limits(self, source_code):
        """Extract amount-based limitations and convert to % of supply"""
        data = {}
        
        # Get total supply first
        total_supply = None
        supply_match = re.search(r'(?:totalSupply|initialTotalSupply).*?=.*?(\d+).*?\*.*?10\*\*.*?(\d+)', source_code, re.IGNORECASE)
        if supply_match:
            base_amount = int(supply_match.group(1))
            decimals = int(supply_match.group(2))
            total_supply = base_amount * (10 ** decimals)
        
        # Max buy amount
        max_buy_match = re.search(r'maxBuyAmount.*?=.*?(?:\(.*?)?(\d+).*?\*.*?(\d+).*?\/.*?(\d+)', source_code, re.IGNORECASE)
        if max_buy_match and total_supply:
            numerator = int(max_buy_match.group(1))
            multiplier = int(max_buy_match.group(2))
            denominator = int(max_buy_match.group(3))
            max_buy_amount = (total_supply * numerator * multiplier) // denominator
            percentage = (max_buy_amount / total_supply) * 100
            data['max_buy_percent'] = round(percentage, 2)
        
        # Max wallet
        max_wallet_match = re.search(r'maxWallet.*?=.*?(?:\(.*?)?(\d+).*?\*.*?(\d+).*?\/.*?(\d+)', source_code, re.IGNORECASE)
        if max_wallet_match and total_supply:
            numerator = int(max_wallet_match.group(1))
            multiplier = int(max_wallet_match.group(2))
            denominator = int(max_wallet_match.group(3))
            max_wallet_amount = (total_supply * numerator * multiplier) // denominator
            percentage = (max_wallet_amount / total_supply) * 100
            data['max_wallet_percent'] = round(percentage, 2)
        
        return data
    
    def _extract_honeypot_flags(self, source_code):
        """This function is removed"""
        return []

class TelegramBot:
    def __init__(self, bot_token, etherscan_api_key, web3_provider_url):
        self.application = Application.builder().token(bot_token).build()
        self.analyzer = ContractAnalyzer(etherscan_api_key, web3_provider_url)
        self.setup_handlers()
        self.start_keepalive()
    
    def start_keepalive(self):
        """Start keepalive in separate thread"""
        def keepalive_worker():
            while True:
                time.sleep(600)  # 10 minutes
                print("🏓 Keepalive ping...")
        
        # Start keepalive thread
        keepalive_thread = threading.Thread(target=keepalive_worker, daemon=True)
        keepalive_thread.start()
        print("🏓 Keepalive thread started")
    
    def setup_handlers(self):
        """Set up bot handlers"""
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_address))
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command"""
        welcome_message = """🤖 Contract Antibot Analyzer

Send me a contract address and I'll extract:
• Initial taxes data
• Block limitations  
• Transfer delays
• Blacklist mechanisms
• Timing restrictions
• Amount limits
• Honeypot flags

Just send the contract address (0x...)"""
        
        await update.message.reply_text(welcome_message)
    
    async def handle_address(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle contract address input"""
        text = update.message.text.strip()
        
        # Check if it's a valid Ethereum address
        if len(text) == 42 and text.startswith('0x'):
            await self.analyze_contract(update, text)
        else:
            await update.message.reply_text("❌ Invalid address. Send valid Ethereum address (0x...)")
    
    async def analyze_contract(self, update: Update, contract_address):
        """Analyze contract and send results"""
        processing_msg = await update.message.reply_text("🔍 Analyzing...")
        
        try:
            contract_info = self.analyzer.get_contract_info(contract_address)
            
            if not contract_info:
                await processing_msg.edit_text("❌ No source code found. Contract not verified?")
                return
            
            data = self.analyzer.analyze_antibot_mechanisms(contract_info['source_code'])
            response = self.build_response(contract_address, contract_info['contract_name'], data)
            
            await processing_msg.edit_text(response)
            
        except Exception as e:
            await processing_msg.edit_text("❌ Error analyzing contract. Please try again.")
    
    def build_response(self, contract_address, contract_name, data):
        """Build response message with raw data"""
        etherscan_link = f"https://etherscan.io/address/{contract_address}#code"
        
        response = f"📊 **Contract Analysis - {contract_name}**\n🔗 Etherscan: {etherscan_link}\n\n"
        
        if not data:
            response += "✅ No antibot mechanisms detected"
            return response
        
        # Initial Taxes
        if 'initial_taxes' in data:
            response += "💰 INITIAL TAXES:\n"
            taxes = data['initial_taxes']
            if 'initial_buy_tax' in taxes:
                response += f"• Initial buy tax: {taxes['initial_buy_tax']}%\n"
            if 'initial_sell_tax' in taxes:
                response += f"• Initial sell tax: {taxes['initial_sell_tax']}%\n"
            if 'tax_reduces_after_buys' in taxes:
                final_tax = taxes.get('final_buy_tax', 'unknown')
                response += f"• Tax reduces to {final_tax}% after {taxes['tax_reduces_after_buys']} buys\n"
            if 'tax_reduces_after_blocks' in taxes:
                final_tax = taxes.get('final_buy_tax_after_blocks', 'unknown')
                response += f"• Tax reduces to {final_tax}% after {taxes['tax_reduces_after_blocks']} blocks\n"
            if 'taxes_go_to_zero' in taxes:
                response += f"• Taxes go to 0%: {taxes['taxes_go_to_zero']}\n"
            response += "\n"
        
        # Block Limits
        if 'block_limits' in data:
            response += "🚫 BLOCK LIMITS:\n"
            limits = data['block_limits']
            if 'max_txs_per_block' in limits:
                response += f"• Max TXs per block: {limits['max_txs_per_block']}\n"
            if 'max_txs_per_origin_per_block' in limits:
                response += f"• Max wallets per block: {limits['max_txs_per_origin_per_block']}\n"
            if 'has_block_tracking' in limits:
                response += f"• Has block tracking: {limits['has_block_tracking']}\n"
            response += "\n"
        
        # Transfer Delays
        if 'transfer_delays' in data:
            response += "⏱️ TRANSFER DELAYS:\n"
            delays = data['transfer_delays']
            if 'transfer_delay_enabled' in delays:
                response += f"• Delay enabled: {delays['transfer_delay_enabled']}\n"
            if 'one_tx_per_block_per_wallet' in delays:
                response += f"• 1 TX per block per wallet: {delays['one_tx_per_block_per_wallet']}\n"
            if 'cooldown_timer_seconds' in delays:
                response += f"• Cooldown: {delays['cooldown_timer_seconds']} seconds\n"
            response += "\n"
        
        # Blacklist Mechanisms
        if 'blacklist_mechanisms' in data:
            response += "⚫ BLACKLIST:\n"
            blacklist = data['blacklist_mechanisms']
            if 'first_buyers_blacklisted' in blacklist:
                response += f"• First {blacklist['first_buyers_blacklisted']} buyers blacklisted\n"
            if 'has_buy_count_tracking' in blacklist:
                response += f"• Buy count tracking: {blacklist['has_buy_count_tracking']}\n"
            response += "\n"
        
        # Timing Restrictions
        if 'timing_restrictions' in data:
            response += "⏰ TIMING:\n"
            timing = data['timing_restrictions']
            if 'launch_block' in timing:
                response += f"• Launch block: {timing['launch_block']}\n"
            if 'protected_blocks' in timing:
                response += f"• Protected blocks: {timing['protected_blocks']}\n"
            response += "\n"
        
        # Amount Limits
        if 'amount_limits' in data:
            response += "💎 AMOUNT LIMITS:\n"
            amounts = data['amount_limits']
            if 'max_buy_percent' in amounts:
                response += f"• Max buy: {amounts['max_buy_percent']}% of supply\n"
            if 'max_wallet_percent' in amounts:
                response += f"• Max wallet: {amounts['max_wallet_percent']}% of supply\n"
            response += "\n"
        
        return response
    
    def run(self):
        """Start the bot with keepalive"""
        print("🤖 Antibot analyzer bot started...")
        print("🏓 Keepalive enabled - bot will stay online 24/7")
        self.application.run_polling()

# Main execution
if __name__ == "__main__":
    # Get environment variables
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    ETHERSCAN_API_KEY = os.getenv('ETHERSCAN_API_KEY')
    WEB3_PROVIDER_URL = os.getenv('WEB3_PROVIDER_URL')
    
    if not all([BOT_TOKEN, ETHERSCAN_API_KEY, WEB3_PROVIDER_URL]):
        print("❌ Missing environment variables!")
        print("Required: BOT_TOKEN, ETHERSCAN_API_KEY, WEB3_PROVIDER_URL")
        exit(1)
    
    bot = TelegramBot(BOT_TOKEN, ETHERSCAN_API_KEY, WEB3_PROVIDER_URL)
    bot.run()
