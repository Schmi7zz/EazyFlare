#!/bin/bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}"
echo "  ╔═══════════════════════════════════╗"
echo "  ║       EazyFlare Installer         ║"
echo "  ║   Cloudflare Manager for Telegram ║"
echo "  ╚═══════════════════════════════════╝"
echo -e "${NC}"

REPO="https://raw.githubusercontent.com/Schmi7zz/EazyFlare/main"
DIR="/opt/eazyflare"

# Ask install method
echo -e "${YELLOW}روش نصب / Install method:${NC}"
echo "  1) 🐳 Docker (پیشنهادی / recommended)"
echo "  2) 📦 Systemd (بدون داکر / without Docker)"
read -p "انتخاب / Choose [1/2]: " METHOD
METHOD=${METHOD:-1}

# Get bot token
echo ""
read -p "🤖 Telegram Bot Token: " BOT_TOKEN
if [ -z "$BOT_TOKEN" ]; then
  echo -e "${RED}❌ Bot token is required${NC}"
  exit 1
fi

# Get webapp URL
echo ""
echo -e "${YELLOW}🌐 Webapp URL (اختیاری / optional):${NC}"
echo "   اگه نمی‌خوای مینی‌اپ داشته باشی Enter بزن"
echo "   Press Enter to skip mini app"
read -p "URL: " WEBAPP_URL
WEBAPP_URL=${WEBAPP_URL:-""}

# Create directory and download files
echo -e "\n${CYAN}📥 Downloading files...${NC}"
mkdir -p "$DIR"
cd "$DIR"

curl -fsSL "$REPO/bot.py" -o bot.py
curl -fsSL "$REPO/requirements.txt" -o requirements.txt
curl -fsSL "$REPO/worker.js" -o worker.js

if [ -n "$WEBAPP_URL" ]; then
  curl -fsSL "$REPO/webapp.html" -o webapp.html
fi

# Create .env
cat > .env << EOF
BOT_TOKEN=$BOT_TOKEN
WEBAPP_URL=$WEBAPP_URL
EOF

# Init users.json
[ -f users.json ] || echo '{"users":{},"cf_logins":{}}' > users.json

if [ "$METHOD" = "1" ]; then
  # ═══ Docker Install ═══
  echo -e "${CYAN}🐳 Docker install...${NC}"

  # Install Docker
  if ! command -v docker &>/dev/null; then
    echo -e "${YELLOW}📦 Installing Docker...${NC}"
    curl -fsSL https://get.docker.com | sh
  fi

  # Install Docker Compose
  if ! docker compose version &>/dev/null 2>&1; then
    echo -e "${YELLOW}📦 Installing Docker Compose...${NC}"
    apt-get update -qq && apt-get install -y -qq docker-compose-plugin 2>/dev/null || true
  fi

  # Download Docker files
  curl -fsSL "$REPO/Dockerfile" -o Dockerfile
  curl -fsSL "$REPO/docker-compose.yml" -o docker-compose.yml

  # Build and start
  docker compose down 2>/dev/null || true
  docker compose up -d --build

  echo -e "\n${GREEN}✅ EazyFlare deployed with Docker!${NC}"
  echo -e "📁 Directory: ${CYAN}$DIR${NC}"
  echo -e "🔧 Logs: ${CYAN}docker compose -f $DIR/docker-compose.yml logs -f${NC}"
  echo -e "🔄 Restart: ${CYAN}docker compose -f $DIR/docker-compose.yml restart${NC}"
  echo -e "🛑 Stop: ${CYAN}docker compose -f $DIR/docker-compose.yml down${NC}"

else
  # ═══ Systemd Install ═══
  echo -e "${CYAN}📦 Systemd install...${NC}"

  apt-get update -qq
  apt-get install -y -qq python3 python3-pip 2>/dev/null

  pip3 install -r requirements.txt --break-system-packages 2>/dev/null || pip3 install -r requirements.txt

  cat > /etc/systemd/system/eazyflare.service << EOF
[Unit]
Description=EazyFlare Telegram Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=$DIR
EnvironmentFile=$DIR/.env
ExecStart=/usr/bin/python3 $DIR/bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable eazyflare
  systemctl start eazyflare

  echo -e "\n${GREEN}✅ EazyFlare deployed with Systemd!${NC}"
  echo -e "📁 Directory: ${CYAN}$DIR${NC}"
  echo -e "🔧 Logs: ${CYAN}journalctl -u eazyflare -f${NC}"
  echo -e "🔄 Restart: ${CYAN}systemctl restart eazyflare${NC}"
  echo -e "🛑 Stop: ${CYAN}systemctl stop eazyflare${NC}"
fi

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  EazyFlare is running! 🚀${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "Made with ♡ by ${CYAN}Schmitz${NC} — t.me/SchmitzWS"
