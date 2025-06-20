print("🚀 SCRIPT STARTING...")

import os
import requests
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.getenv('BOT_TOKEN')
ETHERSCAN_API_KEY = os.getenv('ETHERSCAN_API_KEY')

print("✅ Environment variables loaded")

# Serveur de santé pour Render
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/restart':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write('Restarting bot...'.encode('utf-8'))
            # Force restart
            os._exit(0)
        else:
            self.send_response(200)
            self.send_header('Content-type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write('Contract Analyzer Bot is running!'.encode('utf-8'))
    
    def log_message(self, format, *args):
        # Désactive les logs HTTP pour éviter le spam
        pass

def start_health_server():
    port = int(os.getenv('PORT', 8000))
    server = HTTPServer(('0.0.0.0', port), HealthHandler)
    print(f"🌐 Health server starting on port {port}...")
    server.serve_forever()

# Keep-alive automatique
def keep_alive():
    """Ping le serveur toutes les 10 minutes pour éviter la mise en veille"""
    hostname = os.getenv('RENDER_EXTERNAL_HOSTNAME')
    if not hostname:
        print("⚠️ RENDER_EXTERNAL_HOSTNAME not found, keep-alive disabled")
        return
    
    url = f"https://{hostname}"
    
    while True:
        try:
            time.sleep(600)  # 10 minutes
            response = requests.get(url, timeout=30)
            print(f"🏓 Keep-alive ping to {url}")
            print(f"✅ Keep-alive successful: {response.status_code}")
        except Exception as e:
            print(f"⚠️ Keep-alive failed: {e}")

def start_keep_alive():
    """Démarre le keep-alive dans un thread séparé"""
    import time
    keep_alive()

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
            
            # Max buy limits - détection étendue
            max_buy_found = False
            max_buy_keywords = [
                "maxBuyAmount", "_maxBuyAmount", "maxTransactionAmount", 
                "maxTxAmount", "_maxTxAmount", "maxBuy", "_maxBuy",
                "maxPurchase", "_maxPurchase", "buyLimit", "_buyLimit",
                "transactionLimit", "_transactionLimit", "maxToken",
                "_maxTokensPerTransaction", "maxTokensPerTx"
            ]
            
            # Vérifier si des mots-clés de max buy existent
            has_maxbuy_keywords = any(keyword in source_code for keyword in max_buy_keywords)
            
            if has_maxbuy_keywords:
                result += "💰 MAX BUY LIMITS:\n"
                import re
                
                # Patterns étendus pour capturer plus de variantes
                patterns = [
                    r'maxBuyAmount\s*=\s*(\d+)',
                    r'_maxBuyAmount\s*=\s*(\d+)', 
                    r'maxTransactionAmount\s*=\s*(\d+)',
                    r'maxTxAmount\s*=\s*(\d+)',
                    r'_maxTxAmount\s*=\s*(\d+)',
                    r'maxBuy\s*=\s*(\d+)',
                    r'_maxBuy\s*=\s*(\d+)',
                    r'maxPurchase\s*=\s*(\d+)',
                    r'buyLimit\s*=\s*(\d+)',
                    r'transactionLimit\s*=\s*(\d+)',
                    r'maxToken\s*=\s*(\d+)',
                    r'_maxTokensPerTransaction\s*=\s*(\d+)',
                    # Patterns avec opérations mathématiques
                    r'maxBuyAmount\s*=.*?(\d+)\s*\*\s*10\*\*(\d+)',
                    r'_maxBuyAmount\s*=.*?(\d+)\s*\*\s*10\*\*(\d+)',
                    # Patterns avec pourcentages dans le code
                    r'maxBuy.*?(\d+)\s*%',
                    r'maxTransaction.*?(\d+)\s*%',
                    r'(\d+)\s*%.*?maxBuy'
                ]
                
                for pattern in patterns:
                    matches = re.findall(pattern, source_code, re.IGNORECASE)
                    if matches:
                        if len(matches[0]) == 2:  # Pattern avec 10**decimals
                            base_value = int(matches[0][0])
                            decimals = int(matches[0][1])
                            max_buy_value = base_value * (10 ** decimals)
                        else:
                            max_buy_value = int(matches[0])
                        
                        # Essayer de trouver le total supply pour calculer le %
                        total_supply_patterns = [
                            r'_totalSupply\s*=\s*(\d+)',
                            r'totalSupply\s*=\s*(\d+)',
                            r'_tTotal\s*=\s*(\d+)',
                            r'tTotal\s*=\s*(\d+)',
                            # Avec opérations mathématiques
                            r'_totalSupply\s*=.*?(\d+)\s*\*\s*10\*\*(\d+)',
                            r'totalSupply\s*=.*?(\d+)\s*\*\s*10\*\*(\d+)'
                        ]
                        
                        total_supply = 0
                        for ts_pattern in total_supply_patterns:
                            ts_matches = re.findall(ts_pattern, source_code, re.IGNORECASE)
                            if ts_matches:
                                if len(ts_matches[0]) == 2:  # Avec 10**decimals
                                    base_ts = int(ts_matches[0][0])
                                    decimals_ts = int(ts_matches[0][1])
                                    total_supply = base_ts * (10 ** decimals_ts)
                                else:
                                    total_supply = int(ts_matches[0])
                                break
                        
                        if total_supply > 0 and max_buy_value > 0:
                            max_buy_percent = (max_buy_value / total_supply) * 100
                            result += f"• Max buy: {max_buy_percent:.2f}% of supply\n"
                        elif max_buy_value <= 100:  # Probablement déjà un pourcentage
                            result += f"• Max buy: {max_buy_value}% of supply\n"
                        else:
                            result += f"• Max buy: {max_buy_value} tokens\n"
                        
                        max_buy_found = True
                        break
                
                if not max_buy_found:
                    result += "• Max buy detection: keywords found but value not parsed\n"
                
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

# Démarrer le serveur de santé en arrière-plan
health_thread = threading.Thread(target=start_health_server, daemon=True)
health_thread.start()

# Démarrer le keep-alive en arrière-plan
keep_alive_thread = threading.Thread(target=start_keep_alive, daemon=True)
keep_alive_thread.start()

print("🔄 Keep-alive system activated (ping every 10 minutes)")
print("🚀 Starting bot...")
application.run_polling()
