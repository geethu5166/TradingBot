import os
import time
import json
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Indian Market Symbols
INDIAN_INDICES = {
    "NIFTY50": "^NSEI",
    "BANKNIFTY": "^NSXBANK",
    "SENSEX": "^BSESN",
    "NIFTYMIDCAP": "^NSEMDCP50"
}

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    import google.generativeai as genai
    import yfinance as yf
    import ta
    import pandas as pd
    import requests
except ImportError as e:
    logger.error(f"Missing dependency: {e}")
    logger.info("Run: pip install google-generativeai yfinance ta python-dotenv requests")
    exit(1)

# Initialize Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

def fetch_market_data(symbol, ticker):
    """Fetch real-time market data for Indian indices"""
    try:
        data = yf.download(ticker, period="5d", interval="1m", progress=False)
        if data.empty:
            # Fallback to daily data if 1m not available for indices
            data = yf.download(ticker, period="6mo", interval="1d", progress=False)
        
        if data.empty:
            return None
            
        # Calculate Technical Indicators
        df = data.copy()
        
        # RSI
        df['RSI'] = ta.momentum.RSIIndicator(df['Close'], window=14).rsi()
        
        # MACD
        macd = ta.trend.MACD(df['Close'])
        df['MACD'] = macd.macd()
        df['MACD_Signal'] = macd.macd_signal()
        
        # Bollinger Bands
        bb = ta.volatility.BollingerBands(df['Close'])
        df['BB_High'] = bb.bollinger_hband()
        df['BB_Low'] = bb.bollinger_lband()
        
        # Moving Averages
        df['SMA_20'] = ta.trend.sma_indicator(df['Close'], window=20)
        df['SMA_50'] = ta.trend.sma_indicator(df['Close'], window=50)
        df['EMA_12'] = ta.trend.ema_indicator(df['Close'], window=12)
        
        # Get latest values
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest
        
        return {
            "symbol": symbol,
            "price": float(latest['Close']),
            "change_pct": float(((latest['Close'] - prev['Close']) / prev['Close']) * 100),
            "volume": float(latest.get('Volume', 0)),
            "rsi": float(latest['RSI']) if not pd.isna(latest['RSI']) else 50.0,
            "macd": float(latest['MACD']) if not pd.isna(latest['MACD']) else 0.0,
            "macd_signal": float(latest['MACD_Signal']) if not pd.isna(latest['MACD_Signal']) else 0.0,
            "bb_high": float(latest['BB_High']) if not pd.isna(latest['BB_High']) else latest['Close'],
            "bb_low": float(latest['BB_Low']) if not pd.isna(latest['BB_Low']) else latest['Close'],
            "sma_20": float(latest['SMA_20']) if not pd.isna(latest['SMA_20']) else latest['Close'],
            "sma_50": float(latest['SMA_50']) if not pd.isna(latest['SMA_50']) else latest['Close'],
            "trend": "BULLISH" if latest['Close'] > latest['SMA_20'] else "BEARISH"
        }
    except Exception as e:
        logger.error(f"Error fetching data for {symbol}: {e}")
        return None

def simulate_1000_agents(market_data):
    """Simulate 1000 expert agents using 5 specialized squads"""
    
    prompt = f"""
You are the Chief Investment Officer of a hedge fund managing 1,000 expert trading agents.
Your agents are divided into 5 specialized squads (200 agents each):

1. TECHNICAL SQUAD: Analyzes charts, RSI, MACD, Moving Averages, Bollinger Bands
2. QUANT SQUAD: Statistical arbitrage, mean reversion, momentum strategies
3. MACRO SQUAD: Economic indicators, interest rates, inflation, geopolitical events
4. SENTIMENT SQUAD: News analysis, social media sentiment, institutional flows
5. RISK SQUAD: Volatility assessment, position sizing, stop-loss optimization

MARKET DATA FOR ANALYSIS:
{json.dumps(market_data, indent=2)}

TASK:
1. Each squad debates internally and provides their collective recommendation (BUY/SELL/HOLD)
2. You must synthesize all 5 squad reports into ONE final decision
3. Determine if this is suitable for INTRADAY or SHORT-TERM (1-5 days)
4. Provide specific entry price, stop-loss, and take-profit levels
5. Assign a confidence score (0-100%)

OUTPUT FORMAT (JSON ONLY, no markdown):
{{
    "squads": {{
        "technical": {{"vote": "BUY/SELL/HOLD", "reasoning": "...", "confidence": 0-100}},
        "quant": {{"vote": "BUY/SELL/HOLD", "reasoning": "...", "confidence": 0-100}},
        "macro": {{"vote": "BUY/SELL/HOLD", "reasoning": "...", "confidence": 0-100}},
        "sentiment": {{"vote": "BUY/SELL/HOLD", "reasoning": "...", "confidence": 0-100}},
        "risk": {{"vote": "BUY/SELL/HOLD", "reasoning": "...", "confidence": 0-100}}
    }},
    "final_decision": "BUY/SELL/HOLD",
    "timeframe": "INTRADAY/SHORT_TERM",
    "entry_zone": [min_price, max_price],
    "stop_loss": price,
    "take_profit": [target1, target2],
    "overall_confidence": 0-100,
    "key_reasoning": "concise summary of why",
    "risk_warning": "any major risks to consider"
}}
"""
    
    try:
        response = model.generate_content(prompt)
        # Extract JSON from response
        text = response.text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        
        return json.loads(text)
    except Exception as e:
        logger.error(f"AI Analysis failed: {e}")
        return None

