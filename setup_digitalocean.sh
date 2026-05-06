#!/bin/bash
# TradingBot v2 — DigitalOcean Ubuntu 22.04 Setup Script
# Run as root: bash setup_digitalocean.sh
set -e

echo '=== [1/7] System update ==='
apt-get update && apt-get upgrade -y
apt-get install -y python3 python3-pip python3-venv git tzdata

echo '=== [2/7] Set timezone to IST ==='
timedatectl set-timezone Asia/Kolkata

echo '=== [3/7] Clone / update repo ==='
if [ -d "/root/TradingBot" ]; then
    cd /root/TradingBot && git pull
else
    git clone https://github.com/geethu5166/TradingBot.git /root/TradingBot
fi

echo '=== [4/7] Python venv and dependencies ==='
cd /root/TradingBot
python3 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt

echo '=== [5/7] Setup .env ==='
if [ ! -f "/root/TradingBot/.env" ]; then
    cp /root/TradingBot/.env.example /root/TradingBot/.env
    echo ''
    echo '>>> IMPORTANT: Edit /root/TradingBot/.env with your API keys! <<<'
    echo '>>> Run: nano /root/TradingBot/.env'
    echo ''
fi

echo '=== [6/7] Install systemd service ==='
cp /root/TradingBot/tradingbot.service /etc/systemd/system/tradingbot.service
systemctl daemon-reload
systemctl enable tradingbot
systemctl start tradingbot

echo '=== [7/7] Done! ==='
echo ''
echo 'Useful commands:'
echo '  View live logs:    journalctl -u tradingbot -f'
echo '  View bot.log:      tail -f /root/TradingBot/bot.log'
echo '  Stop bot:          systemctl stop tradingbot'
echo '  Restart bot:       systemctl restart tradingbot'
echo '  Check status:      systemctl status tradingbot'
