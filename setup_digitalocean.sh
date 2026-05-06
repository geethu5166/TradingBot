#!/bin/bash
# TradingBot v2.1 - DigitalOcean Ubuntu 22.04 One-Command Setup
# Run as root: bash setup_digitalocean.sh
set -e

echo ""
echo "======================================="
echo "  TradingBot v2.1 - DigitalOcean Setup"
echo "======================================="
echo ""

echo "[1/8] Stopping & removing any old bot..."
systemctl stop tradingbot 2>/dev/null || true
systemctl disable tradingbot 2>/dev/null || true
rm -f /etc/systemd/system/tradingbot.service
rm -rf /root/TradingBot
systemctl daemon-reload
echo "     Done."

echo "[2/8] System update..."
apt-get update -y && apt-get upgrade -y
apt-get install -y python3 python3-pip python3-venv git tzdata curl
echo "     Done."

echo "[3/8] Setting timezone to IST..."
timedatectl set-timezone Asia/Kolkata
echo "     Timezone: $(timedatectl | grep 'Time zone')"

echo "[4/8] Cloning repo from GitHub..."
git clone https://github.com/geethu5166/TradingBot.git /root/TradingBot
echo "     Done."

echo "[5/8] Creating Python venv & installing packages..."
cd /root/TradingBot
python3 -m venv venv
venv/bin/pip install --upgrade pip --quiet
venv/bin/pip install -r requirements.txt --quiet
echo "     Done."

echo "[6/8] Setting up .env file..."
if [ ! -f "/root/TradingBot/.env" ]; then
    cp /root/TradingBot/.env.example /root/TradingBot/.env
    echo ""
    echo "  ╔══════════════════════════════════════════╗"
    echo "  ║  IMPORTANT: Add your API keys to .env!  ║"
    echo "  ╚══════════════════════════════════════════╝"
    echo ""
    echo "  Run this command to edit:"
    echo "  nano /root/TradingBot/.env"
    echo ""
    echo "  Add these 3 values:"
    echo "  GEMINI_API_KEY=your_gemini_key"
    echo "  TELEGRAM_BOT_TOKEN=your_bot_token"
    echo "  TELEGRAM_CHAT_ID=your_chat_id"
    echo ""
else
    echo "     .env already exists, skipping."
fi

echo "[7/8] Installing systemd service..."
cp /root/TradingBot/tradingbot.service /etc/systemd/system/tradingbot.service
systemctl daemon-reload
systemctl enable tradingbot
echo "     Service enabled."

echo "[8/8] Setup complete!"
echo ""
echo "  ┌─────────────────────────────────────────────┐"
echo "  │  NEXT STEPS:                                │"
echo "  │                                             │"
echo "  │  1. Add your API keys:                      │"
echo "  │     nano /root/TradingBot/.env              │"
echo "  │                                             │"
echo "  │  2. Start the bot:                          │"
echo "  │     systemctl start tradingbot              │"
echo "  │                                             │"
echo "  │  3. Watch live logs:                        │"
echo "  │     journalctl -u tradingbot -f             │"
echo "  │                                             │"
echo "  │  Telegram commands: /start /status          │"
echo "  │                     /signals /symbols       │"
echo "  │                     /market /stop           │"
echo "  └─────────────────────────────────────────────┘"
echo ""
