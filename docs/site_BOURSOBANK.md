# BoursoBank — collecte

> Source de vérité = le code : `cpt_fetch_BOURSOBANK.py` (collecte) + `cpt_format_BOURSOBANK.py` (format). Procédure utilisateur (2FA, repli) = `DESCRIPTION`, GUI onglet Sites.

**En bref :** login automatique (clavier virtuel décodé par OCR), export CSV des comptes (chèque, livret, portefeuille titres) + PDF des soldes, reformatés au schéma standard 9 champs.

## À savoir (non évident)

- **Clavier virtuel = OCR hybride.** L'OCR confond des chiffres (4/7, 1/4, 2/8) ; ce sont les **lettres du clavier téléphonique** (GHI→4, PQRS→7…) qui font foi pour 2-9. Les touches 0 et 1 (sans lettres) sont départagées par densité de pixels.
- **Plafond 2 tentatives de login.** BoursoBank bloque le compte 15 min après 3 échecs d'identification consécutifs — le script s'arrête avant.
- **2FA = attente passive.** Sur nouvel appareil, ne pas naviguer pendant la validation mobile : toute navigation relance la boucle de sécurisation.
- **Garde-fou HTML.** Session expirée / mauvais formulaire → BoursoBank répond HTTP 200 avec une page HTML au lieu du CSV ; elle est refusée (sinon `KeyError` cryptique au format). Le champ `accountbalance` des CSV est obsolète : les soldes viennent des PDF.
</content>
</invoke>
