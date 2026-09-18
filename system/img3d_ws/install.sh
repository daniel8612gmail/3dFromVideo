#!/bin/bash

set -e

echo "=========================================="
echo "   Instalator Image 3D WebSocket Service"
echo "=========================================="
echo

# --------------------------------------------------
# Sprawdzenie root
# --------------------------------------------------

if [ "$EUID" -ne 0 ]; then
    echo "Uruchom instalator jako root:"
    echo
    echo "  sudo ./install.sh"
    exit 1
fi

# --------------------------------------------------
# Katalog instalacyjny
# --------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Katalog instalacyjny:"
echo "  $SCRIPT_DIR"
echo

if [ ! -f "$SCRIPT_DIR/server.js" ]; then
    echo "BŁĄD: Nie znaleziono:"
    echo "  $SCRIPT_DIR/server.js"
    echo
    echo "Umieść install.sh obok server.js."
    exit 1
fi

# --------------------------------------------------
# Node.js
# --------------------------------------------------

NODE_BIN="$(command -v node || true)"
NPM_BIN="$(command -v npm || true)"

if [ -z "$NODE_BIN" ]; then
    echo "BŁĄD: Nie znaleziono Node.js."
    echo "Zainstaluj Node.js i uruchom instalator ponownie."
    exit 1
fi

if [ -z "$NPM_BIN" ]; then
    echo "BŁĄD: Nie znaleziono npm."
    exit 1
fi

echo "Node.js:"
"$NODE_BIN" --version

echo "npm:"
"$NPM_BIN" --version

echo

# --------------------------------------------------
# Katalog data
# --------------------------------------------------

DEFAULT_DATA_DIR="/var/www/html/data"

read -r -p "Podaj pełną ścieżkę do katalogu data [${DEFAULT_DATA_DIR}]: " DATA_DIR
DATA_DIR="${DATA_DIR:-$DEFAULT_DATA_DIR}"
DATA_DIR="$(realpath -m "$DATA_DIR")"

echo
echo "Katalog danych:"
echo "  $DATA_DIR"
echo

# --------------------------------------------------
# Port Node
# --------------------------------------------------

DEFAULT_PORT="8443"

read -r -p "Port lokalnego WebSocket [${DEFAULT_PORT}]: " PORT
PORT="${PORT:-$DEFAULT_PORT}"

# --------------------------------------------------
# Użytkownik usługi
# --------------------------------------------------

DEFAULT_SERVICE_USER="www-data"

read -r -p "Użytkownik usługi [${DEFAULT_SERVICE_USER}]: " SERVICE_USER
SERVICE_USER="${SERVICE_USER:-$DEFAULT_SERVICE_USER}"

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
    echo
    echo "BŁĄD: Użytkownik '$SERVICE_USER' nie istnieje."
    exit 1
fi

SERVICE_GROUP="$(id -gn "$SERVICE_USER")"

# --------------------------------------------------
# Agent
# --------------------------------------------------

DEFAULT_AGENT_ID="agent-01"

echo
echo "=== Konfiguracja pierwszego agenta ==="
echo

read -r -p "ID agenta [${DEFAULT_AGENT_ID}]: " AGENT_ID
AGENT_ID="${AGENT_ID:-$DEFAULT_AGENT_ID}"

read -r -s -p "Token agenta (Enter = wygeneruj automatycznie): " AGENT_TOKEN
echo

if [ -z "$AGENT_TOKEN" ]; then

    if command -v openssl >/dev/null 2>&1; then
        AGENT_TOKEN="$(openssl rand -hex 32)"
    else
        echo "BŁĄD: openssl nie jest zainstalowany."
        exit 1
    fi

    echo
    echo "Wygenerowany token agenta:"
    echo
    echo "$AGENT_TOKEN"
    echo
fi

# --------------------------------------------------
# package.json
# --------------------------------------------------

if [ ! -f "$SCRIPT_DIR/package.json" ]; then

    echo "Tworzenie package.json..."

    cat > "$SCRIPT_DIR/package.json" <<'EOF'
{
  "name": "img3d-ws",
  "version": "1.0.0",
  "private": true,
  "main": "server.js",
  "dependencies": {
    "chokidar": "^4.0.0",
    "dotenv": "^16.4.0",
    "ws": "^8.18.0"
  }
}
EOF

fi

# --------------------------------------------------
# npm install
# --------------------------------------------------

