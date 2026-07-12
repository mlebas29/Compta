#!/usr/bin/env bash
# install_xmr_wallet_rpc.sh — provisionne monero-wallet-rpc en service systemd.
#
# À lancer SUR la machine serveur (hôte toujours allumé qui fait tourner monerod),
# par l'utilisateur propriétaire de monerod / des wallets :
#     bash install_xmr_wallet_rpc.sh
#
# Ce qu'il fait :
#  - localise le binaire monero-wallet-rpc (même tarball que monerod)
#  - lit le login RPC de monerod depuis ~/.bitmonero/monerod.conf (jamais affiché)
#  - génère un login RPC dédié pour wallet-rpc
#  - écrit ~/.config/monero-wallet-rpc.conf (chmod 600) : wallet-dir, daemon-login, rpc-login
#  - installe + démarre le service systemd (sudo demandé)
#  - AFFICHE le login RPC généré → à ajouter dans config_credentials.md.gpg côté poste
#
# Sécurité : wallet-rpc est bindé sur 127.0.0.1 (jamais exposé) ; le poste y accède
# par tunnel SSH. Les .keys restent chiffrées (le mot de passe wallet n'est PAS stocké
# ici : il est envoyé par le poste à open_wallet via le tunnel).
set -euo pipefail

CONF_DIR="$HOME/.config"
CONF="$CONF_DIR/monero-wallet-rpc.conf"
WALLET_DIR="$HOME/Monero/wallets"
MONEROD_CONF="$HOME/.bitmonero/monerod.conf"
RPC_PORT=18083
UNIT=/etc/systemd/system/monero-wallet-rpc.service

# --- binaire wallet-rpc (version-robuste) ---
BIN=$(ls -1 "$HOME"/Applications/monero-x86_64-linux-gnu-*/monero-wallet-rpc 2>/dev/null | sort | tail -1 || true)
[[ -x "$BIN" ]] || { echo "✗ monero-wallet-rpc introuvable sous ~/Applications/monero-*"; exit 1; }
echo "✓ binaire : $BIN"

# --- login monerod (lu localement, jamais affiché) ---
DAEMON_LOGIN=$(grep -E '^rpc-login=' "$MONEROD_CONF" | head -1 | cut -d= -f2-)
[[ -n "$DAEMON_LOGIN" ]] || { echo "✗ rpc-login absent de $MONEROD_CONF"; exit 1; }

# --- wallets présents ? ---
[[ -d "$WALLET_DIR" ]] || { echo "✗ $WALLET_DIR absent (déposer les wallets d'abord)"; exit 1; }

# --- login RPC dédié wallet-rpc ---
RPC_USER="walletrpc"
RPC_PASS=$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-24)

# --- conf (chmod 600) ---
mkdir -p "$CONF_DIR"
umask 077
cat > "$CONF" <<EOF
wallet-dir=$WALLET_DIR
daemon-address=127.0.0.1:18081
daemon-login=$DAEMON_LOGIN
trusted-daemon=1
rpc-bind-ip=127.0.0.1
rpc-bind-port=$RPC_PORT
rpc-login=$RPC_USER:$RPC_PASS
log-file=$HOME/.bitmonero/monero-wallet-rpc.log
log-level=0
EOF
chmod 600 "$CONF"
echo "✓ conf écrite : $CONF (chmod 600)"

# --- unit systemd ---
TMP_UNIT=$(mktemp)
cat > "$TMP_UNIT" <<EOF
[Unit]
Description=Monero Wallet RPC (lecture comptable des wallets)
After=network.target monerod.service
Wants=monerod.service

[Service]
Type=simple
User=$USER
Group=$USER
ExecStart=$BIN --config-file=$CONF
Restart=always
RestartSec=30
NoNewPrivileges=true
LimitNOFILE=8192

[Install]
WantedBy=multi-user.target
EOF

echo "→ installation du service (sudo) …"
sudo cp "$TMP_UNIT" "$UNIT"
rm -f "$TMP_UNIT"
sudo systemctl daemon-reload
sudo systemctl enable --now monero-wallet-rpc.service
sleep 3

echo
echo "=== état service ==="
systemctl --no-pager --full status monero-wallet-rpc.service | head -6 || true
echo "=== écoute 127.0.0.1:$RPC_PORT ? ==="
ss -ltn | grep ":$RPC_PORT" || echo "PAS en écoute (voir: journalctl -u monero-wallet-rpc -n 30)"

echo
echo "############################################################"
echo "#  À AJOUTER dans config_credentials.md.gpg (côté poste) : "
echo "#                                                          "
echo "#     | SiWaRpc-M | $RPC_USER | $RPC_PASS |"
echo "#                                                          "
echo "#  (l'ID SiWaRpc-M doit matcher [XMR] wallet_rpc_credential_id)"
echo "############################################################"
