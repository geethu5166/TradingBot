import os
import asyncio
import pandas as pd
import numpy as np
import yfinance as yf
import ta
import google.generativeai as genai
from telegram import Bot
from datetime import datetime
import json

# ================= CONFIGURATION =================
# Google Gemini API Key
GEMINI_API_KEY = "AIzaSyBRv2VeVyPmLPcv1DUNIRl79RldR7uAv2A"

# Telegram Configuration
TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN_HERE"  # <--- REPLACE THIS WITH YOUR BOT TOKEN FROM @BotFather
TELEGRAM_CHAT_ID = "1443052083"

# Market Configuration (Indian Markets)
TARGET_ASSETS = {
    "NIFTY_50": "^NSEI",
    "BANK_NIFTY": "^NSEBANK",
    "SENSEX": "^BSESN",
    "MIDCAP_100": "^NSEMDCP50"  # Using Nifty Midcap 150 or similar proxy if specific index ticker varies
}

# Trading Mode
TIMEFRAME = "1d"  # 1 day for short-term, use '5m' or '15m' for intraday (requires premium data for some indices)
LOOKBACK_PERIOD = 60  # Days to analyze

# ================= INITIALIZE SERVICES =================
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-pro')

bot = Bot(token=TELEGRAM_BOT_TOKEN) if TELEGRAM_BOT_TOKEN != "YOUR_TELEGRAM_BOT_TOKEN_HERE" else None

# ================= DATA FETCHING & ANALYSIS =================
def fetch_market_data(symbol):
    """Fetches historical data and calculates technical indicators."""
    try:
        df = yf.download(symbol, period=f"{LOOKBACK_PERIOD}d", interval="1d", progress=False)
        if df.empty or len(df) < 20:
            return None
        
        # Flatten columns if multi-index (common in new yfinance versions)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        df = df.dropna()
        
        # Technical Indicators
        df['RSI'] = ta.momentum.RSIIndicator(df['Close'], window=14).rsi()
        df['MACD'] = ta.trend.MACD(df['Close']).macd()
        df['MACD_Signal'] = ta.trend.MACD(df['Close']).macd_signal()
        df['BB_High'] = ta.volatility.BollingerBands(df['Close']).bollinger_hband()
        df['BB_Low'] = ta.volatility.BollingerBands(df['Close']).bollinger_lband()
        df['SMA_50'] = ta.trend.SMAIndicator(df['Close'], window=50).sma_indicator()
        df['SMA_200'] = ta.trend.SMAIndicator(df['Close'], window=200).sma_indicator()
        df['ADX'] = ta.trend.ADXIndicator(df['High'], df['Low'], df['Close']).adx()
        
        # Volatility and Momentum
        df['Volatility'] = df['Close'].pct_change().rolling(window=14).std()
        df['Momentum'] = ta.momentum.ROCIndicator(df['Close'], window=10).roc()
        
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        return {
            "symbol": symbol,
            "current_price": latest['Close'],
            "change_pct": ((latest['Close'] - prev['Close']) / prev['Close']) * 100,
            "rsi": latest['RSI'],
            "macd": latest['MACD'],
            "macd_signal": latest['MACD_Signal'],
            "bb_high": latest['BB_High'],
            "bb_low": latest['BB_Low'],
            "sma_50": latest['SMA_50'],
            "sma_200": latest['SMA_200'],
            "adx": latest['ADX'],
            "volatility": latest['Volatility'],
            "momentum": latest['Momentum'],
            "volume": latest['Volume'],
            "avg_volume": df['Volume'].rolling(window=20).mean().iloc[-1],
            "trend": "Bullish" if latest['Close'] > latest['SMA_50'] else "Bearish"
        }
    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
        return None

