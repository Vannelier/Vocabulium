# Système de rang « Hotline » — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer le multiplicateur continu (×1→×4, plat) par un système de rang arcade D→SSS où la lettre EST la jauge (contour creux qui se remplit), avec dynamique volatile (−1 rang / shatter) et juice Hotline Miami.

**Architecture:** 100 % front. Le multiplicateur est déjà appliqué côté client (`gained = res.hop_points * S.mult`) : on garde `S.mult` comme miroir de `RANK_MULT[rankIndex]`. Toute la logique (état de rang, remplissage, transitions) vit dans `web/app.js` ; l'affichage dans `web/index.html` + `web/style.css`. Aucun changement backend.

**Tech Stack:** Vanilla JS (pas de bundler), CSS (contour via `-webkit-text-stroke`, remplissage via `clip-path`). **Pas de framework de test** → vérification **dans le navigateur** (preview_start « Vocabulium » sur `http://localhost:8077`, `javascript_tool` pour l'état, `computer screenshot` pour le visuel). Bumper `?v=` des assets dans `index.html` à chaque tâche.

**Spec:** `docs/superpowers/specs/2026-08-03-rang-hotline-design.md`

---

## File Structure

- `web/index.html` — remplace le `<span class="mult" id="mult">×1.00</span>` par le bloc lettre-jauge : `<div class="rank" id="rank">` contenant la grande lettre (`#rankltr`, avec `data-l`) + le petit `×N` (`#mult`, id conservé).
- `web/app.js` — état de rang (`rankIndex`, `rankFill`) remplaçant le combo continu ; constantes `RANK_*`, `FILL_*` ; `renderRank()`, `addFill()`, `rankDown()`, `shatter()`, `syncMult()` ; câblage dans `submitHop` (montée) et le filet de ratés (chute) ; reset dans `prepareRun`. Suppression de `renderMult`/`breakCombo`/`_tilt`.
- `web/style.css` — lettre creuse + remplissage clip-path piloté par `--rank-color`/`--rank-fill` ; couleurs par rang ; (Task 2) animations slam/bounce/crack/shatter/flash, screen-shake, pulse SS/SSS, score-pop.

---

## Task 1: Mécanique de rang complète (montée + chute), sans animations

Le système de rang fonctionne de bout en bout, en visuel « plat » (la lettre se remplit et change de rang, mais sans slam/shatter animés — ça vient en Task 2). Le jeu reste jouable.

**Files:**
- Modify: `web/index.html` (bloc HUD `.val`)
- Modify: `web/app.js` (constantes, état `S`, refs `el`, montée/chute, `prepareRun`)
- Modify: `web/style.css` (styles `.rank` / `.rankltr`)

- [ ] **Step 1 : HTML — remplacer le `×N` par le bloc lettre-jauge**

Dans `web/index.html`, remplacer :
```html
<div class="val"><span id="pnum">0</span>
  <span class="mult" id="mult">×1.00</span><span class="jeop" id="jeop"></span></div>
```
par :
```html
<div class="val"><span id="pnum">0</span>
  <span class="jeop" id="jeop"></span></div>
<div class="rank" id="rank"><span class="rankltr" id="rankltr" data-l="D">D</span><span class="mult" id="mult">×1.00</span></div>
```
(Le `#mult` reste — c'est le petit ×N secondaire. Le `#rank` est le nouveau conteneur.)

- [ ] **Step 2 : CSS — lettre creuse + remplissage**

Dans `web/style.css`, ajouter (près des styles `.mult`) :
```css
.rank { display: flex; align-items: center; gap: 10px; margin-top: 2px;
  --rank-color: #8a94a6; --rank-fill: 0%; }
.rankltr { position: relative; font-weight: 900; font-size: 52px; line-height: 1;
  letter-spacing: -.02em; color: transparent;
  -webkit-text-stroke: 3px var(--rank-color); }
/* couche de remplissage : même lettre, révélée de bas en haut selon --rank-fill */
.rankltr::before { content: attr(data-l); position: absolute; inset: 0;
  color: var(--rank-color); -webkit-text-stroke: 0;
  clip-path: inset(calc(100% - var(--rank-fill)) 0 0 0); }
.rank .mult { font-size: 20px; font-weight: 900; }
```
Adapter/retirer l'ancien `.mult { margin-left: … }` s'il gêne (le `#mult` vit maintenant dans `.rank`).

- [ ] **Step 3 : app.js — constantes de rang**

Dans `web/app.js`, **ajouter** (sans rien supprimer — `RARE_THRESHOLD`/`RARE_HI` servent encore au juice « rare ») ces constantes juste après les `const RARE_*` existantes :
```js
const RANK_NAMES = ["D","C","B","A","S","SS","SSS"];
const RANK_MULT  = [1.0, 1.4, 1.8, 2.3, 3.0, 4.0, 5.5];
const RANK_COLOR = ["#8a94a6","#35d0ba","#38bdf8","#a78bfa","#ffd34e","#ff8c1a","#ff2d55"];
const FILL_STEP = 0.55, FILL_FLOOR = 0.45, FILL_WEAK = 0.12, DROP_FILL = 0.30;
// MISS_LIMIT (=2) existe déjà : sert de seuil de shatter (2e raté consécutif).
```

- [ ] **Step 4 : app.js — état + refs**

Dans l'objet `S`, remplacer `mult: 1` par `rankIndex: 0, rankFill: 0, mult: 1` (mult = miroir).
Dans `el`, remplacer `mult: $("mult")` par `rank: $("rank"), rankltr: $("rankltr"), mult: $("mult")`.

- [ ] **Step 5 : app.js — renderRank + helpers (remplacent renderMult/breakCombo)**

Supprimer `renderMult`, `breakCombo`, la variable `_tilt`. Ajouter :
```js
function syncMult() { S.mult = RANK_MULT[S.rankIndex]; }
function renderRank() {
  const i = S.rankIndex, col = RANK_COLOR[i];
  el.rankltr.dataset.l = RANK_NAMES[i];
  el.rankltr.textContent = RANK_NAMES[i];
  el.rank.style.setProperty("--rank-color", col);
  el.rank.style.setProperty("--rank-fill", (Math.max(0, Math.min(1, S.rankFill)) * 100).toFixed(1) + "%");
  el.mult.textContent = "×" + RANK_MULT[i].toFixed(2);
  el.mult.style.color = col;
  el.rank.classList.toggle("hot", i >= 5);   // SS/SSS (pulse ajouté en Task 2)
}
function rankUp() { /* Task 2 : juice de slam */ }
function addFill(amount) {
  S.rankFill += amount;
  while (S.rankFill >= 1 && S.rankIndex < RANK_NAMES.length - 1) {
    S.rankFill -= 1; S.rankIndex += 1; rankUp();
  }
  if (S.rankIndex >= RANK_NAMES.length - 1) S.rankFill = Math.min(S.rankFill, 1);
  syncMult(); renderRank();
}
function rankDown() {
  if (S.rankIndex > 0) { S.rankIndex -= 1; S.rankFill = DROP_FILL; }
  else S.rankFill = 0;
  syncMult(); renderRank();   // Task 2 : + crack rouge
}
function shatter() {
  S.rankIndex = 0; S.rankFill = 0; syncMult(); renderRank();   // Task 2 : + shatter
}
```

- [ ] **Step 6 : app.js — filet de ratés (chute)**

Remplacer `registerMiss` par :
```js
function registerMiss() {
  S.misses += 1;
  if (S.misses >= MISS_LIMIT) { S.misses = 0; shatter(); }   // 2e raté consécutif
  else rankDown();                                            // 1er raté : -1 rang
}
```
(`clearMisses` reste inchangé ; il est déjà appelé sur tout coup accepté.)

- [ ] **Step 7 : app.js — montée sur coup accepté**

Dans `submitHop`, remplacer le bloc `if (res.zone === "strong") { … renderMult("grow"); } else { … }` par :
```js
  if (res.zone === "strong") {
    addFill(FILL_STEP * (FILL_FLOOR + res.rarete));
    S.gauge = 1; S.hops += 1;
  } else {
    addFill(FILL_WEAK);
    S.gauge = Math.max(S.gauge, cfg.weak_refill); S.weakHops += 1;
  }
```

- [ ] **Step 8 : app.js — reset dans prepareRun**

Dans `prepareRun`, dans l'`Object.assign(S, {…})`, remplacer `mult: 1,` par `rankIndex: 0, rankFill: 0, mult: 1,`. Remplacer l'appel `renderMult(null);` par `renderRank();`.

- [ ] **Step 9 : Vérif navigateur — montée**

Bumper `?v=` (ex. v=37) dans `index.html`. `node --check web/app.js`. `preview_start` « Vocabulium », naviguer avec cache-bust.
Via `javascript_tool` : `startWith('random')`, puis simuler des coups forts en appelant `addFill(0.6)` plusieurs fois ; vérifier que `S.rankIndex` monte, `S.mult` suit `RANK_MULT[rankIndex]`, la lettre change (D→C→…) et `--rank-fill` progresse. `screenshot` : la lettre est creuse et se remplit de sa couleur.
Expected : à `rankIndex` 4 → lettre « S » or ×3.00 ; fill visible.

- [ ] **Step 10 : Vérif navigateur — chute**

Toujours en jeu : forcer `S.rankIndex=4; S.rankFill=0.5; S.misses=0; renderRank()`. Appeler `registerMiss()` une fois → attendu `rankIndex=3`, `rankFill=0.30` (rang-down). Rappeler `registerMiss()` → attendu shatter : `rankIndex=0`, `rankFill=0`, `misses=0`. Vérifier `read_console_messages` (aucune erreur).

- [ ] **Step 11 : Commit**

```bash
git add web/index.html web/app.js web/style.css
git commit -m "feat(rang): mécanique de rang D->SSS (lettre-jauge) remplace le multiplicateur continu"
```

---

## Task 2: Juice Hotline Miami (animations de transition)

Ajoute le flash/violence par-dessus la mécanique : slam de rang-up, bounce sur remplissage, crack sur rang-down, shatter, screen-shake, pulse SS/SSS, pop du score.

**Files:**
- Modify: `web/style.css` (keyframes + classes d'animation, screen-shake, pulse)
- Modify: `web/app.js` (déclenchement aux points de transition : `rankUp`, `rankDown`, `shatter`, `addFill`)
- Modify: `web/index.html` (bump `?v=`)

- [ ] **Step 1 : CSS — slam, bounce, crack, shatter, flash**

Dans `web/style.css`, ajouter :
```css
/* rang-up : la lettre s'écrase depuis grand + aberration chromatique */
.rankltr.slam { animation: rankslam .45s cubic-bezier(.2,1.6,.4,1); }
@keyframes rankslam {
  0% { transform: scale(2.2); filter: drop-shadow(3px 0 0 #0ff) drop-shadow(-3px 0 0 #f0f); opacity: .2; }
  40% { transform: scale(.9); }
  100% { transform: scale(1); filter: none; opacity: 1; }
}
/* remplissage : petit rebond */
.rankltr.bump { animation: rankbump .22s ease-out; }
@keyframes rankbump { 0%{transform:scale(1)} 45%{transform:scale(1.18)} 100%{transform:scale(1)} }
/* rang-down : crack rouge */
.rankltr.crack { animation: rankcrack .3s ease-out; }
@keyframes rankcrack {
  0%,100% { filter: none; transform: translateX(0); }
  30% { filter: drop-shadow(0 0 10px #ff3b57); transform: translateX(-4px) rotate(-3deg); }
  60% { transform: translateX(4px) rotate(3deg); }
}
/* shatter : la lettre explose (scale + fade + rouge) */
.rankltr.shatter { animation: rankshatter .5s ease-out; }
@keyframes rankshatter {
  0% { transform: scale(1); filter: drop-shadow(0 0 14px #ff2d55); }
  40% { transform: scale(1.3); opacity: .8; }
  100% { transform: scale(.6); opacity: 1; filter: none; }
}
/* screen shake (sur #app) */
.shake-s { animation: shakeS .18s; } .shake-m { animation: shakeM .28s; } .shake-l { animation: shakeL .4s; }
@keyframes shakeS { 25%{transform:translate(2px,-1px)} 75%{transform:translate(-2px,1px)} }
@keyframes shakeM { 20%{transform:translate(-4px,2px)} 60%{transform:translate(4px,-2px)} }
@keyframes shakeL { 10%{transform:translate(-7px,3px)} 40%{transform:translate(7px,-4px)} 70%{transform:translate(-5px,2px)} }
/* pulse "en feu" aux hauts rangs */
.rank.hot .rankltr { animation: hotpulse 1.1s ease-in-out infinite; }
@keyframes hotpulse { 0%,100%{filter:drop-shadow(0 0 6px var(--rank-color))} 50%{filter:drop-shadow(0 0 20px var(--rank-color))} }
```

- [ ] **Step 2 : app.js — helper de relance d'anim + screen shake**

Ajouter :
```js
function replay(elm, cls) { elm.classList.remove(cls); void elm.offsetWidth; elm.classList.add(cls); }
function screenShake(kind) {   // "s" | "m" | "l"
  const c = "shake-" + kind, app = document.getElementById("app");
  app.classList.remove("shake-s","shake-m","shake-l"); void app.offsetWidth; app.classList.add(c);
  setTimeout(() => app.classList.remove(c), 450);
}
```

- [ ] **Step 3 : app.js — brancher le juice aux transitions**

- Dans `rankUp()` : `replay(el.rankltr, "slam"); screenShake("m");`
- Dans `addFill()`, après un remplissage SANS rang-up (sinon le slam prime) : déclencher `replay(el.rankltr, "bump")` uniquement si aucun rang-up n'a eu lieu ce coup-ci (garder un booléen local `leveled`).
- Dans `rankDown()` : `replay(el.rankltr, "crack"); screenShake("s");`
- Dans `shatter()` : `replay(el.rankltr, "shatter"); screenShake("l");`

Exemple `addFill` révisé :
```js
function addFill(amount) {
  let leveled = false;
  S.rankFill += amount;
  while (S.rankFill >= 1 && S.rankIndex < RANK_NAMES.length - 1) {
    S.rankFill -= 1; S.rankIndex += 1; leveled = true; rankUp();
  }
  if (S.rankIndex >= RANK_NAMES.length - 1) S.rankFill = Math.min(S.rankFill, 1);
  syncMult(); renderRank();
  if (!leveled) replay(el.rankltr, "bump");
}
```

- [ ] **Step 4 : app.js — pop du score dans la couleur du rang**

Dans `renderHud()` (ou après un coup accepté), faire pulser `el.pnum` : ajouter une classe qui scale + colore brièvement dans `RANK_COLOR[S.rankIndex]`. (Réutiliser le pattern `replay`.) Ne pas casser l'état « record » doré existant : ne pas écraser la classe `.record` — utiliser une animation séparée (`.pop`) sur `#pnum`.
```css
#pnum.pop { animation: scorepop .2s ease-out; }
@keyframes scorepop { 0%{transform:scale(1)} 50%{transform:scale(1.25)} 100%{transform:scale(1)} }
```

- [ ] **Step 5 : Vérif navigateur — juice**

Bump `?v=` (v=38). `node --check`. Naviguer.
- `startWith('random')` puis `addFill(1.1)` → attendu : slam (screenshot montrant la lettre grande/aberration au moment T, ou vérifier `el.rankltr.classList.contains('slam')` juste après).
- Forcer un rang élevé, `registerMiss()` → crack + `#app` porte `shake-s` ; 2e `registerMiss()` → `shatter` + `shake-l`.
- Forcer `S.rankIndex=5; renderRank()` → `.rank.hot` présent (pulse).
- `read_console_messages` : aucune erreur. `screenshot` final pour le rendu.

- [ ] **Step 6 : Commit**

```bash
git add web/index.html web/app.js web/style.css
git commit -m "feat(rang): juice Hotline (slam, bounce, crack, shatter, screen-shake, pulse)"
```

---

## Notes d'exécution

- **Prod live** : merge/push sur `main` déclenche l'auto-deploy Railway. Grouper si besoin.
- **Playtest après coup** : les constantes (`RANK_MULT`, `FILL_STEP/FLOOR/WEAK`, `DROP_FILL`) sont à re-sentir en jeu ; cible ≈ 8-12 bons coups pour SSS, chute qui pique sans frustrer.
- **Non-régression** : les refus « lettre interdite » / « même mot » / « sing.-plur. » ne passent PAS par `registerMiss` (ils ne doivent donc ni faire chuter le rang ni casser le combo) — vérifier que c'est toujours le cas après Task 1.
