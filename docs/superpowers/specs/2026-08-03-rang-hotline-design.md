# Vocabulium — Système de rang « Hotline » (combo + juice)

Date : 2026-08-03
Statut : validé (brainstorming), à implémenter
Bloc : A+B (feel du score + juice arcade)

## Contexte & objectif

Le multiplicateur actuel (×1→×4, glissement continu) est **plat et invisible** : il
monte lentement, ses variations se noient dans des scores déjà gros, et le joueur ne
ressent ni sa montée ni sa chute. Objectif : transformer le combo en un **système de
rang arcade, lisible et violent** (« maniaque / Hotline Miami »), qui donne envie de
pousser le risque.

Décisions de design déjà tranchées (brainstorming) :
- On **relooke le multiplicateur existant** (option A) : le rang EST le multiplicateur.
  Pas de 2ᵉ système à équilibrer. Priorité = lisibilité.
- Modèle **paliers discrets + barre**, où **la lettre du rang EST la barre** : dessinée
  en contour creux, elle se remplit de sa couleur ; pleine = palier suivant.
- Dynamique **volatile** : monte vite, chute qui pique (−1 rang au 1ᵉʳ raté, shatter au 2ᵉ).
- **100 % front** : le multiplicateur est déjà appliqué côté client (`gained =
  hop_points × mult`). Aucun changement backend, aucun risque prod.

## Le modèle de rang (paliers discrets)

Sept rangs : **D · C · B · A · S · SS · SSS**. Chaque rang porte un multiplicateur fixe,
non-linéaire (le haut paie fort). Valeurs de départ (tunables) :

| rang | D | C | B | A | S | SS | SSS |
|------|---|---|---|---|---|----|-----|
| ×    |1.0|1.4|1.8|2.3|3.0|4.0 |5.5 |
| couleur | `#8a94a6` acier | `#35d0ba` vert | `#38bdf8` cyan | `#a78bfa` violet | `#ffd34e` or | `#ff8c1a` orange | `#ff2d55` rouge néon |

Le plafond passe de ×4 à **×5.5**, mais réservé au skill soutenu.

### État (client)

