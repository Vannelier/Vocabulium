# Vocabulium — Mécanique « Mot cible » (waypoint exact)

Date : 2026-08-03
Statut : validé (brainstorming), à implémenter
Bloc : D (profondeur — objectif de skill)

## Contexte & objectif

Le jeu a de bonnes bases (chaînage, rareté/vitesse, rang, lettres interdites) mais
manque d'un **but à poursuivre**. On ajoute un **mot cible** : un objectif optionnel
par-dessus le chaînage, qui récompense le pilotage de la chaîne vers un mot précis.

Décisions de design (brainstorming) :
- **Bonus optionnel** : on continue à enchaîner normalement ; la cible est un bonus,
  jamais une obligation, jamais une punition si on l'ignore.
- **Capture = mot EXACT** joué et **accepté** par le portail (pas rejeté).
- **Zéro guidage** : aucun indicateur « à portée ». Le joueur juge lui-même quand il
  est assez proche. Tenter la cible trop loin = **rejet = raté normal** (−1 rang) : le
  risque fait le skill.
- **Anti-collision par protection** : la cible est tirée **sans aucune lettre déjà
  interdite**, et tant qu'elle est active **le système d'interdiction ne bannit JAMAIS
  une lettre présente dans la cible** (il en prend une autre). La cible reste donc
  toujours 100 % tapable.
- **Aucun rafraîchissement** : la cible **reste jusqu'à la capture** (ni timeout, ni
  remplacement). Le joueur a tout son temps pour construire son chemin.
- **Bonus × rang** : le bonus de capture est multiplié par le multiplicateur du rang
  courant → capturer en plein SSS = jackpot (lie les deux systèmes).

## Le mécanisme

1. **Affichage.** Une bande **CIBLE** compacte montre le mot à atteindre + son bonus de
   base : `CIBLE  océan  +500`. Discrète ; elle **célèbre** à la capture. Pas d'état
   intermédiaire (pas de « à portée »).

2. **Poursuite.** Le joueur enchaîne librement en essayant de rapprocher la chaîne du
   sens de la cible. Chaque coup reste soumis aux règles habituelles (proximité au mot
   précédent, lettres interdites). La cible ne bouge pas.

3. **Capture.** Quand le mot joué est **exactement** la cible ET qu'il est **accepté**
   (zone forte ou faible, pas rejeté) :
   - **bonus = BONUS_BASE(cible) × RANK_MULT[rang]**, ajouté au score (EN PLUS des points
     normaux du hop).
   - **célébration** (flash + toast « CIBLE ! »), puis **nouvelle cible plus rare / plus
     payante**. L'escalade (rareté ↑, bonus ↑) n'a lieu **qu'à la capture**.

4. **Essai manqué.** Taper la cible alors qu'elle est trop loin → le portail la rejette
   → **raté normal** (−1 rang, comme tout mot trop loin). Aucune logique spéciale.

## Anti-collision : le tirage des lettres saute les lettres de la cible

Règle : **aucune lettre de la cible active n'est jamais interdite.**

- À la **sélection** de la cible : on écarte tout mot contenant une lettre **déjà
  interdite** (au moment du tirage).
- Pendant que la cible est active : les lettres interdites actives =
  `ordre.filter(lettre ∉ cible).slice(0, forbiddenCount)`. On **maintient le nombre**
  de lettres interdites (`forbiddenCount` inchangé) en **puisant plus loin** dans
  l'ordre, mais **jamais** une lettre de la cible.
- À la **capture** (changement de cible) : on recalcule ; les lettres de l'ANCIENNE
  cible redeviennent interdictibles, celles de la NOUVELLE deviennent protégées. Simple
  re-render, pas de beat pour ces échanges (le beat ne se déclenche qu'à l'augmentation
  du compteur).

## Sélection de la cible (backend)

