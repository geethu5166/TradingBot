# TradingBot v2

Advanced NSE index signal bot powered by **Gemini AI** + **multi-indicator analysis** with real-time **Telegram alerts**.

## Features
- 11 technical indicators: RSI, MACD, ADX +/-DI, EMA9/20, SMA50/200, ATR, Bollinger Bands, Stochastic, CCI, OBV
- Gemini 1.5 Flash AI with 5-squad analysis (Trend, Momentum, Volatility, Volume, Risk)
- Dual targets (TP1 and TP2) with R:R filter — only alerts if R:R >= 1.5
- Market hours aware — skips scanning outside NSE hours (9:15-15:30 IST, Mon-Fri)
- Heartbeat ping — Telegram health check every 6 hours
- Auto-restart via systemd service
- Structured logging to console and bot.log
- Env-configurable: interval, confidence threshold, sleep time

## Symbols Monitored
- NIFTY 50 (^NSEI)
- BANK NIFTY (^NSEBANK)
- MIDCAP 50 (^NSEMDCP50)
- SENSEX (^BSESN)
- FINNIFTY (^CNXFIN)

## Quick Start (DigitalOcean Ubuntu 22.04)

```bash
ssh root@your_droplet_ip
curl -O https://raw.githubusercontent.com/geethu5166/TradingBot/main/setup_digitalocean.sh
bash setup_digitalocean.sh
nano /root/TradingBot/.env   # add your keys
systemctl restart tradingbot
journalctl -u tradingbot -f
```

## .env Configuration
```
GEMINI_API_KEY=your_gemini_key
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
INTERVAL=15m
SLEEP_SECONDS=900
CONFIDENCE_THRESHOLD=70
```

## Disclaimer
For educational and research purposes only. Not financial advice.
