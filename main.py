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
            
            # Max buy limits - détection dans le code source
            max_buy_found = False
            
            # Chercher les valeurs hardcodées dans le constructeur ou les variables d'initialisation
            import re
            
            # Patterns pour les max buy dans le code source (valeurs hardcodées)
            constructor_patterns = [
                # Dans le constructeur avec pourcentages directs
                r'maxBuyAmount\s*=\s*_totalSupply\s*\*\s*(\d+)\s*/\s*100',
                r'_maxBuyAmount\s*=\s*_totalSupply\s*\*\s*(\d+)\s*/\s*100',
                r'maxTransactionAmount\s*=\s*_totalSupply\s*\*\s*(\d+)\s*/\s*100',
                
                # Avec division directe 
                r'maxBuyAmount\s*=\s*_totalSupply\s*/\s*(\d+)',
                r'_maxBuyAmount\s*=\s*_totalSupply\s*/\s*(\d+)',
                r'maxTransactionAmount\s*=\s*_totalSupply\s*/\s*(\d+)',
                
                # Valeurs fixes dans le constructeur
                r'maxBuyAmount\s*=\s*(\d+)\s*\*\s*10\*\*(\d+)',
                r'_maxBuyAmount\s*=\s*(\d+)\s*\*\s*10\*\*(\d+)',
                
                # Patterns avec commentaires de pourcentage
                r'//.*?(\d+)%.*?\n.*?maxBuyAmount\s*=',
                r'/\*.*?(\d+)%.*?\*/.*?maxBuyAmount\s*=',
                
                # Patterns pour les tokens typiques avec 1%, 2%, 3% etc
                r'maxBuyAmount\s*=\s*totalSupply\(\)\s*/\s*(\d+)',
                r'_maxBuyAmount\s*=\s*totalSupply\(\)\s*/\s*(\d+)',
                
                # Variables déclarées avec des fractions du total supply
                r'uint256.*?maxBuy.*?=\s*_totalSupply\s*/\s*(\d+)',
                r'uint256.*?_maxBuy.*?=\s*_totalSupply\s*/\s*(\d+)',
            ]
            
            # Chercher dans le code source
            for pattern in constructor_patterns:
                matches = re.findall(pattern, source_code, re.IGNORECASE | re.MULTILINE)
                if matches:
                    if len(matches[0]) == 2:  # Pattern avec decimals (comme 2 * 10**18)
                        base_value = int(matches[0][0])
                        # C'est probablement un pourcentage si base_value < 100
                        if base_value <= 100:
                            result += "💰 MAX BUY LIMITS:\n"
                            result += f"• Max buy: {base_value}% of supply (hardcoded)\n"
                            max_buy_found = True
                            break
                    else:
                        value = int(matches[0])
                        result += "💰 MAX BUY LIMITS:\n"
                        
                        # Si division par X, c'est 100/X %
                        if '/\s*(\d+)' in pattern:
                            percentage = 100 / value
                            result += f"• Max buy: {percentage:.1f}% of supply (1/{value} of total)\n"
                        # Si multiplication par X / 100, c'est X%
                        elif '\*\s*(\d+)\s*/\s*100' in pattern:
                            result += f"• Max buy: {value}% of supply (hardcoded)\n"
                        else:
                            result += f"• Max buy: {value}% of supply (hardcoded)\n"
                        
                        max_buy_found = True
                        break
            
            # Si pas trouvé, chercher des patterns plus génériques
            if not max_buy_found:
                # Chercher des commentaires avec des pourcentages près des max buy
                comment_patterns = [
                    r'//.*?(\d+)%.*?max.*?buy',
                    r'/\*.*?(\d+)%.*?max.*?buy.*?\*/',
                    r'//.*?max.*?buy.*?(\d+)%',
                    r'/\*.*?max.*?buy.*?(\d+)%.*?\*/'
                ]
                
                for pattern in comment_patterns:
                    matches = re.findall(pattern, source_code, re.IGNORECASE | re.MULTILINE)
                    if matches:
                        percentage = int(matches[0])
                        result += "💰 MAX BUY LIMITS:\n"
                        result += f"• Max buy: {percentage}% of supply (from comments)\n"
                        max_buy_found = True
                        break
            
            # Chercher des patterns typiques dans les tokens modernes
            if not max_buy_found:
                # Beaucoup de tokens utilisent des fractions standard
                standard_fractions = [
                    r'maxBuyAmount\s*=\s*_totalSupply\s*/\s*50',  # 2%
                    r'maxBuyAmount\s*=\s*_totalSupply\s*/\s*100', # 1%
                    r'maxBuyAmount\s*=\s*_totalSupply\s*/\s*33',  # ~3%
                    r'maxBuyAmount\s*=\s*_totalSupply\s*/\s*25',  # 4%
                    r'_maxBuyAmount\s*=\s*_totalSupply\s*/\s*50',
                    r'_maxBuyAmount\s*=\s*_totalSupply\s*/\s*100',
                    r'_maxBuyAmount\s*=\s*_totalSupply\s*/\s*33',
                    r'_maxBuyAmount\s*=\s*_totalSupply\s*/\s*25'
                ]
                
                fraction_map = {50: "2%", 100: "1%", 33: "3%", 25: "4%", 20: "5%"}
                
                for pattern in standard_fractions:
                    if re.search(pattern, source_code, re.IGNORECASE):
                        divisor = int(re.search(r'/\s*(\d+)', pattern).group(1))
                        percentage = fraction_map.get(divisor, f"{100/divisor:.1f}%")
                        result += "💰 MAX BUY LIMITS:\n"
                        result += f"• Max buy: {percentage} of supply (1/{divisor} of total)\n"
                        max_buy_found = True
                        break
            
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
