#!/usr/bin/env bash
# ShowPace installer for a server (Ubuntu or Debian). Run it from inside the ShowPace folder:
#   sudo bash install.sh
# It installs Docker if it's missing, asks for your web address, then starts ShowPace with free HTTPS.
set -euo pipefail
cd "$(dirname "$0")"

say() { printf '\n\033[1;32m%s\033[0m\n' "$*"; }
stop() { printf '\n\033[1;31m%s\033[0m\n' "$*"; exit 1; }

if [ "$(id -u)" -ne 0 ] && ! docker info >/dev/null 2>&1; then
  stop "Run it with sudo in front:  sudo bash install.sh"
fi

if ! command -v docker >/dev/null 2>&1; then
  command -v curl >/dev/null 2>&1 || { apt-get update -qq && apt-get install -y -qq curl; }
  say "Installing Docker. This takes a minute or two."
  curl -fsSL https://get.docker.com | sh
fi
docker compose version >/dev/null 2>&1 || stop "Docker is installed but Docker Compose is missing. Run: sudo apt-get install -y docker-compose-plugin  then run this again."

DOMAIN="${1:-}"
if [ -z "$DOMAIN" ] && [ -f .env ]; then DOMAIN="$(sed -n 's/^DOMAIN=//p' .env)"; fi
while [ -z "$DOMAIN" ]; do
  read -rp "Your web address for ShowPace (like shows.example.com): " DOMAIN
done
DOMAIN="${DOMAIN#http://}"; DOMAIN="${DOMAIN#https://}"; DOMAIN="${DOMAIN%%/*}"
echo "DOMAIN=$DOMAIN" > .env

# The most common problem: the address doesn't point at this server yet, so HTTPS can't start
if command -v getent >/dev/null 2>&1 && command -v hostname >/dev/null 2>&1 && [ "$DOMAIN" != localhost ]; then
  POINTS_TO="$(getent ahostsv4 "$DOMAIN" | awk 'NR==1{print $1}')"
  if [ -z "$POINTS_TO" ]; then
    echo "Heads up: $DOMAIN doesn't point anywhere yet. Add an A record for it with this server's IP address."
  elif ! hostname -I 2>/dev/null | tr ' ' '\n' | grep -qx "$POINTS_TO"; then
    echo "Heads up: $DOMAIN points to $POINTS_TO. If that isn't this server, HTTPS won't work until you fix the A record."
  fi
fi

# Let web traffic in, if the firewall is on
if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
  ufw allow 80/tcp >/dev/null && ufw allow 443/tcp >/dev/null
fi

say "Starting ShowPace"
docker compose up -d --build

say "Waiting for it to answer at https://$DOMAIN"
for _ in $(seq 1 30); do
  if curl -fsS -o /dev/null --max-time 5 ${INSECURE:-} "https://$DOMAIN/api/brand" 2>/dev/null; then
    say "Done! Open https://$DOMAIN in your browser and create your admin login."
    exit 0
  fi
  sleep 4
done
echo
echo "ShowPace is running, but https://$DOMAIN isn't answering yet."
echo "Usually that means the address doesn't point at this server yet. Fix the A record, wait a few minutes, then open it."
echo "To see what's happening:  sudo docker compose logs caddy"
