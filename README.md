# TradingBot v2.1

Advanced NSE signal bot: **Gemini AI** + **13 instruments** + **Telegram alerts & commands**.

## Features
- 11 technical indicators: RSI, MACD, ADX +/-DI, EMA9/21, SMA50/200, ATR, Bollinger Bands, Stochastic, CCI, Volume Ratio
- Gemini 1.5 Flash AI with 4-squad analysis (Trend, Momentum, Volatility, Volume)
- Per-symbol cooldown (60 min) — no duplicate spam
- Daily summary at 3:35 PM IST
- Market hours aware (NSE 9:15–15:30 IST, Mon–Fri)
- Interactive Telegram commands (locked to your chat_id only)
- Auto-restart via systemd

## Symbols Monitored (13)
**Indices:** NIFTY 50, BANK NIFTY, MIDCAP 50  
**F&O Stocks:** RELIANCE, TCS, INFOSYS, HDFC BANK, ICICI BANK, WIPRO, ADANIENT, TATAMOTORS, BAJFINANCE, AXISBANK

## Telegram Commands
| Command | Description |
|---|---|
| /start | Show all commands |
| /status | Uptime, signal count, market status |
| /signals | All signals fired today |
| /symbols | All 13 monitored symbols |
| /market | Is NSE open right now? |
| /stop | Stop the bot |

## DigitalOcean Setup (One Command)
```bash
ssh root@your_droplet_ip
curl -O https://raw.githubusercontent.com/geethu5166/TradingBot/main/setup_digitalocean.sh
bash setup_digitalocean.sh
```

Then add keys:
```bash
nano /root/TradingBot/.env
```

Add:
```
GEMINI_API_KEY=your_gemini_key_here
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

Start:
```bash
systemctl start tradingbot
journalctl -u tradingbot -f
```

## Useful Commands on Droplet
```bash
systemctl status tradingbot     # Check if running
systemctl restart tradingbot    # Restart after changes
journalctl -u tradingbot -f     # Live logs
tail -f /root/TradingBot/bot.log # Bot log file
git pull && systemctl restart tradingbot  # Update & restart
```

## .env Keys Reference
| Key | Where to get it |
|---|---|
| GEMINI_API_KEY | https://aistudio.google.com -> Get API Key |
| TELEGRAM_BOT_TOKEN | Telegram -> @BotFather -> /newbot |
| TELEGRAM_CHAT_ID | Telegram -> @userinfobot -> start it |

## Disclaimer
For educational and research purposes only. Not financial advice.
