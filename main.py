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
            
            # Max buy/wallet limits - détection du PREMIER BLOC seulement
            max_buy_found = False
            
            import re
            
            # Chercher spécifiquement les patterns du premier bloc/première condition
            first_block_patterns = [
                # Pattern pour la première condition temporelle (< 60 secondes)
                r'if\s*\([^}]*?<\s*60[^}]*?\)[^}]*?MAX_SUPPLY\s*/\s*(\d+)',
                r'if\s*\([^}]*?<\s*60[^}]*?\)[^}]*?_totalSupply\s*/\s*(\d+)',
                
                # Pattern avec commentaire de pourcentage + première condition
                r'//.*?(\d+(?:\.\d+)?)%[^}]*?\n[^}]*?if[^}]*?<\s*60[^}]*?MAX_SUPPLY\s*/\s*(\d+)',
                
                # Patterns pour les premiers returns dans les fonctions temporelles
                r'_diffSeconds\s*<\s*60[^}]*?MAX_SUPPLY\s*/\s*(\d+)[^}]*?//.*?(\d+(?:\.\d+)?)%',
                r'_diffSeconds\s*<\s*60[^}]*?_maxWallet\s*=\s*MAX_SUPPLY\s*/\s*(\d+)',
                
                # Pattern pour block.number == startBlock (premier bloc)
                r'block\.number\s*==\s*startBlock[^}]*?MAX_SUPPLY\s*/\s*(\d+)',
                r'block\.number\s*==\s*startBlock[^}]*?_totalSupply\s*/\s*(\d+)',
                
                # Patterns pour le très début du trading
                r'if\s*\([^}]*?diffSeconds\s*<\s*60[^}]*?\)[^}]*?MAX_SUPPLY\s*/\s*(\d+)',
                r'if\s*\([^}]*?_diffSeconds\s*<\s*60[^}]*?\)[^}]*?MAX_SUPPLY\s*/\s*(\d+)',
                
                # Patterns avec les premières conditions (plus strictes)
                r'if\s*\([^}]*?<\s*(?:60|1\s*\*\s*60)[^}]*?\)[^}]*?/\s*(\d+)[^}]*?//.*?(\d+(?:\.\d+)?)%'
            ]
            
            for pattern in first_block_patterns:
                matches = re.findall(pattern, source_code, re.IGNORECASE | re.MULTILINE | re.DOTALL)
                if matches:
                    for match in matches:
                        if isinstance(match, tuple) and len(match) == 2:
                            # Pattern avec pourcentage dans commentaire
                            try:
                                divisor = int(match[1])
                                percentage = float(match[0])
                                if 10 <= divisor <= 2000:  # Diviseurs réalistes
                                    result += "💰 MAX BUY LIMITS:\n"
                                    result += f"• Initial max buy: {percentage}% of supply (first block)\n"
                                    max_buy_found = True
                                    break
                            except:
                                continue
                        else:
                            # Pattern simple avec diviseur
                            try:
                                divisor = int(match)
                                if 10 <= divisor <= 2000:  # Éviter les faux positifs
                                    percentage = 100 / divisor
                                    result += "💰 MAX BUY LIMITS:\n"
                                    result += f"• Initial max buy: {percentage:.2f}% of supply (first block)\n"
                                    max_buy_found = True
                                    break
                            except:
                                continue
                    
                    if max_buy_found:
                        break
            
            # Si pas trouvé avec les patterns temporels, chercher les patterns standards du premier bloc
            if not max_buy_found:
                simple_first_patterns = [
                    # Constructeur avec max buy initial
                    r'constructor[^}]*?maxBuyAmount\s*=\s*_totalSupply\s*/\s*(\d+)',
                    r'constructor[^}]*?_maxBuyAmount\s*=\s*_totalSupply\s*/\s*(\d+)',
                    
                    # Variables initiales avec MAX_SUPPLY
                    r'uint256.*?maxBuy.*?=\s*MAX_SUPPLY\s*/\s*(\d+)',
                    r'uint256.*?_maxBuy.*?=\s*MAX_SUPPLY\s*/\s*(\d+)',
                    
                    # Première condition dans _update ou transfer
                    r'function\s+_update[^}]*?MAX_SUPPLY\s*/\s*(\d+)[^}]*?(?:first|initial|start)',
                ]
                
                for pattern in simple_first_patterns:
                    matches = re.findall(pattern, source_code, re.IGNORECASE | re.MULTILINE | re.DOTALL)
                    if matches:
                        try:
                            divisor = int(matches[0])
                            if 10 <= divisor <= 2000:
                                percentage = 100 / divisor
                                result += "💰 MAX BUY LIMITS:\n"
                                result += f"• Initial max buy: {percentage:.2f}% of supply (first block)\n"
                                max_buy_found = True
                                break
                        except:
                            continue
            
            if max_buy_found:
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
