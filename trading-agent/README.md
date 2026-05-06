# Multi-Agent Trading System for Indian Markets

An AI-powered trading agent that simulates **1,000 expert traders** across 5 specialized squads to generate actionable buy/sell signals for Indian stock indices.

## 🎯 Features

- **1000-Agent Simulation**: 5 squads (Technical, Quant, Macro, Sentiment, Risk) with 200 agents each
- **Indian Market Focus**: Nifty 50, Bank Nifty, Sensex, Midcap
- **Advanced Technical Analysis**: RSI, MACD, Bollinger Bands, Moving Averages
- **AI-Powered Decision Making**: Google Gemini integration for multi-agent debate
- **Telegram Alerts**: Real-time trading signals sent directly to your phone
- **Timeframe Detection**: Automatically identifies INTRADAY vs SHORT-TERM opportunities
- **Risk Management**: Built-in stop-loss and take-profit calculations

## 📋 Prerequisites

- Python 3.8+
- Google Gemini API Key
- Telegram Bot Token
- Telegram Chat ID

## 🚀 Installation

### 1. Clone/Setup Project
```bash
mkdir trading-agent
cd trading-agent
python3 -m venv venv
source venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install google-generativeai yfinance ta python-dotenv requests
```

### 3. Configure Environment Variables

Create a `.env` file:
```bash
cp .env.example .env
nano .env
```

Add your credentials:
```env
GEMINI_API_KEY=your_actual_gemini_api_key
TELEGRAM_BOT_TOKEN=your_actual_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

### 4. Run the Trading Agent
```bash
python main.py
```

## 📊 How It Works

1. **Data Collection**: Fetches real-time market data from Yahoo Finance
2. **Technical Analysis**: Calculates RSI, MACD, Bollinger Bands, SMAs
3. **Multi-Agent Debate**: 
   - Technical Squad analyzes chart patterns
   - Quant Squad runs statistical models
   - Macro Squad evaluates economic factors
   - Sentiment Squad processes news/social media
   - Risk Squad optimizes position sizing
4. **Consensus Decision**: Chief Investment Officer synthesizes all inputs
5. **Signal Generation**: Creates BUY/SELL/HOLD recommendation with entry/exit levels
6. **Telegram Alert**: Sends formatted signal to your phone

## 📱 Sample Telegram Output

```
🟢 MULTI-AGENT TRADING SIGNAL 🟢

📊 Asset: NIFTY50
🎯 Decision: BUY
⏱️ Timeframe: INTRADAY
💯 Confidence: 78%

📈 ENTRY ZONE:
   Min: 24150.00
   Max: 24180.00

🛑 STOP LOSS: 24100.00

💰 TAKE PROFIT:
   Target 1: 24250.00
   Target 2: 24320.00

🧠 SQUAD VOTES:
• Technical: BUY (85%)
• Quant: BUY (72%)
• Macro: HOLD (60%)
• Sentiment: BUY (80%)
• Risk: BUY (75%)

💡 Key Reasoning:
Strong bullish momentum with RSI breakout...

⚠️ Risk Warning: Global market volatility expected

🕒 Generated: 2024-01-15 10:30:00 IST
```

## ⚙️ Configuration

### Market Hours
By default, the system runs 24/7. To restrict to Indian market hours (9:15 AM - 3:30 PM IST), uncomment the time check in `main.py`:

```python
if 9 <= current_time.hour <= 15:  # Approx IST check
    # Run analysis
```

### Scan Interval
Default: Every 15 minutes
Modify in `main.py`: `time.sleep(900)` (900 seconds = 15 minutes)

## 🔒 Security Best Practices

- **NEVER** commit your `.env` file to Git
- Keep your API keys private
- Use environment variables in production
- Rotate keys periodically

## 🌐 Deployment on DigitalOcean

See detailed deployment guide in `DEPLOYMENT.md`

## ⚠️ Disclaimer

This software is for educational and research purposes only. 

- **No Financial Advice**: Not a substitute for professional financial advice
- **Market Risk**: Trading involves substantial risk of loss
- **No Guarantees**: Past performance does not guarantee future results
- **100% Accuracy Myth**: No trading system can achieve 100% accuracy

Always do your own research and consult with a qualified financial advisor before making investment decisions.

## 📄 License

MIT License - Feel free to modify and distribute

## 🤝 Support

For issues or questions, please check the logs:
```bash
tail -f bot.log
```
