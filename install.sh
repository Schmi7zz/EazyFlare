#!/bin/bash
clear
echo -e "\e[36m=========================================\e[0m"
echo -e "\e[32m      🚀 EazyFlare Bot Installer       \e[0m"
echo -e "\e[36m=========================================\e[0m"

echo -e "\n\e[33m[+] Updating packages and installing dependencies...\e[0m"
sudo apt-get update -y
sudo apt-get install -y python3 python3-pip git

echo -e "\n\e[33m[+] Cloning EazyFlare repository...\e[0m"
git clone https://github.com/Schmi7zz/EazyFlare.git
cd EazyFlare || exit

echo -e "\n\e[33m[+] Installing Python requirements...\e[0m"
pip3 install python-telegram-bot requests

echo -e "\n\e[32m[✔] Installation Completed Successfully!\e[0m"
echo -e "\e[37m-------------------------------------------------\e[0m"
echo -e "Next steps:"
echo -e "1. Navigate to the folder: \e[36mcd EazyFlare\e[0m"
echo -e "2. Edit the config inside \e[36mbot.py\e[0m (Set BOT_TOKEN & WEBAPP_URL)"
echo -e "3. Run the bot: \e[36mpython3 bot.py\e[0m"
echo -e "\e[37m-------------------------------------------------\e[0m"