Nouvel endpoint `GET /api/target` :
- **Entrées** (query) : `current` (mot courant), `avoid` (lettres interdites actives,
  concaténées), `captures` (nb de captures, pour le palier de rareté), `played`
  (mots déjà joués, à exclure — ou géré côté client en re-tirant).
- **Sélection** : un mot jouable tel que
  - zipf dans une bande qui **descend avec `captures`** (de plus en plus rare) ;
  - ne contient **aucune** lettre de `avoid` ;
  - **pas déjà joué**, ≠ mot courant ;
  - **pas immédiatement jouable** depuis `current` (prox(current, cible) < `TAU_GRACE`)
    → force un vrai chemin de plusieurs hops (sinon capture triviale).
- **Sortie** : `{ "word": <cible>, "zipf": <z>, "bonus_base": <int> }` où
  `bonus_base = TARGET_BASE + round(TARGET_RARE_W × rarete(zipf))` (rareté = même
  formule que le scoring). Valeurs de départ : `TARGET_BASE = 200`, `TARGET_RARE_W = 800`.

Bande de rareté de départ (tunable) : `zHi = clamp(4.8 − 0.5×captures, ZIPF_MIN, …)`,
`zLo = zHi − 0.6`. La rareté croissante durcit naturellement (moins de voisins).

## UI (lisibilité)

- Bande **CIBLE** compacte au-dessus (ou sous) la bande **Lettres interdites**, même
  style de cadre : titre `CIBLE`, le mot en gros, le bonus de base à droite.
- **Capture** : la bande flashe (couleur de succès), un toast `★ CIBLE ★ +N` (N = bonus
  réellement encaissé, × rang), puis la nouvelle cible apparaît (petit slam).
- **Mobile** : compacte, une ligne ; s'intègre au layout défilable existant.
- Pas d'indicateur de proximité (choix de design : zéro guidage).

## Portée technique

- **Backend** : ajout de `GET /api/target` (sélection). `/api/hop` **inchangé** — la
  capture est détectée **côté client** (`res.word === target` && hop accepté).
- **`web/letters.js`** : `activeForbidden(order, words, every, start, targetLetters)`
  filtre les lettres de la cible (protection). `forbiddenCount` inchangé.
- **`web/app.js`** : état `target` (mot), `targetBonusBase`, `captures` ; `fetchTarget()`
  (appelle `/api/target`), `renderTarget()`, détection de capture dans `submitHop`
  (bonus × rang, célébration, re-fetch), reset dans `prepareRun`. `activeForbidden()`
  passe les lettres de la cible.
- **`web/index.html` / `web/style.css`** : bande CIBLE + animation de capture.
- **Daily** : la cible dépend de `current`/`captures`/`avoid` (dérivés du run), pas
  d'un tirage date-déterministe dédié pour l'instant — le défi du jour reste défini par
  le mot de départ + l'ordre des lettres. (Cibles déterministes en daily = hors périmètre.)

## Paramètres réglables

`TARGET_BASE`, `TARGET_RARE_W`, bande de rareté (`zHi/zLo` vs `captures`), seuil
« pas immédiatement jouable » (`TAU_GRACE`), bonus × rang (on/off).

## Hors périmètre (plus tard)

- Cibles **déterministes** en défi du jour (mêmes cibles pour tous).
- Indice de direction / « chaud-froid » (on a explicitement choisi zéro guidage).
- Historique / stats des captures.

## Critères de réussite

- La cible est **lisible** et **toujours tapable** (aucune de ses lettres n'est jamais
  interdite ; tirée sans lettre interdite).
- Capturer demande de **piloter la chaîne** sur plusieurs hops (cible non immédiate) et
  de **juger le bon moment** (tenter trop loin coûte un raté).
- La capture est **gratifiante** (bonus × rang, célébration) et **relance** l'objectif
  (cible plus rare).
- Zéro régression : la mécanique est **optionnelle** (ignorer la cible ne pénalise pas) ;
  le chaînage, le rang, les lettres interdites fonctionnent comme avant ; backend
  `/api/hop` intact ; mobile OK.
