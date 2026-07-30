# Vocabulium

Prototype jetable d'un jeu de **chaînage sémantique** en score-attack.

Un mot de départ quotidien (le même pour tous). Le joueur enchaîne des mots,
chacun devant être proche du **précédent** (pas du mot de départ). Il trace sa
propre ligne et score en enchaînant vite et en trouvant des ponts malins. Jeu de
style/flow (façon Tony Hawk), pas un puzzle : pas de mot cible.

C'est un proto : pas d'auth, pas de DB utilisateurs, pas de Docker. Le serveur est
**stateless** (le combo, le pending, le timer et les mots joués vivent côté client).

## Ce qu'il réutilise de Discoverix (LECTURE SEULE)

- `../Discoverix/data/fasttext/cc.fr.300.2M.kv` — vecteurs FastText (gensim),
  chargés en mmap. **C'est le dictionnaire ET la mesure de proximité** (voir
  Architecture). On ne réimporte pas le package Discoverix, pour rester découplé.
- `../Discoverix/.venv` — interpréteur qui contient déjà gensim/numpy/wordfreq/
  fastapi/uvicorn. On l'emprunte **sans jamais rien y installer ni modifier**.

Rien n'est écrit ni modifié dans Discoverix.

## Lancer

```bash
# Serveur (emprunte le venv de Discoverix). Aucune étape de build : le vocab est
# reconstruit en mémoire au démarrage (~4 s) depuis le modèle.
../Discoverix/.venv/Scripts/python.exe -m uvicorn app.main:app --port 8077
# -> http://127.0.0.1:8077
```

## Jouer

- **Entrée** : pose le mot saisi (validé contre le mot courant).
- **Entrée à vide** ou **Tab** : encaisse le pending dans le score définitif.
- **Trois zones** (pas un mur binaire) :
  - *fort* (cos ≥ TAU) : plein score, recharge la jauge, monte le combo ;
  - *faible* (TAU_GRACE ≤ cos < TAU) : accepté, minoré, recharge partielle, combo figé ;
  - *rejet* (cos < TAU_GRACE) : refusé **sans pénalité**, on réessaie.
- **Jauge** (pas de timer plat) : se vide vite, se recharge à chaque bon mot.
  À sec avec du pending non encaissé → tu le **perds** (le vrai risque du push).
- Mot de départ **aléatoire** à chaque partie (le mode quotidien déterministe
  reste dispo côté serveur : `/api/seed?mode=daily`).

## Architecture

```
constants.py   TOUS les knobs calibrables (VOCAB_ZIPF_MIN, TAU, TAU_GRACE, SYNO, WS, WV, jauge…)
app/db.py      Vocab : dictionnaire + proximité + spécificité, tout au runtime depuis le modèle
app/scoring.py formule de hop (sweet-spot + surprise), fonctions pures
app/seed.py    mot du jour (hash date) ou aléatoire
app/main.py    FastAPI : GET /api/seed, POST /api/hop
web/           front vanilla (HTML/CSS/JS), localStorage pour le best local
```

**Le modèle EST le dictionnaire — aucune base, aucun rebuild.** Un mot est jouable
s'il a un vecteur ET que `wordfreq` le reconnaît (`zipf >= VOCAB_ZIPF_MIN`). Au
démarrage (~4 s), `app/db.py` scanne le top-600k du modèle, garde ~83k mots
jouables (avec leur zipf) et bâtit une petite matrice de référence (top-30k) pour
la spécificité. Ensuite, tout est runtime :

- **validité** = mot dans le vocab (accent-insensible) ;
- **proximité** = `cos(P, G)`, un produit scalaire des deux vecteurs ;
- **spécificité** = degré de G (nb de voisins >= TAU parmi les 30k mots de
  référence), un produit matrice-vecteur (~9 ms).

Conséquence : **tous les seuils (`VOCAB_ZIPF_MIN`, `TAU`, `TAU_GRACE`, `SYNO`…)
sont des réglages instantanés** — il suffit de redémarrer (~4 s). Couverture = tout
vrai mot FR du modèle, dérivations comprises (`royalisme`…).

## Formule (dans `app/scoring.py`, knobs dans `constants.py`)

Deux indicateurs séparés autour du tableau de score :
- **portail** (proximité) : la proximité est un *gate*, pas des points — elle décide
  seulement si le hop est valide (ni trop loin, ni trop proche).
- **ressemblance** : malus si G est un écho du mot précédent (synonyme `>= SYNO` ou
  même racine) → le hop passe en faible.

```
prox = cos(P, G)
if prox < TAU_GRACE  : REJET (refusé)
rarete       = borne inverse du Zipf(G)      # SEUL score de "valeur du mot" (rareté
                                             #   et spécificité fusionnées, pour la lisibilité)
speed        = exp(-t / SPEED_TAU)           # sépare les hops rapides
hop_points   = BASE * (1 + WS*rarete) * (1 + WV*speed)

zone FORT   si TAU <= prox < SYNO et pas même-racine  -> plein score + monte le combo
zone FAIBLE sinon (trop loin, trop proche/synonyme, ou dérivation) -> *= WEAK_POINTS_FACTOR, combo figé
```

Combo : le pending accumule `hop_points × m`. `m` démarre à 1 et monte selon la
**rareté** du hop fort : `m += COMBO_STEP × (COMBO_FLOOR + rarete)`, **plafonné à
MULT_MAX** (pour que la longueur ne batte plus l'intelligence). Encaisser : pending ->
score, m -> 1. Filet : 1er raté = le mult tressaille, 2e raté consécutif = reset ×1 ;
un bon mot réarme. Jauge à sec : pending perdu.

## Calibration — repères (tout est runtime, redémarrer suffit)

- **Bruit de fond** (paires sans rapport) : ~0.12–0.25 (`chat~voiture` 0.24).
- **Faible mais plausible** : ~0.29–0.30 (`guerre~tuer` 0.29).
- **Vrais ponts** : ~0.35–0.55 (`guerre~paix` 0.52). **Quasi-synonymes** : 0.7+
  (`chat~chats` 0.74). → d'où `TAU=0.30`, `TAU_GRACE=0.26`, `SYNO=0.62`.

À sentir : `VOCAB_ZIPF_MIN` (couverture/bruit du dico), `TAU`/`TAU_GRACE`/`SYNO`
(zones), `SPEC_SCALE`, `GAUGE_SECONDS`, `WS`/`WV`.

Les **noms propres** (john/paris/olga…) sont écartés nativement : un mot est rejeté
si sa forme Capitalisée est `PROPER_NOUN_RATIO`× plus fréquente que sa minuscule
(d'après les rangs du modèle). Les mots communs qui sont aussi des prénoms
(`pierre`, `rose`, `olivier`) restent jouables.

Limite de fond (FastText = proximité **distributionnelle**) : les **collocations /
liens encyclopédiques** sont invisibles (`fille facile` 0.23, `hémoglobine~complexe`
0.10). Il faudrait blender une source d'associations type **JeuxDeMots** — hors proto.
