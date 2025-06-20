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
            
            # Max buy/wallet limits - détection généraliste pour tous les contrats
            max_buy_found = False
            
            import re
            
            # Patterns universels pour tous les types de contrats
            universal_patterns = [
                # 1. Variables de max buy classiques (division simple)
                r'uint256.*?(?:maxBuy|maxWallet|maxTransaction|maxTx).*?=\s*(?:_totalSupply|totalSupply\(\)|MAX_SUPPLY|initialTotalSupply)\s*/\s*(\d+)',
                
                # 2. Variables avec multiplication puis division : (totalSupply * X) / Y
                r'uint256.*?(?:maxBuy|maxWallet|maxTransaction|maxTx).*?=\s*\((?:_totalSupply|totalSupply\(\)|MAX_SUPPLY|initialTotalSupply)\s*\*\s*(\d+)\)\s*/\s*(\d+)',
                
                # 3. Assignments directs (division)
                r'(?:maxBuy|maxWallet|maxTransaction|maxTx)Amount\s*=\s*(?:_totalSupply|totalSupply\(\)|MAX_SUPPLY|initialTotalSupply)\s*/\s*(\d+)',
                r'_(?:maxBuy|maxWallet|maxTransaction|maxTx)Amount\s*=\s*(?:_totalSupply|totalSupply\(\)|MAX_SUPPLY|initialTotalSupply)\s*/\s*(\d+)',
                
                # 4. Assignments avec multiplication/division : maxBuy = (totalSupply * X) / Y
                r'(?:maxBuy|maxWallet|maxTransaction|maxTx).*?=\s*\((?:_totalSupply|totalSupply\(\)|MAX_SUPPLY|initialTotalSupply)\s*\*\s*(\d+)\)\s*/\s*(\d+)',
                
                # 5. Dans les constructeurs
                r'constructor[^}]*?(?:maxBuy|maxWallet|maxTransaction)[^}]*?(?:_totalSupply|MAX_SUPPLY|initialTotalSupply)\s*/\s*(\d+)',
                r'constructor[^}]*?(?:maxBuy|maxWallet|maxTransaction)[^}]*?\((?:_totalSupply|MAX_SUPPLY|initialTotalSupply)\s*\*\s*(\d+)\)\s*/\s*(\d+)',
                
                # 6. Patterns avec pourcentages en commentaires
                r'(?:maxBuy|maxWallet|maxTransaction)[^=]*?=\s*(?:_totalSupply|MAX_SUPPLY|initialTotalSupply)\s*/\s*(\d+)[^;]*?;//[^0-9]*?(\d+(?:\.\d+)?)%',
            ]
            
            found_max_buys = []
            
            for pattern in universal_patterns:
                matches = re.findall(pattern, source_code, re.IGNORECASE | re.MULTILINE)
                for match in matches:
                    try:
                        if isinstance(match, tuple):
                            if len(match) == 3:
                                # Pattern avec multiplication/division : (totalSupply * X) / Y
                                numerator = int(match[0])
                                denominator = int(match[1])
                                percentage = (numerator / denominator) * 100
                                # Validation : pourcentage réaliste (0.01% à 20%)
                                if 0.01 <= percentage <= 20:
                                    found_max_buys.append(f"{percentage:.2f}%")
                            elif len(match) == 2:
                                # Pattern avec commentaire de pourcentage
                                divisor = int(match[0])
                                percentage = float(match[1])
                                # Validation : pourcentage réaliste (0.01% à 20%)
                                if 0.01 <= percentage <= 20 and 5 <= divisor <= 10000:
                                    found_max_buys.append(f"{percentage}%")
                        else:
                            # Pattern simple avec diviseur
                            divisor = int(match)
                            # Validation : diviseurs réalistes pour max buy
                            if 5 <= divisor <= 1000:  # De 0.1% (1000) à 20% (5)
                                percentage = 100 / divisor
                                if percentage <= 20:  # Max 20% de supply
                                    found_max_buys.append(f"{percentage:.2f}%")
                    except (ValueError, IndexError, ZeroDivisionError):
                        continue
            
            # Supprimer les doublons et prendre les 2 premiers résultats
            if found_max_buys:
                unique_max_buys = list(set(found_max_buys))[:2]
                result += "💰 MAX BUY LIMITS:\n"
                for max_buy in unique_max_buys:
                    result += f"• Max buy: {max_buy} of supply\n"
                result += "\n"
                max_buy_found = True
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
