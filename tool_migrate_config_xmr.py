#!/usr/bin/env python3
"""
tool_migrate_config_xmr.py — migration de schéma config [XMR].

Collecte locale (monero-wallet-cli + monerod local) → nœud DISTANT (monero-wallet-rpc).
Migration carte-décrite (upgrade_map.json, action v5.7.0). Aucune valeur n'est
auto-migrable (l'architecture change) : on remet le bloc [XMR] au nouveau schéma en
PRÉSERVANT `credential_id` (mot de passe wallet, toujours utile) et `max_days_back`,
puis on DÉSACTIVE le site (retrait de [sites] enabled). La saisie des nouveaux
paramètres (hôte SSH wallet-rpc) + la (re)création du credential GPG du login RPC sont
une action de configuration MANUELLE (GUI), hors chemin d'upgrade — le disable la force.

Auto-gated + idempotent : déclencheur = clé héritée `wallet_cli_dir`. No-op si déjà
migré → un ré-`enable` ultérieur par l'utilisateur n'est jamais re-désactivé.
Édition ligne-à-ligne (préserve les commentaires des autres sections, pas de dump
configparser qui les écraserait — même doctrine que inc_install.normalize_config).

Usage: tool_migrate_config_xmr.py [config.ini]   (défaut: <base_dir>/config.ini)
"""

import re
import sys
from pathlib import Path

SENTINEL = 'wallet_cli_dir'  # clé héritée présente uniquement dans l'ancien schéma [XMR]

# Nouveau bloc [XMR] (schéma nœud distant). {cred}/{days} préservés de l'ancien.
NEW_BLOCK = """\
[XMR]
name = Monero Wallets
dossier = XMR
# Collecte via un monero-wallet-rpc DISTANT (cf. Compta_xmr.md).
# Cible SSH du serveur hébergeant wallet-rpc (clé SSH non-interactive requise) :
wallet_rpc_ssh_host = user@monero-host.example.lan
# Port du wallet-rpc côté serveur (bindé localhost là-bas) + port local du tunnel SSH
wallet_rpc_port = 18083
wallet_rpc_local_port = 28083
# Login RPC du wallet-rpc (GPG) — format : | SiWaRpc-M | username | password |
wallet_rpc_credential_id = SiWaRpc-M
# Mot de passe du wallet (GPG) — envoyé à open_wallet via le tunnel chiffré
credential_id = {cred}
# Fenêtre d'historique des opérations + délais (secondes)
max_days_back = {days}
refresh_timeout = 300
tunnel_timeout = 15"""


def migrate(config_path):
    """Migre le bloc [XMR] en place. Retourne True si une migration a eu lieu."""
    path = Path(config_path)
    if not path.exists():
        return False
    lines = path.read_text(encoding='utf-8').split('\n')

    # Localiser la section [XMR]
    xmr_i = next((i for i, l in enumerate(lines) if re.match(r'\s*\[XMR\]\s*$', l)), None)
    if xmr_i is None:
        return False

    # Fin du bloc = 1ʳᵉ ligne vide OU section suivante (les commentaires précédant la
    # section suivante lui appartiennent → on s'arrête à la ligne vide séparatrice).
    j = xmr_i + 1
    while j < len(lines) and not re.match(r'\s*$', lines[j]) and not re.match(r'\s*\[', lines[j]):
        j += 1
    block = lines[xmr_i:j]

    # Gate : déclencheur présent (ancien schéma) ?
    if not any(re.match(rf'\s*{SENTINEL}\s*=', l) for l in block):
        return False

    # Préserver credential_id (mot de passe wallet) et max_days_back
    def grab(key, default):
        for l in block:
            if l.lstrip().startswith('#'):
                continue
            m = re.match(rf'\s*{key}\s*=\s*(.*?)\s*$', l)
            if m:
                return m.group(1) or default
        return default

    cred = grab('credential_id', 'CrMo-M')
    days = grab('max_days_back', '90')

    new_block = NEW_BLOCK.format(cred=cred, days=days).split('\n')
    lines = lines[:xmr_i] + new_block + lines[j:]

    # Désactiver XMR dans [sites] enabled (force la reconfiguration manuelle en GUI)
    for i, l in enumerate(lines):
        if re.match(r'\s*enabled\s*=', l) and not l.lstrip().startswith('#') and 'XMR' in l:
            val = l.split('=', 1)[1]
            sites = [s.strip() for s in val.split(',') if s.strip() and s.strip() != 'XMR']
            lines[i] = 'enabled = ' + ','.join(sites)
            break

    path.write_text('\n'.join(lines), encoding='utf-8')
    return True


def main():
    if len(sys.argv) > 1:
        config_path = Path(sys.argv[1])
    else:
        import inc_mode
        config_path = inc_mode.get_base_dir() / 'config.ini'

    if migrate(config_path):
        print(f'✓ [XMR] migré vers nœud distant (wallet-rpc) + site désactivé')
        print(f'⚠ XMR : reconfigurer le site dans la GUI (hôte SSH wallet-rpc) ET')
        print(f'  (re)créer le credential GPG « SiWaRpc-M » — cf. Compta_xmr.md')
    else:
        print(f'✓ [XMR] config déjà au schéma nœud distant (rien à migrer)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
