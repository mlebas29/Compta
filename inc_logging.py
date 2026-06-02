#!/usr/bin/env python3
"""
Module centralisé de logging pour le système comptable
Gère l'affichage écran et l'écriture dans le journal

Usage:
    from inc_logging import Logger

    # Initialisation
    logger = Logger(
        script_name="mon_script",
        journal_file=JOURNAL_FILE,
        verbose=False,
        debug=False
    )

    # Messages inconditionnels (toujours affichés)
    logger.info("Message informatif")
    logger.warning("Avertissement")
    logger.error("Erreur")

    # Messages conditionnels
    logger.debug("Message de debug")      # Affiché si DEBUG=true
    logger.verbose("Message verbeux")     # Affiché si verbose=true

    # Journal seulement (sans formatage)
    logger.write_to_journal("Message brut pour journal")
"""

import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


class Logger:
    """Logger centralisé pour affichage et journal"""

    def __init__(self, script_name: str, journal_file: Optional[Path] = None,
                 verbose: bool = False, debug: bool = False):
        """
        Initialise le logger

        Args:
            script_name: Nom du script (utilisé dans le formatage)
            journal_file: Chemin vers le fichier journal (None = pas de journal)
            verbose: Mode verbeux (affiche les messages verbose)
            debug: Mode debug (affiche les messages debug)
        """
        self.script_name = script_name
        self.journal_file = Path(journal_file) if journal_file else None
        self.verbose_mode = verbose
        self.debug_mode = debug

        # Créer le répertoire du journal si nécessaire
        if self.journal_file and not self.journal_file.parent.exists():
            self.journal_file.parent.mkdir(parents=True, exist_ok=True)

    def _format_message(self, message: str, prefix: str = "✓") -> str:
        """
        Formate un message avec timestamp, script et préfixe

        Args:
            message: Message à formater
            prefix: Préfixe emoji (✓, ⚠️, ❌, 🛠)

        Returns:
            Message formaté
        """
        timestamp = datetime.now().strftime('%H:%M:%S')
        return f"{timestamp} {self.script_name} {prefix} {message}"

    def _log(self, message: str, prefix: str, display: bool, to_journal: bool, is_error: bool = False, simple: bool = False):
        """
        Fonction interne de logging

        Args:
            message: Message à logger
            prefix: Préfixe emoji
            display: Si True, affiche à l'écran
            to_journal: Si True, écrit dans le journal
            is_error: Si True, envoie vers stderr au lieu de stdout
            simple: Si True, affiche sans timestamp ni nom de script (juste prefix + message)
        """
        # Affichage écran
        if display:
            if simple:
                # Affichage simple : juste le message (pas de timestamp)
                display_msg = message
            else:
                # Affichage complet avec timestamp et script
                display_msg = self._format_message(message, prefix)

            output_stream = sys.stderr if is_error else sys.stdout
            print(display_msg, file=output_stream)

        # Écriture journal (toujours avec format complet)
        if to_journal and self.journal_file:
            try:
                formatted = self._format_message(message, prefix)
                with open(self.journal_file, 'a', encoding='utf-8') as f:
                    f.write(formatted + '\n')
            except Exception:
                pass  # Ne pas bloquer si erreur d'écriture

    def info(self, message: str):
        """Message informatif (toujours affiché, format simple sans timestamp)"""
        self._log(message, prefix="✓", display=True, to_journal=True, simple=True)

    def warning(self, message: str):
        """Avertissement (toujours affiché)"""
        self._log(message, prefix="⚠️", display=True, to_journal=True)

    def error(self, message: str):
        """Erreur (toujours affichée sur stderr)"""
        self._log(message, prefix="❌", display=True, to_journal=True, is_error=True)

    def alert(self, message: str):
        """Message d'alerte urgent (toujours affiché, visible via l'orchestrateur).

        Utilisé pour les notifications 2FA et autres messages nécessitant
        une action immédiate de l'utilisateur. Le marqueur 🔔 permet à
        l'orchestrateur de les afficher en temps réel même en mode non-verbose.
        """
        self._log(message, prefix="🔔", display=True, to_journal=True)

    def debug(self, message: str):
        """Message de debug (affiché seulement si DEBUG=true)"""
        self._log(message, prefix="🛠", display=self.debug_mode, to_journal=self.debug_mode)

    def verbose(self, message: str):
        """Message verbeux (affiché seulement si verbose=true)"""
        self._log(message, prefix="✓", display=self.verbose_mode, to_journal=True)

    def write_to_journal(self, message: str):
        """
        Écrit un message brut dans le journal (sans formatage, sans écran)
        Utile pour les headers de session, résumés, etc.

        Args:
            message: Message brut à écrire
        """
        if not self.journal_file:
            return

        try:
            with open(self.journal_file, 'a', encoding='utf-8') as f:
                f.write(message + '\n')
        except Exception:
            pass

    def with_prefix(self, name):
        """Crée un logger enfant qui préfixe [NAME] sur chaque message."""
        return PrefixLogger(self, f"[{name}]")


class PrefixLogger:
    """Logger enfant qui préfixe [NAME] sur chaque message."""

    def __init__(self, parent, prefix):
        self._parent = parent
        self._prefix = prefix

    def info(self, msg):
        self._parent.info(f"{self._prefix} {msg}")

    def warning(self, msg):
        self._parent.warning(f"{self._prefix} {msg}")

    def error(self, msg):
        self._parent.error(f"{self._prefix} {msg}")

    def verbose(self, msg):
        self._parent.verbose(f"{self._prefix} {msg}")

    def debug(self, msg):
        self._parent.debug(f"{self._prefix} {msg}")

    def alert(self, msg):
        self._parent.alert(f"{self._prefix} {msg}")

    def write_to_journal(self, msg):
        self._parent.write_to_journal(msg)
