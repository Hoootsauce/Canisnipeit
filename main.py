import os
import re
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from web3 import Web3

class ContractAnalyzer:
    def __init__(self, etherscan_api_key, web3_provider_url):
        self.etherscan_api_key = etherscan_api_key
        self.w3 = Web3(Web3.HTTPProvider(web3_provider_url))
        self.etherscan_base_url = "https://api.etherscan.io/api"
    
    def get_contract_source(self, contract_address):
        """Get contract source code from Etherscan"""
        params = {
            'module': 'contract',
            'action': 'getsourcecode',
            'address': contract_address,
            'apikey': self.etherscan_api_key
        }
        
        response = requests.get(self.etherscan_base_url, params=params)
        data = response.json()
        
        if data['status'] == '1' and data['result'][0]['SourceCode']:
            return data['result'][0]['SourceCode']
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
            'amount_limits': self._extract_amount_limits(source_code),
            'honeypot_flags': self._extract_honeypot_flags(source_code)
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
        
        # Tax countdown/reduction trigger
        match = re.search(r'buyCount.*?(\d+)', source_code, re.IGNORECASE)
        if match:
            data['tax_reduction_at'] = int(match.group(1))
        
        # Detect if taxes reduce to zero
        if re.search(r'buyCount.*?buyTax.*?=.*?0', source_code, re.IGNORECASE):
            data['taxes_reduce_to_zero'] = True
        
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
        
        # Holder last transfer timestamp
        if re.search(r'holderLastTransferTimestamp', source_code, re.IGNORECASE):
            data['has_timestamp_tracking'] = True
        
        # Cooldown timer
        match = re.search(r'cooldownTimer.*?=.*?(\d+)', source_code, re.IGNORECASE)
        if match:
            data['cooldown_timer'] = int(match.group(1))
        
        return data
    
    def _extract_blacklist_mechanisms(self, source_code):
        """Extract blacklist mechanisms"""
        data = {}
        
        # Blacklist count
        match = re.search(r'blacklistCount.*?=.*?(\d+)', source_code, re.IGNORECASE)
        if match:
            data['blacklist_count'] = int(match.group(1))
        
        # Current buy count tracking
        if re.search(r'currentBuyCount', source_code, re.IGNORECASE):
            data['has_buy_count_tracking'] = True
        
        # Amount-based blacklist threshold
        match = re.search(r'amount.*?>.*?(\d+)', source_code, re.IGNORECASE)
        if match:
            data['amount_blacklist_threshold'] = match.group(1)
        
        # Smart blacklist logic detection
        if re.search(r'currentBuyCount.*?blacklistCount.*?bots', source_code, re.IGNORECASE):
            data['has_smart_blacklist_logic'] = True
        
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
        """Extract amount-based limitations"""
        data = {}
        
        # Max buy amount
        match = re.search(r'maxBuyAmount.*?=.*?([^;]+)', source_code, re.IGNORECASE)
        if match:
            data['max_buy_amount'] = match.group(1).strip()
        
        # Max wallet
        match = re.search(r'maxWallet.*?=.*?([^;]+)', source_code, re.IGNORECASE)
        if match:
            data['max_wallet'] = match.group(1).strip()
        
        return data
    
    def _extract_honeypot_flags(self, source_code):
        """Extract potential honeypot indicators"""
        flags = []
        
        if re.search(r'onlyOwner.*transfer', source_code, re.IGNORECASE):
            flags.append("owner_can_control_transfers")
        
        if re.search(r'function.*pause', source_code, re.IGNORECASE):
            flags.append("has_pause_function")
        
        if re.search(r'setFee', source_code, re.IGNORECASE):
            flags.append("can_modify_fees")
        
        return flags

class TelegramBot:
    def __init__(self, bot_token, etherscan_api_key, web3_provider_url):
        self.application = Application.builder().token(bot_token).build()
        self.analyzer = ContractAnalyzer(etherscan_api_key, web3_provider_url)
        self.setup_handlers()
    
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
            source_code = self.analyzer.get_contract_source(contract_address)
            
            if not source_code:
                await processing_msg.edit_text("❌ No source code found. Contract not verified?")
                return
            
            data = self.analyzer.analyze_antibot_mechanisms(source_code)
            response = self.build_response(contract_address, data)
            
            await processing_msg.edit_text(response)
            
        except Exception as e:
            await processing_msg.edit_text("❌ Error analyzing contract. Please try again.")
    
    def build_response(self, contract_address, data):
        """Build response message with raw data"""
        etherscan_link = f"https://etherscan.io/address/{contract_address}#code"
        
        response = f"📊 Contract Analysis\n🔗 Etherscan: {etherscan_link}\n\n"
        
        if not data:
            response += "✅ No antibot mechanisms detected"
            return response
        
        # Initial Taxes
        if 'initial_taxes' in data:
            response += "💰 INITIAL TAXES:\n"
            taxes = data['initial_taxes']
            if 'initial_buy_tax' in taxes:
                response += f"• Buy tax: {taxes['initial_buy_tax']}%\n"
            if 'initial_sell_tax' in taxes:
                response += f"• Sell tax: {taxes['initial_sell_tax']}%\n"
            if 'tax_reduction_at' in taxes:
                response += f"• Reduces at: {taxes['tax_reduction_at']} buys\n"
            if 'taxes_reduce_to_zero' in taxes:
                response += f"• Reduces to zero: {taxes['taxes_reduce_to_zero']}\n"
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
            if 'has_timestamp_tracking' in delays:
                response += f"• Timestamp tracking: {delays['has_timestamp_tracking']}\n"
            if 'cooldown_timer' in delays:
                response += f"• Cooldown timer: {delays['cooldown_timer']}\n"
            response += "\n"
        
        # Blacklist Mechanisms
        if 'blacklist_mechanisms' in data:
            response += "⚫ BLACKLIST:\n"
            blacklist = data['blacklist_mechanisms']
            if 'blacklist_count' in blacklist:
                response += f"• Blacklist count: {blacklist['blacklist_count']}\n"
            if 'has_buy_count_tracking' in blacklist:
                response += f"• Buy count tracking: {blacklist['has_buy_count_tracking']}\n"
            if 'amount_blacklist_threshold' in blacklist:
                response += f"• Amount threshold: {blacklist['amount_blacklist_threshold']}\n"
            if 'has_smart_blacklist_logic' in blacklist:
                response += f"• Smart logic: {blacklist['has_smart_blacklist_logic']}\n"
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
            if 'max_buy_amount' in amounts:
                response += f"• Max buy: {amounts['max_buy_amount']}\n"
            if 'max_wallet' in amounts:
                response += f"• Max wallet: {amounts['max_wallet']}\n"
            response += "\n"
        
        # Honeypot Flags
        if 'honeypot_flags' in data and data['honeypot_flags']:
            response += "🚨 HONEYPOT FLAGS:\n"
            for flag in data['honeypot_flags']:
                response += f"• {flag}\n"
        
        return response
    
    def run(self):
        """Start the bot"""
        print("🤖 Antibot analyzer bot started...")
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