Remplace le `S.mult` continu par :
- `rankIndex` : 0 (D) … 6 (SSS).
- `rankFill` : progression [0,1] vers le rang suivant.
- `misses` : filet de ratés (comme aujourd'hui).
- Le multiplicateur appliqué au score = `RANK_MULT[rankIndex]` (exposé via `S.mult`
  pour ne rien changer à la ligne de scoring `gained = res.hop_points * S.mult`).

### La montée (remplissage, pondéré qualité)

- **Coup fort** : `rankFill += FILL_STEP × (FILL_FLOOR + rarete)`. Un pont rare/rapide
  (rareté haute) remplit davantage → le skill accélère la montée.
- **Coup faible** : petit remplissage `FILL_WEAK` (ne bloque pas totalement, mais reste
  marginal ; les coups forts sont le vrai moteur).
- Quand `rankFill >= 1` et `rankIndex < 6` : **rang-up** → `rankIndex++`,
  `rankFill -= 1` (report du surplus), déclenche le SLAM. À SSS, `rankFill` reste plein
  (clamp), pas de rang au-dessus.
- Tout coup accepté (fort ou faible) **réarme le filet** (`misses = 0`).

Constantes de départ (tunables, cible ≈ 8-12 bons coups pour SSS) :
`FILL_STEP = 0.55`, `FILL_FLOOR = 0.45`, `FILL_WEAK = 0.12`.

### La chute (volatile)

Un raté = mot rejeté (trop loin) ou inconnu (typo). (Le refus « lettre interdite » et
« même mot / sing.-plur. » ne comptent PAS comme ratés — inchangé.)

- **1ᵉʳ raté** (`misses` passe à 1) : **rang-down** → `rankIndex = max(0, rankIndex-1)`,
  `rankFill = DROP_FILL` (retombe partiellement rempli), juice de chute (crack rouge +
  petit shake). Si déjà à D, pas de descente, juste le flash d'avertissement.
- **2ᵉ raté consécutif** (`misses >= 2`) : **SHATTER** → `rankIndex = 0` (D),
  `rankFill = 0`, `misses = 0`, juice violent (éclats + gros flash rouge + shake fort).

Constantes : `DROP_FILL = 0.30`, `MISS_SHATTER = 2`.

## L'UI — la lettre-jauge

Le HUD montre une **grosse lettre de rang** comme héros, à la place de l'actuel `×N.NN`
(le `×N` reste, mais **petit** à côté, pour la lisibilité du score).

**Rendu contour creux + remplissage** (technique CSS, sans image) :
- Couche 1 (contour) : la lettre en `color: transparent` + `-webkit-text-stroke: 3px
  var(--rank-color)` → contour creux.
- Couche 2 (remplissage) : une copie EXACTE de la lettre superposée, `color:
  var(--rank-color)`, révélée de bas en haut via `clip-path: inset(<(1-fill)·100>% 0 0 0)`.
  Quand `rankFill` monte, l'inset du haut diminue → la couleur monte dans la lettre.
- La couleur `--rank-color` = couleur du rang courant (voir table).

Le `×N` secondaire prend aussi la couleur du rang. Le **nombre de score** pulse dans la
couleur du rang à chaque coup (pop plus gros aux hauts rangs).

## Le juice (Hotline Miami)

- **Rang-up (SLAM)** : la nouvelle lettre s'écrase (scale-down élastique depuis grand),
  **flash blanc 1 frame**, **aberration chromatique** (ombres cyan/magenta décalées),
  **screen shake** court, burst de couleur du nouveau rang.
- **Chaque coup accepté** : impact-flash dans la couleur du rang, la lettre gagne son
  remplissage avec un petit rebond (bounce).
- **Rang-down (raté)** : crack rouge sur la lettre + shake léger.
- **Shatter (2ᵉ raté)** : la lettre **explose en morceaux** (éclats projetés), flash
  rouge lourd, shake fort, retour à D.
- **Ambiance** : aux rangs **SS / SSS**, le HUD entier peut pulser dans la couleur chaude
  (glow orange/rouge) pour signaler l'état « en feu ».
- **Screen shake** : classe sur `#app` (ou `body`) avec keyframes translate, 3 intensités
  (léger / moyen / fort) selon l'événement.

## Paramètres réglables (constantes, `app.js`)

`RANK_NAMES`, `RANK_MULT[]`, `RANK_COLOR[]`, `FILL_STEP`, `FILL_FLOOR`, `FILL_WEAK`,
`DROP_FILL`, `MISS_SHATTER`. Tout se re-tune sans toucher à la structure.

## Portée technique

- **`web/app.js`** : remplace la logique combo continue (`renderMult`, `breakCombo`,
  `registerMiss` côté combo) par l'état de rang (`rankIndex`, `rankFill`) + `renderRank()`
  (met à jour lettre creuse, remplissage, couleur, `×N`), + les transitions
  (rang-up / rang-down / shatter) qui déclenchent le juice. `S.mult` devient un miroir de
  `RANK_MULT[rankIndex]` pour garder `gained = res.hop_points * S.mult`.
- **`web/index.html`** : remplace le bloc `×N.NN` par la structure lettre-jauge
  (2 couches) + petit `×N`.
- **`web/style.css`** : contour creux + remplissage clip-path, couleurs par rang,
  animations slam / bounce / crack / shatter / flash, screen-shake, pulse SS/SSS.
- **Backend** : **aucun changement**.

## Hors périmètre (plus tard)

- **SFX / son** (prévu, hooks laissés aux points slam / shatter / hit).
- Les autres blocs : mode « mot-cible » (D), et l'éventuel re-tuning fin après playtest.
- Persistance du meilleur rang atteint (le high score existant suffit pour l'instant).

## Critères de réussite

- Le rang est **lisible d'un coup d'œil** (lettre géante qui se remplit) et son évolution
  se **ressent** (slam à chaque palier, shatter à la chute).
- Monter est **rapide et grisant** (~8-12 bons coups pour SSS), tomber **fait mal et se
  voit** (−1 rang / shatter).
- Le score du skill soutenu est **nettement** plus élevé (plafond ×5.5) sans casser la
  courbe des débutants (rang D = ×1.0).
- Zéro régression : refus lettre interdite / même-mot / sing.-plur. ne comptent toujours
  pas comme ratés ; backend intact ; pas de scroll horizontal ; mobile OK.