echo
echo "Instalowanie zależności Node.js..."

cd "$SCRIPT_DIR"

"$NPM_BIN" install

# --------------------------------------------------
# .env
# --------------------------------------------------

echo
echo "Tworzenie pliku .env..."

cat > "$SCRIPT_DIR/.env" <<EOF
DATA_DIR=$DATA_DIR
PORT=$PORT
AGENTS_FILE=$SCRIPT_DIR/agents.json
EOF

chmod 600 "$SCRIPT_DIR/.env"

# --------------------------------------------------
# agents.json
# --------------------------------------------------

echo
echo "Tworzenie listy autoryzowanych agentów..."

cat > "$SCRIPT_DIR/agents.json" <<EOF
{
    "agents": {
        "$AGENT_ID": {
            "token": "$AGENT_TOKEN"
        }
    }
}
EOF

chmod 600 "$SCRIPT_DIR/agents.json"

# --------------------------------------------------
# systemStatus.json
# --------------------------------------------------

mkdir -p "$DATA_DIR"

if [ ! -f "$DATA_DIR/systemStatus.json" ]; then

    echo "Tworzenie systemStatus.json..."

    cat > "$DATA_DIR/systemStatus.json" <<'EOF'
{
    "lastCleanup": null
}
EOF

fi

# --------------------------------------------------
# Uprawnienia
# --------------------------------------------------

echo
echo "Ustawianie uprawnień..."

chown -R "$SERVICE_USER:$SERVICE_GROUP" "$DATA_DIR"

# Pliki zawierające tokeny tylko dla użytkownika usługi
chown "$SERVICE_USER:$SERVICE_GROUP" "$SCRIPT_DIR/.env"
chown "$SERVICE_USER:$SERVICE_GROUP" "$SCRIPT_DIR/agents.json"

chmod 600 "$SCRIPT_DIR/.env"
chmod 600 "$SCRIPT_DIR/agents.json"

# --------------------------------------------------
# systemd
# --------------------------------------------------

SERVICE_FILE="/etc/systemd/system/img3d-ws.service"

echo
echo "Tworzenie usługi systemd:"
echo "  $SERVICE_FILE"

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Image 3D WebSocket Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple

User=$SERVICE_USER
Group=$SERVICE_GROUP

WorkingDirectory=$SCRIPT_DIR

ExecStart=$NODE_BIN $SCRIPT_DIR/server.js

Restart=always
RestartSec=5

Environment=NODE_ENV=production

StandardOutput=journal
StandardError=journal

NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF

# --------------------------------------------------
# Uruchomienie
# --------------------------------------------------

echo
echo "Przeładowanie konfiguracji systemd..."

systemctl daemon-reload

echo "Włączanie usługi przy starcie systemu..."

systemctl enable img3d-ws

echo "Uruchamianie usługi..."

systemctl restart img3d-ws

sleep 2

# --------------------------------------------------
# Status
# --------------------------------------------------

echo
echo "=========================================="

if systemctl is-active --quiet img3d-ws; then

    echo " INSTALACJA ZAKOŃCZONA POMYŚLNIE"
    echo "=========================================="
    echo
    echo "Node.js działa jako usługa systemowa."
    echo
    echo "Lokalny WebSocket:"
    echo "  ws://127.0.0.1:$PORT"
    echo
    echo "TLS/WSS:"
    echo "  obsługiwane przez Apache/Nginx"
    echo
    echo "Autoryzowany agent:"
    echo "  $AGENT_ID"
    echo
    echo "Konfiguracja agentów:"
    echo "  $SCRIPT_DIR/agents.json"
    echo
    echo "Katalog danych:"
    echo "  $DATA_DIR"
    echo
    echo "Katalog aplikacji:"
    echo "  $SCRIPT_DIR"
    echo
    echo "Przydatne polecenia:"
    echo
    echo "  systemctl status img3d-ws"
    echo "  systemctl restart img3d-ws"
    echo "  systemctl stop img3d-ws"
    echo "  journalctl -u img3d-ws -f"
    echo

else

    echo " BŁĄD: Usługa nie uruchomiła się."
    echo "=========================================="
    echo
    echo "Sprawdź:"
    echo
    echo "  systemctl status img3d-ws"
    echo
    echo "oraz:"
    echo
    echo "  journalctl -u img3d-ws -n 100 --no-pager"
    echo

    exit 1

fi
