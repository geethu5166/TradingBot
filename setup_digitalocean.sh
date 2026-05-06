#!/bin/bash
# TradingBot DigitalOcean Setup Script
# Run as root: bash setup_digitalocean.sh

set -e
echo "==================================================="
echo "  TradingBot v2 - DigitalOcean Setup"
echo "==================================================="

# Update system
apt-get update -y && apt-get upgrade -y
apt-get install -y python3 python3-pip python3-venv git curl nano

# Clone or update repo
if [ -d "/root/TradingBot" ]; then
    echo "Repo exists, pulling latest..."
    cd /root/TradingBot && git pull
else
    echo "Cloning repo..."
    git clone https://github.com/geethu5166/TradingBot.git /root/TradingBot
fi

cd /root/TradingBot

# Virtual environment
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Create .env from example if not exists
if [ ! -f .env ]; then
    cp .env.example .env
    echo ""
    echo ">>> IMPORTANT: Edit your .env file with real tokens!"
    echo "    nano /root/TradingBot/.env"
fi

# Install systemd service for Telegram bot
cp tradingbot.service /etc/systemd/system/tradingbot.service
systemctl daemon-reload
systemctl enable tradingbot
systemctl restart tradingbot

echo ""
echo "==================================================="
echo "  Setup Complete!"
echo "==================================================="
echo ""
echo "Bot service status:"
systemctl status tradingbot --no-pager
echo ""
echo "Useful commands:"
echo "  View logs:     journalctl -u tradingbot -f"
echo "  Restart bot:   systemctl restart tradingbot"
echo "  Stop bot:      systemctl stop tradingbot"
echo "  Edit config:   nano /root/TradingBot/.env"
echo ""
echo "Test your bot by typing /help in Telegram!"
