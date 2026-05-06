import os
import time
import json
import requests
from datetime import datetime
from dotenv import load_dotenv
import google.generativeai as genai
import yfinance as yf
import pandas as pd
import ta

# Load environment variables
load_dotenv()

# Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Indian Market Symbols
SYMBOLS = {
    "NIFTY 50": "^NSEI",
    "BANK NIFTY": "^NSEBANK",
    "SENSEX": "^BSESN",
    "NIFTY MIDCAP": "^NSEMDCP50"
}

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-pro')

def send_telegram_message(message):
    """Send message to Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=data)
        print(f"Telegram alert sent at {datetime.now()}")
    except Exception as e:
        print(f"Telegram error: {e}")

def fetch_market_data(symbol_ticker):
    """Fetch real-time market data and calculate indicators"""
    ticker = yf.Ticker(symbol_ticker)
    df = ticker.history(period="5d", interval="5m")
    
    if df.empty:
        return None

    # Calculate Technical Indicators
    df['RSI'] = ta.momentum.RSIIndicator(df['Close'], window=14).rsi()
    df['MACD'] = ta.trend.MACD(df['Close']).macd()
    df['BB_High'] = ta.volatility.BollingerBands(df['Close']).bollinger_hband()
    df['BB_Low'] = ta.volatility.BollingerBands(df['Close']).bollinger_lband()
    df['SMA_20'] = ta.trend.sma_indicator(df['Close'], window=20)
    df['SMA_50'] = ta.trend.sma_indicator(df['Close'], window=50)
    
    current = df.iloc[-1]
    prev = df.iloc[-2]
    
    return {
        "symbol": symbol_ticker,
        "price": current['Close'],
        "rsi": current['RSI'],
        "macd": current['MACD'],
        "bb_high": current['BB_High'],
        "bb_low": current['BB_Low'],
        "sma_20": current['SMA_20'],
        "sma_50": current['SMA_50'],
        "trend": "Bullish" if current['SMA_20'] > current['SMA_50'] else "Bearish",
        "volume": current['Volume'],
        "change_pct": ((current['Close'] - prev['Close']) / prev['Close']) * 100
    }

def simulate_1000_agents(data):
    """Simulate 1000 agents using 5 specialized squads via Gemini"""
    
    prompt = f"""
    Act as a Multi-Agent Trading System representing 1,000 expert traders divided into 5 squads.
    Analyze the following market data for {data['symbol']} and provide a consensus decision.
    
    MARKET DATA:
    - Current Price: {data['price']:.2f}
    - RSI (14): {data['rsi']:.2f}
    - MACD: {data['macd']:.2f}
    - Bollinger Upper: {data['bb_high']:.2f}
    - Bollinger Lower: {data['bb_low']:.2f}
    - SMA 20: {data['sma_20']:.2f}
    - SMA 50: {data['sma_50']:.2f}
    - Trend: {data['trend']}
    - Volume: {data['volume']:.0f}
    - Change %: {data['change_pct']:.2f}%

    SIMULATE THE FOLLOWING SQUADS (200 agents each):
    1. Technical Squad: Focus on RSI, MACD, Moving Averages.
    2. Quant Squad: Focus on statistical patterns and volatility.
    3. Macro Squad: Consider Indian market context (Nifty/BankNifty behavior).
    4. Sentiment Squad: Analyze momentum and volume spikes.
    5. Risk Squad: Evaluate stop-loss levels and risk/reward ratio.

    OUTPUT FORMAT (Strict JSON):
    {{
        "technical_verdict": "BUY/SELL/HOLD",
        "quant_verdict": "BUY/SELL/HOLD",
        "macro_verdict": "BUY/SELL/HOLD",
        "sentiment_verdict": "BUY/SELL/HOLD",
        "risk_verdict": "BUY/SELL/HOLD",
        "final_decision": "BUY/SELL/HOLD",
        "confidence_score": "0-100",
        "timeframe": "Intraday or Short-term",
        "entry_zone": "Price range",
        "stop_loss": "Price level",
        "take_profit": "Price level",
        "reasoning": "Brief summary of the 1000 agents' debate"
    }}
    """
    
    try:
        response = model.generate_content(prompt)
        text = response.text
        # Extract JSON from markdown code blocks if present
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        
        return json.loads(text.strip())
    except Exception as e:
        return {
            "final_decision": "HOLD",
            "confidence_score": 0,
            "reasoning": f"Error analyzing data: {str(e)}",
            "timeframe": "N/A",
            "entry_zone": "N/A",
            "stop_loss": "N/A",
            "take_profit": "N/A"
        }

def format_alert(symbol, data, analysis):
    """Format the final Telegram alert"""
    emoji = "🟢" if analysis['final_decision'] == "BUY" else ("🔴" if analysis['final_decision'] == "SELL" else "⚪")
    
    message = f"""
{emoji} *MULTI-AGENT TRADING SIGNAL* {emoji}
*Asset:* {symbol}
*Decision:* *{analysis['final_decision']}*
*Confidence:* {analysis['confidence_score']}%
*Timeframe:* {analysis['timeframe']}

*Market Status:*
Price: ₹{data['price']:.2f}
RSI: {data['rsi']:.2f}
Trend: {data['trend']}

*Strategy Details:*
🎯 Entry: {analysis['entry_zone']}
🛑 Stop Loss: {analysis['stop_loss']}
💰 Take Profit: {analysis['take_profit']}

*Agent Consensus:*
_{analysis['reasoning']}_

⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} IST
    """
    return message.strip()

def main():
    print("🚀 Starting 1000-Agent Trading System...")
    send_telegram_message("🤖 *System Started*\nMonitoring Indian Markets (Nifty, BankNifty, Sensex)...")
    
    while True:
        try:
            for name, ticker in SYMBOLS.items():
                print(f"Analyzing {name}...")
                data = fetch_market_data(ticker)
                
                if data:
                    analysis = simulate_1000_agents(data)
                    message = format_alert(name, data, analysis)
                    send_telegram_message(message)
                else:
                    print(f"No data for {name}")
            
            # Wait 15 minutes before next scan
            print("Sleeping for 15 minutes...")
            time.sleep(900)
            
        except KeyboardInterrupt:
            send_telegram_message("⛔ System stopped by user.")
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
