import os, time, requests, json
import pandas as pd
import yfinance as yf
import google.generativeai as genai
from dotenv import load_dotenv
from ta.momentum import RSIIndicator
from ta.trend import MACD, ADXIndicator, SMAIndicator
from ta.volatility import AverageTrueRange

# Load environment variables
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# CONFIGURATION
SYMBOLS = {
    "NIFTY 50": "^NSEI", 
    "BANK NIFTY": "^NSEBANK", 
    "MIDCAP 50": "^NSEMDCP50"
}
INTERVAL = "15m"

def get_advanced_indicators(df):
    """Calculates professional grade indicators."""
    adx = ADXIndicator(df['High'], df['Low'], df['Close'])
    df['adx'] = adx.adx()
    df['rsi'] = RSIIndicator(df['Close']).rsi()
    macd = MACD(df['Close'])
    df['macd_diff'] = macd.macd_diff()
    df['atr'] = AverageTrueRange(df['High'], df['Low'], df['Close']).average_true_range()
    df['sma50'] = SMAIndicator(df['Close'], window=50).sma_indicator()
    df['sma200'] = SMAIndicator(df['Close'], window=200).sma_indicator()
    return df.iloc[-1]

def get_ai_analysis(symbol, data):
    """Simulates 1000 agents via Gemini 1.5 Flash."""
    model = genai.GenerativeModel('gemini-1.5-flash')
    prompt = f"""
    You are the CIO of a Quant Firm managing 1,000 agents. Analyze:
    Symbol: {symbol} | Price: {data['Close']:.2f} | ADX: {data['adx']:.2f}
    RSI: {data['rsi']:.2f} | MACD Hist: {data['macd_diff']:.2f} | ATR: {data['atr']:.2f}
    SMA50: {data['sma50']:.2f} | SMA200: {data['sma200']:.2f}

    Agent Tasks:
    - Squad Trend: Check SMA Cross & ADX (>25 is strong).
    - Squad Volatility: Set SL at 1.5x ATR distance from Entry.
    - Squad Momentum: Confirm MACD & RSI alignment.

    Return ONLY a JSON object:
    {{
        "signal": "BUY/SELL/HOLD",
        "confidence": 0-100,
        "entry": price,
        "sl": price,
        "tp": price,
        "rationale": "one sentence"
    }}
    """
    try:
        response = model.generate_content(prompt)
        json_str = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(json_str)
    except:
        return None

def broadcast(msg_obj, name):
    """Sends the analysis to Telegram if confidence is high."""
    if not msg_obj or msg_obj['signal'] == "HOLD" or msg_obj['confidence'] < 70:
        return
    emoji = "🚀" if msg_obj['signal'] == "BUY" else "🔻"
    text = (
        f"{emoji} *{msg_obj['signal']} ALERT: {name}*\n"
        f"━━━━━━━━━━━━━━\n"
        f"📍 *Entry:* {msg_obj['entry']}\n"
        f"🛑 *Stop Loss:* {msg_obj['sl']}\n"
        f"🎯 *Target:* {msg_obj['tp']}\n"
        f"📊 *Confidence:* {msg_obj['confidence']}%\n"
        f"📝 *Note:* {msg_obj['rationale']}"
    )
    url = f"https://api.telegram.org/bot{os.getenv('TELEGRAM_BOT_TOKEN')}/sendMessage"
    requests.post(url, json={"chat_id": os.getenv("TELEGRAM_CHAT_ID"), "text": text, "parse_mode": "Markdown"})

def main():
    print("Bot sequence started...")
    while True:
        for name, ticker in SYMBOLS.items():
            try:
                df = yf.download(ticker, period="5d", interval=INTERVAL, progress=False)
                if len(df) < 50: continue
                data = get_advanced_indicators(df)
                analysis = get_ai_analysis(name, data)
                if analysis: broadcast(analysis, name)
            except Exception as e: print(f"Error: {e}")
        time.sleep(900)

if __name__ == "__main__":
    main()
