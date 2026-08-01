"""Vocabulium — toutes les valeurs calibrables du jeu, au même endroit.

Le prototype vise le FEEL : ces constantes sont faites pour être bougées à la
main pendant les sessions de test. Le backend et le pipeline de données lisent
TOUS leurs paramètres ici — ne dupliquez pas de nombre magique ailleurs.
"""
from __future__ import annotations

from pathlib import Path

# --- Chemins ----------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"

# Artefact DÉPLOYABLE (~50 Mo) : uniquement les vecteurs des mots jouables, en
# float16, + la liste des mots et leur zipf. C'est ce qui tourne en prod (Railway)
# — pas de modèle 2,4 Go, pas de volume. Généré par tools/export_vectors.py.
VECTORS_NPY = DATA_DIR / "vectors.f16.npy"
VOCAB_JSON = DATA_DIR / "vocab.json"

# Modèle FastText complet (2M mots) — présent seulement en DEV local (Discoverix,
# LECTURE SEULE). Sert à (re)générer l'artefact et à calibrer le vocab en direct.
DISCOVERIX_ROOT = PROJECT_ROOT.parent / "Discoverix"
FASTTEXT_KV = DISCOVERIX_ROOT / "data" / "fasttext" / "cc.fr.300.2M.kv"

# --- Dictionnaire = LE MODÈLE, filtré par wordfreq (aucune base, aucun rebuild)
# Un mot est jouable s'il est dans le modèle FastText ET reconnu par wordfreq
# (zipf >= VOCAB_ZIPF_MIN). Ça couvre tout vrai mot FR du modèle, dérivations
# comprises (royalisme…). Le vocab est reconstruit en mémoire au démarrage (~3 s).
# VOCAB_ZIPF_MIN est LE curseur couverture/bruit : plus bas = plus de mots rares
# (et un peu de scories), plus haut = plus propre. Changement = redémarrer, pas
# de rebuild.
VOCAB_ZIPF_MIN = 2.0     # >= 2.0 -> ~83k mots (inclut royalisme à 2.13)
KV_SCAN = 600000         # on scanne le top-600k du modèle (freq-ordonné) ; au-delà zipf<2
MIN_WORD_LEN = 3         # on écarte les mots-outils courts (de, la, un…) et les ~340 scories de 2 lettres

# Exception au MIN_WORD_LEN : les rares vrais mots FR de 2 lettres (contenu, pas
# mots-outils). Sans ça "or" (métal, cos(or,argent)=0.47) serait injouable.
# Facile à étendre (notes de musique do/ré/mi/fa, etc.).
SHORT_WORDS = {"or", "os", "an", "if"}

# Filtre noms propres (natif : d'après le modèle, sans liste externe). Un mot est
# rejeté si sa forme Capitalisée est >= ce facteur plus fréquente que sa minuscule
# (rang de corpus). Les vrais noms propres (john/paris) sont à ratio 20-56 ; les
# mots communs qui sont AUSSI des prénoms (pierre/rose/olivier) restent < ~12, donc
# gardés. 15 = bon compromis (exclut les noms, épargne les ambigus).
PROPER_NOUN_RATIO = 15
REF_SIZE = 30000         # matrice de référence (top mots) pour le degré/spécificité au runtime

# --- Zones de proximité : un "sweet spot", ni trop loin ni trop proche ------
# La proximité est un PORTAIL, pas un bonus. Trop proche = quasi-synonyme = pont
# évident = peu de points (comme trop loin). Les vrais ponts vivent à ~0.35-0.55.
# < GRACE           : REJET (casse le combo)
# [GRACE, TAU[      : FAIBLE "trop loin"  (accepté, peu de points, combo figé)
# [TAU, SYNO[       : FORT                (plein score + combo) ← la zone qui paie
# >= SYNO           : FAIBLE "trop proche"(quasi-synonyme : peu de points, combo figé)
TAU_GRACE = 0.22        # portail généreux : admet les collocations faibles (nucléaire~réaction
#                         0.227) en zone faible — au prix d'un peu de bruit du même niveau
TAU = 0.30
SYNO = 0.62              # au-delà : quasi-synonyme (royaliste~royalistes 0.74, chat~chats 0.74)
WEAK_POINTS_FACTOR = 0.35  # un hop faible rapporte ~1/3 d'un hop fort équivalent

