# TradingBot v3.0

Advanced Multi-Market Signal Bot: **NSE + MCX Commodities + Crypto (24/7)** with **Gemini AI Why-This-Trade** explanations.

## Markets Covered

| Market | Symbols | Hours |
|---|---|---|
| NSE Indices | NIFTY 50, BANK NIFTY, MIDCAP 50 | 09:15–15:30 IST Mon-Fri |
| NSE F&O Stocks | 15 top stocks (RELIANCE, TCS, INFY...) | 09:15–15:30 IST Mon-Fri |
| MCX Commodities | GOLD, SILVER, CRUDE OIL, NAT GAS, COPPER, ZINC, ALUMINIUM | 09:00–23:30 IST Mon-Sat |
| Crypto | BTC, ETH, BNB, SOL, XRP, ADA, DOGE, MATIC | 24/7 Always Open |

**Total: 33 symbols scanned**

## Why-This-Trade Feature

Every signal includes a detailed AI explanation:
```
🧠 Why This Trade?
  • RSI: at 68, approaching overbought but still room to run
  • MACD: histogram turning positive for 3 candles confirming momentum
  • EMA: price above EMA9 and EMA21, both sloping up = bullish stack
  • ADX: at 28 confirms strong trend, +DI > -DI buyers in control
  • VOLUME: 2.1x above average = institutional accumulation
```

## Telegram Commands

| Command | Description |
|---|---|
| /start | Show all commands |
| /status | Uptime, all market counts, open/closed status |
| /signals | All signals fired today |
| /nse | NSE Indices + F&O Stocks |
| /stocks | NSE F&O Stocks only |
| /mcx | MCX Commodities list |
| /crypto | Crypto symbols list |
| /market | Live status of all 3 markets |
| /stop | Stop the bot |

## DigitalOcean Setup
```bash
ssh root@your_droplet_ip
cd /root/TradingBot
git pull && systemctl restart tradingbot
journalctl -u tradingbot -f
```

## .env Keys
```
GEMINI_API_KEY=your_gemini_key
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

## Disclaimer
For educational and research purposes only. Not financial advice.
