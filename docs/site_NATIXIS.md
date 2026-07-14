# Natixis (épargne salariale PEE) — collecte

> Source de vérité = le code : `cpt_fetch_NATIXIS.py` (collecte) et
> `cpt_format_NATIXIS.py` (parsing). Descriptif opérateur (GUI onglet Sites) =
> constante `DESCRIPTION` du fetch. Ci-dessous, seulement le « pourquoi » non déductible du code.

**En bref.** PEE, compte unique. Login sans 2FA classique (SMS/OTP) mais assistant
« appareil de confiance » à écarter. La collecte imprime **2 PDF** (positions + opérations).

## À savoir

- **Assistant « appareil de confiance »** (post-login, SPA Angular) : `_dismiss_trusted_device_interstitial()` le franchit en 2 écrans (« Plus tard » = ne pas enrôler, puis « Continuer »). Sans le 1er clic, la page reste sur l'IdP SAML (`/auth`) et la détection de session timeoute.
- **Sortie = 2 PDF, pas CSV** : le fetch imprime chaque page (CDP `printToPDF`, requis en headed) ; opérations, positions et solde sont extraits ensuite par pdfplumber. Les CSV ne sont qu'un secours legacy (collecte manuelle).
- **Arbitrages** : montant ramené à 0,00 (somme nulle) mais conservé **dans le libellé**, jamais en commentaire — trace sans fausser le solde.
- **Nombre de fonds dynamique** : dépend de l'allocation du salarié ; le parsing détecte chaque ligne de fonds, aucun nombre figé.
