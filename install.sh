#!/bin/bash
# EazyFlare — One-line installer
# Usage: curl -fsSL https://raw.githubusercontent.com/SchmitzWS/eazyflare/main/install.sh | bash
set -e

GREEN='\033[0;32m'
ORANGE='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${ORANGE}"
echo "  ███████╗ █████╗ ███████╗██╗   ██╗███████╗██╗      █████╗ ██████╗ ███████╗"
echo "  ██╔════╝██╔══██╗╚══███╔╝╚██╗ ██╔╝██╔════╝██║     ██╔══██╗██╔══██╗██╔════╝"
echo "  █████╗  ███████║  ███╔╝  ╚████╔╝ █████╗  ██║     ███████║██████╔╝█████╗  "
echo "  ██╔══╝  ██╔══██║ ███╔╝    ╚██╔╝  ██╔══╝  ██║     ██╔══██║██╔══██╗██╔══╝  "
echo "  ███████╗██║  ██║███████╗   ██║   ██║     ███████╗██║  ██║██║  ██║███████╗"
echo "  ╚══════╝╚═╝  ╚═╝╚══════╝   ╚═╝   ╚═╝     ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝"
echo -e "${NC}"
echo "  Cloudflare DNS Manager — Telegram Bot + Mini App"
echo "  https://github.com/SchmitzWS/eazyflare"
echo ""

INSTALL_DIR="/opt/eazyflare"

# 1. Install dependencies
echo -e "${GREEN}[1/6]${NC} Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip nginx certbot python3-certbot-nginx git > /dev/null 2>&1

# 2. Clone repo
echo -e "${GREEN}[2/6]${NC} Downloading EazyFlare..."
rm -rf $INSTALL_DIR
git clone --depth 1 https://github.com/SchmitzWS/eazyflare.git $INSTALL_DIR
cd $INSTALL_DIR

# 3. Install Python deps
echo -e "${GREEN}[3/6]${NC} Installing Python packages..."
pip3 install -r requirements.txt --break-system-packages -q

# 4. Get config from user
echo ""
echo -e "${ORANGE}━━━━ Configuration ━━━━${NC}"
echo ""

read -p "🤖 Telegram Bot Token (from @BotFather): " BOT_TOKEN
read -p "🌐 Your domain for webapp (e.g. eazyflare.yourdomain.com): " DOMAIN
read -p "☁️  Cloudflare Worker URL (e.g. https://cf-proxy.xxx.workers.dev): " WORKER_URL

# 5. Configure files
echo -e "${GREEN}[4/6]${NC} Configuring..."

# Set bot env
cat > $INSTALL_DIR/.env << EOF
BOT_TOKEN=$BOT_TOKEN
WEBAPP_URL=https://$DOMAIN
EOF

# Set worker URL in webapp
sed -i "s|var PROXY = \"\";|var PROXY = \"$WORKER_URL\";|g" $INSTALL_DIR/web/index.html

# 6. Setup Nginx
echo -e "${GREEN}[5/6]${NC} Setting up Nginx..."
cat > /etc/nginx/sites-available/eazyflare << EOF
server {
    listen 80;
    server_name $DOMAIN;
    root $INSTALL_DIR/web;
    index index.html;

    location / {
        try_files \$uri \$uri/ =404;
    }
}
EOF

ln -sf /etc/nginx/sites-available/eazyflare /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx

# 7. Setup systemd service
echo -e "${GREEN}[6/6]${NC} Setting up bot service..."
cat > /etc/systemd/system/eazyflare.service << EOF
[Unit]
Description=EazyFlare Telegram Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=/usr/bin/python3 $INSTALL_DIR/bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable eazyflare
systemctl start eazyflare

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  ✅ EazyFlare installed successfully!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  📊 Web App:   http://$DOMAIN"
echo -e "  🤖 Bot:       Running as systemd service"
echo ""
echo -e "  ${ORANGE}Next steps:${NC}"
echo -e "  1. Point your domain A record to this server's IP"
echo -e "  2. Run: ${GREEN}certbot --nginx -d $DOMAIN${NC}"
echo -e "  3. Deploy worker.js to Cloudflare Workers"
echo -e "  4. Open your Telegram bot and send /start"
echo ""
echo -e "  ${ORANGE}Manage:${NC}"
echo -e "  Status:  systemctl status eazyflare"
echo -e "  Logs:    journalctl -u eazyflare -f"
echo -e "  Restart: systemctl restart eazyflare"
echo ""