def send_telegram_message(message):
    """Send formatted message to Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            logger.info("Telegram alert sent successfully")
            return True
        else:
            logger.error(f"Telegram API error: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return False

def format_alert(symbol, analysis):
    """Format the analysis into a readable Telegram alert"""
    if not analysis:
        return None
    
    squads = analysis.get('squads', {})
    emoji = "🟢" if analysis['final_decision'] == "BUY" else "🔴" if analysis['final_decision'] == "SELL" else "⚪"
    
    message = f"""
{emoji} *MULTI-AGENT TRADING SIGNAL* {emoji}

📊 *Asset:* {symbol}
🎯 *Decision:* *{analysis['final_decision']}*
⏱️ *Timeframe:* {analysis['timeframe'].replace('_', ' ')}
💯 *Confidence:* {analysis['overall_confidence']}%

📈 *ENTRY ZONE:*
   Min: {analysis['entry_zone'][0]:.2f}
   Max: {analysis['entry_zone'][1]:.2f}

🛑 *STOP LOSS:* {analysis['stop_loss']:.2f}

💰 *TAKE PROFIT:*
   Target 1: {analysis['take_profit'][0]:.2f}
   Target 2: {analysis['take_profit'][1]:.2f}

🧠 *SQUAD VOTES:*
• Technical: {squads.get('technical', {}).get('vote', 'N/A')} ({squads.get('technical', {}).get('confidence', 0)}%)
• Quant: {squads.get('quant', {}).get('vote', 'N/A')} ({squads.get('quant', {}).get('confidence', 0)}%)
• Macro: {squads.get('macro', {}).get('vote', 'N/A')} ({squads.get('macro', {}).get('confidence', 0)}%)
• Sentiment: {squads.get('sentiment', {}).get('vote', 'N/A')} ({squads.get('sentiment', {}).get('confidence', 0)}%)
• Risk: {squads.get('risk', {}).get('vote', 'N/A')} ({squads.get('risk', {}).get('confidence', 0)}%)

💡 *Key Reasoning:*
_{analysis['key_reasoning']}_

⚠️ *Risk Warning:* {analysis['risk_warning']}

🕒 *Generated:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}
"""
    return message

def main():
    """Main trading loop"""
    logger.info("🚀 Multi-Agent Trading System Started")
    logger.info(f"Monitoring: {list(INDIAN_INDICES.keys())}")
    
    # Send startup notification
    send_telegram_message("🤖 *Trading Agent Online*\n\nMonitoring Indian Markets (Nifty, BankNifty, Sensex, Midcap)\n\nSystem ready for analysis...")
    
    while True:
        try:
            current_time = datetime.now()
            
            # Only run during Indian market hours (9:15 AM - 3:30 PM IST)
            # For demo, we run 24/7 but you can add time checks
            # if 9 <= current_time.hour <= 15:  # Approx IST check
            
            for symbol, ticker in INDIAN_INDICES.items():
                logger.info(f"Analyzing {symbol}...")
                
                # Fetch market data
                market_data = fetch_market_data(symbol, ticker)
                
                if not market_data:
                    logger.warning(f"No data for {symbol}, skipping...")
                    continue
                
                logger.info(f"{symbol}: Price={market_data['price']}, RSI={market_data['rsi']:.2f}, Trend={market_data['trend']}")
                
                # Run 1000-agent simulation
                analysis = simulate_1000_agents(market_data)
                
                if analysis and analysis['final_decision'] != "HOLD":
                    # Send alert only for BUY/SELL signals
                    message = format_alert(symbol, analysis)
                    if message:
                        send_telegram_message(message)
                        logger.info(f"Signal sent for {symbol}: {analysis['final_decision']}")
                
                # Wait between symbols to avoid rate limits
                time.sleep(5)
            
            # Wait 15 minutes before next full scan
            logger.info("Waiting 15 minutes before next scan...")
            time.sleep(900)
            
        except KeyboardInterrupt:
            logger.info("System shutdown requested")
            send_telegram_message("⚠️ Trading Agent Stopped by user")
            break
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
