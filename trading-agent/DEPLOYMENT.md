# Deployment Guide for DigitalOcean

This guide walks you through deploying the Multi-Agent Trading System on a DigitalOcean Droplet for 24/7 operation.

## 🚨 CRITICAL SECURITY WARNING

**Before proceeding:**
1. **Revoke all API keys** you may have shared in chat logs
2. Generate **new API keys** from official sources
3. Never share credentials in public forums or chat

## Step 1: Create a DigitalOcean Droplet

1. Log in to [DigitalOcean](https://cloud.digitalocean.com/)
2. Click "Create" → "Droplets"
3. Choose:
   - **OS**: Ubuntu 24.04 LTS x64
   - **Plan**: Basic ($6/month recommended)
   - **Region**: Choose closest to Indian markets (Singapore or Bangalore if available)
4. Add SSH key (recommended) or use password
5. Click "Create Droplet"

## Step 2: Connect to Your Droplet

```bash
ssh root@YOUR_DROPLET_IP
```

## Step 3: Install System Dependencies

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install Python and tools
sudo apt install python3-pip python3-venv git nano curl -y
```

## Step 4: Set Up Project Directory

```bash
# Create project directory
mkdir -p ~/trading-agent
cd ~/trading-agent

# Copy your project files (from local machine)
# Option A: Use git clone if you have a repo
# git clone <your-repo-url> .

# Option B: Create files manually with nano
nano main.py
# Paste the code from main.py and save (Ctrl+X, Y, Enter)

nano .env
# Add your credentials (see Step 5)
```

## Step 5: Configure Environment Variables

```bash
nano .env
```

Add your **NEW** credentials:
```env
GEMINI_API_KEY=AIzaSy...YOUR_NEW_KEY
TELEGRAM_BOT_TOKEN=123456789:YOUR_NEW_BOT_TOKEN
TELEGRAM_CHAT_ID=1443052083
```

Save and exit (Ctrl+X, Y, Enter)

## Step 6: Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install google-generativeai yfinance ta python-dotenv requests
```

## Step 7: Test the Application

```bash
# Run once to test
python main.py
```

You should see:
- "🚀 Multi-Agent Trading System Started"
- Telegram startup message
- Market analysis logs

Press `Ctrl+C` to stop after testing.

## Step 8: Run as Background Service

### Option A: Using nohup (Simple)

```bash
nohup python main.py > bot.log 2>&1 &

# Check if running
ps aux | grep main.py

# View logs
tail -f bot.log
```

### Option B: Using systemd (Recommended for Production)

Create a service file:
```bash
sudo nano /etc/systemd/system/trading-agent.service
```

Add this content:
```ini
[Unit]
Description=Multi-Agent Trading System
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/trading-agent
Environment="PATH=/root/trading-agent/venv/bin"
ExecStart=/root/trading-agent/venv/bin/python /root/trading-agent/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable trading-agent
sudo systemctl start trading-agent

# Check status
sudo systemctl status trading-agent

# View logs
sudo journalctl -u trading-agent -f
```

## Step 9: Monitor Your Bot

```bash
# Check if running
sudo systemctl status trading-agent

# View real-time logs
sudo journalctl -u trading-agent -f

# Restart if needed
sudo systemctl restart trading-agent

# Stop
sudo systemctl stop trading-agent
```

## Step 10: Set Up Auto-Updates (Optional)

Create an update script:
```bash
nano ~/update-bot.sh
```

```bash
#!/bin/bash
cd ~/trading-agent
source venv/bin/activate
git pull origin main  # If using git
pip install -r requirements.txt  # If you have requirements.txt
sudo systemctl restart trading-agent
echo "Bot updated at $(date)" >> ~/update.log
```

Make it executable:
```bash
chmod +x ~/update-bot.sh
```

## 🔧 Troubleshooting

### Issue: "No space left on device"
```bash
# Check disk usage
df -h

# Clean up old files
sudo apt clean
sudo apt autoremove -y

# Remove old logs
sudo journalctl --vacuum-time=1d
```

### Issue: "Module not found"
```bash
source ~/trading-agent/venv/bin/activate
pip install google-generativeai yfinance ta python-dotenv requests
```

### Issue: Bot stops unexpectedly
```bash
# Check logs
sudo journalctl -u trading-agent -n 50

# Restart
sudo systemctl restart trading-agent
```

### Issue: No Telegram messages
1. Verify bot token is correct
2. Check chat ID is correct
3. Ensure bot is not blocked
4. Test with: `curl "https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates"`

## 📊 Expected Resource Usage

- **RAM**: ~200-400 MB
- **CPU**: Minimal (spikes during analysis)
- **Disk**: ~500 MB
- **Network**: Low (API calls every 15 minutes)

## 🔐 Security Checklist

- [ ] Used NEW API keys (not shared ones)
- [ ] `.env` file is not in any git repository
- [ ] SSH key authentication enabled (not password)
- [ ] Firewall configured (UFW)
- [ ] Regular system updates scheduled

```bash
# Enable firewall
sudo ufw allow ssh
sudo ufw enable

# Schedule updates
sudo apt install unattended-upgrades -y
```

## 💰 Cost Estimate

- **Droplet**: $6/month (Basic plan)
- **Gemini API**: Free tier available, then ~$0.000125 per 1K tokens
- **Telegram**: Free

**Total**: ~$6-10/month depending on usage

## 🎯 Next Steps

1. Monitor first few days of signals
2. Adjust confidence thresholds if needed
3. Consider adding more indices or cryptocurrencies
4. Set up alerts for system health

---

**Remember**: This is a trading tool, not a guaranteed profit machine. Always use proper risk management!