# Anti-dérivation : un mot qui partage une racine avec le précédent
# (rapide->rapidement, grand->grande, génie->génial) est un pont fainéant. On le
# traite comme un synonyme (faible, pas de combo) même si son cosinus est en zone
# forte. Règle : préfixe commun >= ROOT_MIN_PREFIX, ET les DEUX mots >= ROOT_MIN_LEN
# (sinon "port"/"porte" : le préfixe EST le mot court -> deux mots distincts), ET
# préfixe >= ROOT_FRAC du plus court (évite const-itution/const-ruction).
# Les dérivations de mots très courts (chat/chats) sont couvertes par SYNO (cos élevé).
ROOT_MIN_PREFIX = 4      # géni-e / géni-al partagent 4
ROOT_MIN_LEN = 5         # ... mais port(4)/porte épargnés (mot court == préfixe)
ROOT_FRAC = 0.6

# --- Fréquence (rareté) -----------------------------------------------------
# Zipf (wordfreq) : ~7 = ultra courant, ~2 = rare. rarete = plus rare -> plus haut.
# ZIPF_MIN bas (1.0) évite que tout le bas du vocab (zipf 2.0-2.5) sature à 1.0 :
# "nichon" (zipf 2.27) tombe à ~0.75 au lieu de 1.00. Limite de fond : la fréquence
# ÉCRITE surestime la rareté des mots tabous/argot (connus mais peu écrits) — seul
# un lexique de familiarité corrigerait vraiment ça.
ZIPF_MIN = 1.0           # zipf <= MIN  -> rarete = 1.0
ZIPF_MAX = 6.0           # zipf >= MAX  -> rarete = 0.0

# --- Poids de la formule de hop ---------------------------------------------
BASE = 100.0
WS = 1.5                 # poids de la rareté
WV = 0.9                 # poids de la vitesse (relevé : la vitesse pèse plus)
SPEED_TAU = 3.0          # vitesse = exp(-t/TAU) : décroît vite -> sépare nettement les hops rapides

# --- Combo (rééquilibré : qualité > longueur) -------------------------------
# Le combo ne monte plus d'un pas fixe : le gain dépend de la QUALITÉ (surprise)
# du hop -> gain = COMBO_STEP * (COMBO_FLOOR + surprise). Un pont banal fait à
# peine bouger le combo, un pont brillant le propulse. Et il est PLAFONNÉ, pour
# qu'une longue chaîne de mots faciles ne batte plus un enchaînement malin court.
COMBO_START = 1.0
COMBO_STEP = 0.18        # gain de base par hop fort
COMBO_FLOOR = 0.4        # part minimale du gain (même un hop sans surprise en donne un peu)
MULT_MAX = 4.0           # plafond du multiplicateur

# --- Jauge / fin de partie --------------------------------------------------
# La jauge remplace le timer plat : elle se vide vite et se recharge à chaque
# bon mot. Le run finit quand elle atteint 0. Le vrai risque du "push" : si elle
# se vide avec du pending non encaissé, ce pending est PERDU (mets True pour
# revenir à l'auto-encaissement doux de l'ancien MVP).
GAUGE_SECONDS = 15.0       # temps de vidage complet (plein -> vide) sans action
WEAK_REFILL = 0.45         # un hop faible remonte la jauge jusqu'à ce niveau max
KEEP_PENDING_ON_TIMEOUT = False

# --- Sélection du mot de départ ---------------------------------------------
# On tire le seed parmi les mots jouables d'une bande de fréquence moyenne :
# ni trop rares (imprononçables) ni mots-outils hyper courants.
SEED_ZIPF_MIN = 3.2
SEED_ZIPF_MAX = 5.6