# ================= AGENT SIMULATION ENGINE =================
async def simulate_1000_agents(data):
    """
    Simulates 1000 agents by prompting Gemini to act as 5 distinct squads 
    (200 agents each) and then a Chief Investment Officer to finalize the decision.
    """
    
    data_context = f"""
    Market Data for {data['symbol']}:
    - Current Price: {data['current_price']:.2f}
    - Daily Change: {data['change_pct']:.2f}%
    - RSI (14): {data['rsi']:.2f}
    - MACD: {data['macd']:.4f} | Signal: {data['macd_signal']:.4f}
    - Bollinger Bands: High {data['bb_high']:.2f} | Low {data['bb_low']:.2f}
    - SMA 50: {data['sma_50']:.2f} | SMA 200: {data['sma_200']:.2f}
    - ADX (Trend Strength): {data['adx']:.2f}
    - Momentum (ROC): {data['momentum']:.2f}
    - Volume: {data['volume']} | Avg Vol: {data['avg_volume']:.0f}
    - Primary Trend: {data['trend']}
    """

    prompt = f"""
    You are the central processing unit for a hedge fund consisting of 1,000 expert trading agents. 
    These agents are divided into 5 specialized squads (200 agents each):
    
    1. **Technical Analysts**: Focus on RSI, MACD, Bollinger Bands, and Chart Patterns.
    2. **Quantitative Strategists**: Focus on Statistical Arbitrage, Mean Reversion, and Volatility.
    3. **Macro & Sentiment Experts**: Analyze market regime, news sentiment, and institutional flow (FII/DII).
    4. **Risk Managers**: Focus on Drawdown protection, Stop-loss placement, and Position Sizing.
    5. **Algorithmic High-Frequency Traders**: Focus on momentum bursts and volume anomalies.

    **Task**:
    Based on the following market data for an Indian Market Asset, simulate a rigorous debate among these 5 squads.
    Each squad should provide a brief summary of their stance (Bullish, Bearish, or Neutral) and their key reasoning.
    Finally, act as the **Chief Investment Officer (CIO)** to synthesize these views into a SINGLE final decision.

    **Market Data**:
    {data_context}

    **Output Format (JSON ONLY)**:
    {{
        "debate_summary": {{
            "technical_squad": "Summary of technical view...",
            "quant_squad": "Summary of quant view...",
            "macro_squad": "Summary of macro/sentiment view...",
            "risk_squad": "Summary of risk assessment...",
            "algo_squad": "Summary of algo/momentum view..."
        }},
        "final_decision": "BUY" or "SELL" or "HOLD",
        "trade_type": "INTRADAY" or "SHORT_TERM",
        "confidence_score": 0-100,
        "entry_zone": "Price range for entry",
        "stop_loss": "Specific price level",
        "take_profit": "Specific price level",
        "reasoning": "Concise summary of why the 1000 agents agreed on this."
    }}
    
    Ensure the analysis considers the specific characteristics of the Indian market (volatility, opening gaps, FII influence).
    """

    try:
        response = await model.generate_content_async(prompt)
        text_response = response.text
        
        # Clean up markdown code blocks if present
        if "```json" in text_response:
            text_response = text_response.split("```json")[1].split("```")[0]
        elif "```" in text_response:
            text_response = text_response.split("```")[1].split("```")[0]
            
        return json.loads(text_response.strip())
    except Exception as e:
        print(f"Error in Agent Simulation: {e}")
        return {
            "error": str(e),
            "final_decision": "HOLD",
            "reasoning": "Failed to parse agent consensus due to API error."
        }

# ================= TELEGRAM NOTIFICATION =================
async def send_telegram_alert(signal_data, symbol_name):
    if not bot:
        print("Telegram Bot not initialized. Check Token.")
        return

    message = f"""
🚀 **MULTI-AGENT TRADING SIGNAL** 🚀
Asset: **{symbol_name}**
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

📊 **FINAL VERDICT**: **{signal_data.get('final_decision', 'HOLD')}**
Type: {signal_data.get('trade_type', 'N/A')}
Confidence: {signal_data.get('confidence_score', 0)}%

💰 **EXECUTION DETAILS**:
Entry Zone: {signal_data.get('entry_zone', 'N/A')}
Stop Loss: {signal_data.get('stop_loss', 'N/A')}
Take Profit: {signal_data.get('take_profit', 'N/A')}

🧠 **CONSENSUS FROM 1000 AGENTS**:
{signal_data.get('reasoning', 'No reasoning available')}

---
👥 **SQUAD BREAKDOWN**:
🔹 Tech: {signal_data.get('debate_summary', {}).get('technical_squad', 'N/A')}
🔹 Quant: {signal_data.get('debate_summary', {}).get('quant_squad', 'N/A')}
🔹 Macro: {signal_data.get('debate_summary', {}).get('macro_squad', 'N/A')}
🔹 Risk: {signal_data.get('debate_summary', {}).get('risk_squad', 'N/A')}

*Disclaimer: This is AI-generated analysis. Not financial advice. Trade at your own risk.*
    """

    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode='Markdown')
        print(f"Alert sent to Telegram for {symbol_name}")
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")

# ================= MAIN EXECUTION =================
async def main():
    print("🚀 Starting Multi-Agent Trading System (Indian Markets)...")
    print(f"Using Model: Gemini 1.5 Pro")
    print(f"Target Chat ID: {TELEGRAM_CHAT_ID}")
    
    # Select asset to analyze (Default: NIFTY_50)
    # Change this loop to iterate over TARGET_ASSETS.values() if you want all
    asset_name = "NIFTY_50"
    ticker = TARGET_ASSETS[asset_name]
    
    print(f"\nAnalyzing {asset_name} ({ticker})...")
    
    # 1. Fetch Data
    market_data = fetch_market_data(ticker)
    
    if not market_data:
        print("Failed to fetch market data. Exiting.")
        return

    print(f"Data fetched. Current Price: {market_data['current_price']}")
    
    # 2. Simulate 1000 Agents
    print("🧠 Simulating 1000 Expert Agents (Debate Phase)...")
    signal = await simulate_1000_agents(market_data)
    
    if "error" in signal:
        print(f"Agent simulation error: {signal['error']}")
        return

    print(f"✅ Consensus Reached: {signal['final_decision']}")
    
    # 3. Send Alert
    if signal['final_decision'] != "HOLD":
        await send_telegram_alert(signal, asset_name)
    else:
        print("No trade signal generated (HOLD). Sending summary anyway?")
        # Uncomment next line to receive HOLD signals too
        # await send_telegram_alert(signal, asset_name)

if __name__ == "__main__":
    if TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        print("❌ ERROR: Please set your TELEGRAM_BOT_TOKEN in the code before running.")
    else:
        asyncio.run(main())