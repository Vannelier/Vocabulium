# Mode « Lettre interdite » — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter le mode « lettre interdite » (contrainte cumulative +1 lettre/10 mots), simplifier le scoring (retrait bank-or-push), et une fin partageable — pour un jeu web viral sans onboarding, mobile-first.

**Architecture:** Tout le mécanisme est **côté client** (JS vanilla) : un petit module pur `web/letters.js` (tirage pondéré des lettres, test accent-insensible, escalade, RNG déterministe pour le défi du jour), branché dans `web/app.js`. Le backend ne change pas (le serveur valide déjà la proximité du hop). UI dans `web/index.html` + `web/style.css`.

**Tech Stack:** JS vanilla (pas de build, pas de framework de test), FastAPI (inchangé), preview navigateur pour la vérification (pattern établi du projet : `preview_start` + `javascript_tool`).

**Note vérification :** le projet n'a pas de harness de test JS. On vérifie chaque tâche via le **navigateur** (`mcp__Claude_Browser__preview_start` puis `javascript_tool` pour asserter le comportement / lire le DOM), comme tout le reste du projet. Chaque tâche liste les assertions à faire.

---

## Structure des fichiers

- **Créer** `web/letters.js` — module pur : fréquences FR, `drawLetters`, `hasForbidden`, `forbiddenCount`, RNG déterministe. Aucune dépendance DOM. Exposé sur `window` (le projet n'a pas de bundler).
- **Modifier** `web/index.html` — bande lettres interdites, beat plein écran, écran de fin (partage), slots pub ; retrait du bouton Encaisser ; inclure `letters.js?v=`.
- **Modifier** `web/style.css` — styles bande/compteur/beat/blink, highlight rouge saisie, écran de fin, layout mobile.
- **Modifier** `web/app.js` — état lettres interdites + escalade, refus lettre interdite, highlight live, scoring direct (retrait pending/bank), fin + carte de partage, choix endless/daily.
- **Inchangé** : `app/*.py`, `constants.py` (le mécanisme est client).

Convention du projet : après toute modif front, **bumper le `?v=` des assets** dans `index.html` (cache-busting) et recharger avec `?cb=<ts>` pour éviter le cache HTML.

---

### Task 1 : Module `letters.js` — logique pure (tirage, test, escalade)

**Files:**
- Create: `web/letters.js`

- [ ] **Step 1 : Écrire le module complet**

```javascript
"use strict";
// Module PUR (aucun DOM). Exposé sur window (pas de bundler dans le projet).
(function (root) {
  // Fréquences des lettres en français (%). Sert à PONDÉRER le tirage : on veut
  // les lettres RARES d'abord (poids ∝ 1/fréquence), les courantes tard.
  const FREQ = {
    a: 7.6, b: 0.9, c: 3.3, d: 3.7, e: 14.7, f: 1.1, g: 0.9, h: 0.7, i: 7.5,
    j: 0.5, k: 0.05, l: 5.5, m: 3.0, n: 7.1, o: 5.4, p: 3.0, q: 1.4, r: 6.6,
    s: 7.9, t: 7.2, u: 6.3, v: 1.6, w: 0.04, x: 0.4, y: 0.3, z: 0.1,
  };
  const ALPHABET = Object.keys(FREQ);

  // RNG déterministe (mulberry32) à partir d'une graine entière.
  function rng(seed) {
    let s = seed >>> 0;
    return function () {
      s |= 0; s = (s + 0x6D2B79F5) | 0;
      let t = Math.imul(s ^ (s >>> 15), 1 | s);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  // Graine entière à partir d'une chaîne (date "2026-08-02").
  function seedFromString(str) {
    let h = 2166136261 >>> 0;
    for (let i = 0; i < str.length; i++) {
      h ^= str.charCodeAt(i); h = Math.imul(h, 16777619);
    }
    return h >>> 0;
  }

  // Replie les accents/majuscule -> lettre de base (é->e, ç->c, À->a).
  function fold(ch) {
    return ch.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase();
  }

  // Ordre COMPLET des 26 lettres, tirées sans remise, pondérées par 1/fréquence
  // (rares d'abord). `rand` = fonction 0..1 (Math.random en endless, rng(seed) en daily).
  // Retourne la liste ordonnée : la i-ème lettre interdite = ordre[i].
  function drawOrder(rand) {
    const pool = ALPHABET.map((L) => ({ L, w: 1 / FREQ[L] }));
    const order = [];
    while (pool.length) {
      const total = pool.reduce((s, p) => s + p.w, 0);
      let r = rand() * total, idx = 0;
      while (r > pool[idx].w) { r -= pool[idx].w; idx++; }
      order.push(pool[idx].L);
      pool.splice(idx, 1);
    }
    return order;
  }

  // Nb de lettres interdites après `words` mots acceptés, 1 nouvelle tous les `every`.
  function forbiddenCount(words, every) {
    return Math.floor(words / every);
  }

  // Les lettres interdites actives = les `forbiddenCount` premières de l'ordre.
  function activeForbidden(order, words, every) {
    return order.slice(0, forbiddenCount(words, every));
  }

  // Quelles lettres interdites (parmi `active`) apparaissent dans `word` (accents repliés).
  function offendingLetters(word, active) {
    const set = new Set(active);
    const hit = new Set();
    for (const ch of word) { const f = fold(ch); if (set.has(f)) hit.add(f); }
    return [...hit];
  }

  root.Letters = { FREQ, ALPHABET, rng, seedFromString, fold, drawOrder,
                   forbiddenCount, activeForbidden, offendingLetters };
})(window);
```

- [ ] **Step 2 : Vérifier au navigateur (module pur)**

Démarrer la preview (`preview_start {name:"Vocabulium"}`), charger `letters.js` puis asserter via `javascript_tool` :

```javascript
// injecte le module puis teste
await import('/letters.js?v=probe').catch(()=>{}); // si pas module, on charge via script
// (dans la vraie exécution : ajouter <script src="/letters.js"> à la page d'abord, cf Task 3)
const L = window.Letters;
const out = {};
// déterminisme : même graine -> même ordre
const a = L.drawOrder(L.rng(L.seedFromString("2026-08-02")));
const b = L.drawOrder(L.rng(L.seedFromString("2026-08-02")));
out.deterministe = JSON.stringify(a) === JSON.stringify(b);
out.premieres_rares = a.slice(0,5);            // doit contenir des rares (w,k,z,x,j…)
out.e_tard = a.indexOf('e') > 15;              // "e" doit sortir tard
out.count = [L.forbiddenCount(9,10), L.forbiddenCount(10,10), L.forbiddenCount(25,10)]; // [0,1,2]
out.accents = L.offendingLetters("éléphant", ['e']); // -> ['e'] (é replié)
out.clean = L.offendingLetters("chat", ['w','k']);    // -> []
return out;
```
Attendu : `deterministe:true`, `premieres_rares` = lettres rares, `e_tard:true`, `count:[0,1,2]`, `accents:['e']`, `clean:[]`.

- [ ] **Step 3 : Commit**

```bash
git add web/letters.js
git commit -m "feat(letters): module pur tirage/test/escalade des lettres interdites"
```

---

### Task 2 : Inclure `letters.js` et poser l'état lettres interdites dans le run

**Files:**
- Modify: `web/index.html` (ajouter le `<script src="/letters.js?v=15">` AVANT `app.js`)
- Modify: `web/app.js` (état `S.forbiddenOrder`, `S.wordCount` ; init endless/daily ; escalade)

- [ ] **Step 1 : Inclure le module dans la page**

Dans `web/index.html`, juste avant `<script src="/app.js?v=…">`, ajouter :
```html
  <script src="/letters.js?v=15"></script>
```
Et bumper `app.js`/`style.css` à `?v=15`.

- [ ] **Step 2 : État & init dans `app.js`**

Dans l'objet `S` (état), ajouter `forbiddenOrder: [], wordCount: 0`.
Dans `fetchSeed()` (ou `prepareRun`), après avoir `cfg`, initialiser l'ordre des lettres :
```javascript
// mode "daily" -> ordre déterministe depuis la date ; sinon aléatoire local.
const mode = new URLSearchParams(location.search).get("mode") || "random";
const dateKey = (new Date()).toISOString().slice(0,10);
const rand = mode === "daily"
  ? Letters.rng(Letters.seedFromString(dateKey))
  : Math.random;
S.forbiddenOrder = Letters.drawOrder(rand);
```
Dans `prepareRun()` (Object.assign de l'état), remettre `wordCount: 0`.

Ajouter une constante en haut d'`app.js` : `const LETTER_EVERY = 10;`
Exposer aussi `cfg.letter_every` plus tard si on veut la régler serveur — pour l'instant constante client.

- [ ] **Step 3 : Helper d'accès aux lettres actives**

Ajouter dans `app.js` :
```javascript
function activeForbidden() {
  return Letters.activeForbidden(S.forbiddenOrder, S.wordCount, LETTER_EVERY);
}
```

- [ ] **Step 4 : Vérifier**

Bump `?v=15`, recharger (`/?cb=<ts>`), puis :
```javascript
return { has_module: !!window.Letters, ordre_len: S?.forbiddenOrder?.length,
         actives_debut: activeForbidden() };
```
Attendu : `has_module:true`, `ordre_len:26`, `actives_debut:[]` (0 mot joué).

- [ ] **Step 5 : Commit**

```bash
git add web/index.html web/app.js
git commit -m "feat(letters): état + ordre des lettres interdites dans le run (endless/daily)"
```

---

### Task 3 : Refus des mots à lettre interdite (mécanique)

**Files:**
- Modify: `web/app.js` (dans `submitHop`, AVANT l'envoi au serveur)

- [ ] **Step 1 : Intercepter les lettres interdites**

Dans `submitHop()`, après `const raw = el.guess.value.trim()` et le early-return `if(!raw)`, mais AVANT le `fetch('/api/hop')`, ajouter :
```javascript
const active = activeForbidden();
const offending = Letters.offendingLetters(raw.toLowerCase(), active);
if (offending.length) {
  // refusé : ni raté, ni casse de combo. Juste illégal -> feedback + retry.
  flashForbidden(offending);          // clignote la/les lettre(s) dans la bande (Task 5)
  shake();                            // le champ tremble
  el.guess.value = "";
  return;                             // la jauge continue de tourner (le coût = temps)
}
```
(`flashForbidden` sera défini en Task 5 ; pour l'instant on peut le stubber `function flashForbidden(){}` pour que ça tourne.)

- [ ] **Step 2 : Incrémenter `wordCount` sur mot accepté**

Dans le bloc « hop accepté (strong ou weak) » de `submitHop` (là où on fait `S.played.add(res.word)`), ajouter :
```javascript
  S.wordCount += 1;
  maybeEscalate();     // vérifie si on franchit un palier de 10 (Task 4)
```
Stubber `function maybeEscalate(){}` pour l'instant.

- [ ] **Step 3 : Vérifier**

Bump `?v=16`, recharger. Jouer (cliquer Jouer), puis forcer un état d'interdiction pour tester :
```javascript
S.wordCount = 15;                      // simule 1 lettre interdite active
const active = activeForbidden();      // 1 lettre
const bad = active[0];                 // ex 'w'
// trouve un mot du vocab contenant cette lettre pour tester le refus
const g=document.getElementById('guess');
g.value = "kiwi";                      // si 'w' interdit -> doit être refusé sans casser le combo
const multBefore = document.getElementById('mult').textContent;
g.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true}));
await new Promise(r=>setTimeout(r,100));
return { active, refusé_input_vidé: g.value==="", combo_intact: document.getElementById('mult').textContent===multBefore };
```
Attendu : le mot contenant la lettre interdite est refusé (input vidé), combo inchangé. (Adapter le mot testé à la lettre réellement active.)

- [ ] **Step 4 : Commit**

```bash
git add web/app.js
git commit -m "feat(letters): refuse les mots contenant une lettre interdite (sans casser le combo)"
```

---

### Task 4 : Bande des lettres interdites + compteur N/10 + escalade

**Files:**
- Modify: `web/index.html` (bloc bande lettres, placé au-dessus du mot courant)
- Modify: `web/style.css` (styles bande + compteur)
- Modify: `web/app.js` (`renderForbidden`, `maybeEscalate`)

- [ ] **Step 1 : HTML de la bande**

Dans `index.html`, juste avant le bloc `.current` (« tu enchaînes depuis »), insérer :
```html
    <div class="forbid" id="forbid">
      <div class="forbid-head">INTERDIT
        <span class="forbid-next" id="forbidNext">prochaine dans 10</span></div>
      <div class="forbid-letters" id="forbidLetters"></div>
    </div>
```

- [ ] **Step 2 : CSS**

Dans `style.css` :
```css
.forbid { margin-bottom: 14px; }
.forbid-head { font-size: 11px; letter-spacing: .14em; text-transform: uppercase;
  color: var(--muted); display: flex; justify-content: space-between; align-items: baseline;
  margin-bottom: 6px; }
.forbid-next { font-weight: 800; color: var(--warm); letter-spacing: .02em; }
.forbid-letters { display: flex; flex-wrap: wrap; gap: 8px; min-height: 34px; }
.forbid-letters .fl { display: inline-flex; align-items: center; justify-content: center;
  width: 30px; height: 34px; border-radius: 8px; background: rgba(255,59,87,.14);
  border: 1.5px solid var(--bail); color: var(--bail); font-weight: 900; font-size: 19px;
  text-transform: uppercase; position: relative; }
.forbid-letters .fl::after { content: ""; position: absolute; left: 4px; right: 4px;
  height: 2.5px; background: var(--bail); transform: rotate(-12deg); }  /* barré */
.forbid-empty { color: var(--muted); font-size: 12px; opacity: .7; align-self: center; }
.forbid-letters .fl.blink { animation: flblink .5s ease-out 3; }
@keyframes flblink {
  0%,100% { background: rgba(255,59,87,.14); transform: scale(1); }
  50% { background: var(--bail); color: #fff; transform: scale(1.18);
        box-shadow: 0 0 14px var(--bail); }
}
```

- [ ] **Step 3 : `renderForbidden` + `maybeEscalate` dans `app.js`**

```javascript
function renderForbidden() {
  const active = activeForbidden();
  const box = el.forbidLetters;
  box.innerHTML = active.length
    ? active.map(L => `<span class="fl" data-l="${L}">${L}</span>`).join("")
    : `<span class="forbid-empty">aucune — profite !</span>`;
  const into = LETTER_EVERY - (S.wordCount % LETTER_EVERY);
  el.forbidNext.textContent = "prochaine dans " + into;
}

// Appelé après chaque mot accepté : détecte le franchissement d'un palier de 10.
function maybeEscalate() {
  const before = Letters.forbiddenCount(S.wordCount - 1, LETTER_EVERY);
  const after = Letters.forbiddenCount(S.wordCount, LETTER_EVERY);
  if (after > before) newForbiddenBeat(activeForbidden()[after - 1]);  // Task 6
  renderForbidden();
}
```
Ajouter les refs dans `el` : `forbid: $("forbid"), forbidLetters: $("forbid-letters")`… (ids : `forbidLetters`, `forbidNext`).
Corriger : `forbidLetters: $("forbidLetters"), forbidNext: $("forbidNext")`.
Stubber `function newForbiddenBeat(){}` (Task 6).
Appeler `renderForbidden()` dans `prepareRun()` (après reset de `wordCount`).

- [ ] **Step 4 : Vérifier**

Bump `?v=17`, recharger. Jouer, puis :
```javascript
S.wordCount = 24; renderForbidden();
return { lettres_affichées: [...el.forbidLetters.querySelectorAll('.fl')].map(e=>e.textContent),
         compteur: el.forbidNext.textContent };   // 2 lettres, "prochaine dans 6"
```
Attendu : 2 lettres barrées rouges, compteur « prochaine dans 6 ».

- [ ] **Step 5 : Commit**

```bash
git add web/index.html web/style.css web/app.js
git commit -m "feat(ui): bande des lettres interdites + compteur N/10 + escalade"
```

---

### Task 5 : Highlight live dans la saisie + clignotement au refus

**Files:**
- Modify: `web/app.js` (`flashForbidden`, listener `input`)
- Modify: `web/style.css` (état saisie « contient interdit »)

- [ ] **Step 1 : Clignotement de la lettre fautive dans la bande**

```javascript
function flashForbidden(letters) {
  for (const L of letters) {
    const el2 = el.forbidLetters.querySelector(`.fl[data-l="${L}"]`);
    if (el2) { el2.classList.remove("blink"); void el2.offsetWidth; el2.classList.add("blink"); }
  }
}
```

- [ ] **Step 2 : Highlight live pendant la frappe**

Ajouter un listener `input` sur `#guess` (près du listener `keydown`) :
```javascript
el.guess.addEventListener("input", () => {
  const bad = Letters.offendingLetters(el.guess.value.toLowerCase(), activeForbidden());
  el.guess.classList.toggle("hasforbidden", bad.length > 0);
});
```
CSS :
```css
#guess.hasforbidden { border-color: var(--bail);
  box-shadow: 0 0 0 3px rgba(255,59,87,.20); color: var(--bail); }
```

- [ ] **Step 3 : Vérifier**

Bump `?v=18`, recharger, jouer. Forcer une lettre active et taper un mot fautif :
```javascript
S.wordCount = 15; renderForbidden();
const bad = activeForbidden()[0];
const g=document.getElementById('guess');
g.value = "abc"+bad; g.dispatchEvent(new Event('input',{bubbles:true}));
const live = g.classList.contains('hasforbidden');
g.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true}));
await new Promise(r=>setTimeout(r,60));
const blink = !!el.forbidLetters.querySelector('.fl.blink');
return { highlight_live: live, clignote_au_refus: blink };
```
Attendu : `highlight_live:true`, `clignote_au_refus:true`.

- [ ] **Step 4 : Commit**

```bash
git add web/app.js web/style.css
git commit -m "feat(ui): highlight rouge live dans la saisie + clignotement de la lettre au refus"
```

---

### Task 6 : Beat « ⛔ LETTRE INTERDITE » à chaque palier

**Files:**
- Modify: `web/index.html` (élément overlay du beat)
- Modify: `web/style.css` (animation)
- Modify: `web/app.js` (`newForbiddenBeat`)

- [ ] **Step 1 : HTML**

Ajouter dans `index.html` (à côté du `#toast`) :
```html
  <div class="beat" id="beat"></div>
```

- [ ] **Step 2 : CSS**

```css
.beat { position: fixed; left: 50%; top: 40%; transform: translateX(-50%);
  pointer-events: none; text-align: center; font-weight: 900; color: var(--bail);
  text-shadow: 0 0 24px var(--bail); z-index: 30; opacity: 0; }
.beat .b1 { font-size: 15px; letter-spacing: .2em; }
.beat .b2 { font-size: 64px; text-transform: uppercase; }
.beat.play { animation: beatpop 1s ease-out forwards; }
@keyframes beatpop {
  0% { opacity: 0; transform: translateX(-50%) scale(.6); }
  15% { opacity: 1; transform: translateX(-50%) scale(1.12); }
  70% { opacity: 1; transform: translateX(-50%) scale(1); }
  100% { opacity: 0; transform: translateX(-50%) scale(1); }
}
```

- [ ] **Step 3 : JS**

```javascript
function newForbiddenBeat(letter) {
  el.beat.innerHTML = `<div class="b1">⛔ lettre interdite</div><div class="b2">${letter}</div>`;
  el.beat.classList.remove("play"); void el.beat.offsetWidth; el.beat.classList.add("play");
}
```
Ajouter `beat: $("beat")` dans `el`.

- [ ] **Step 4 : Vérifier**

Bump `?v=19`, recharger, jouer. Déclencher :
```javascript
newForbiddenBeat("w");
await new Promise(r=>setTimeout(r,50));
return { beat_visible: el.beat.classList.contains('play'), html: el.beat.textContent };
```
Attendu : `beat_visible:true`, texte « ⛔ lettre interdite w ».

- [ ] **Step 5 : Commit**

```bash
git add web/index.html web/style.css web/app.js
git commit -m "feat(ui): beat plein écran a chaque nouvelle lettre interdite"
```

---

### Task 7 : Scoring direct — retrait du bank-or-push

**Files:**
- Modify: `web/index.html` (retirer le bouton Encaisser + son texte de hint)
- Modify: `web/app.js` (score direct, retrait `pending`/`bank`)

- [ ] **Step 1 : Retirer l'UI d'encaissement**

Dans `index.html` : supprimer le `<button id="bank">ENCAISSER</button>` (garder l'input seul dans `.inrow`), et dans le HUD renommer « Pending » en « Score » n'est pas nécessaire — on garde un seul `SCORE`. Simplifier le HUD à : `Score ×combo`. Retirer les mentions « encaisse » du `.hint`.

Concrètement, remplacer le HUD :
```html
    <div class="hud">
      <div class="stat" id="score"><div class="label">Score</div>
        <div class="val"><span id="pnum">0</span>
          <span class="mult" id="mult">×1.00</span></div></div>
    </div>
```
(On réutilise `#pnum` comme affichage du score total, `#mult` reste le combo.)

- [ ] **Step 2 : Score direct dans `app.js`**

Dans `submitHop`, bloc accepté : remplacer l'accumulation `pending` par un ajout direct au score :
```javascript
  const gained = res.hop_points * S.mult;
  S.score += gained;          // <-- direct, plus de pending
```
Supprimer : la fonction `bank()`, l'appel `bank()` sur Entrée-à-vide (Entrée à vide ne fait plus rien, ou relance le focus), la gestion `S.pending`, l'`el.bank`, le raccourci `Tab`, et dans `endRun()` la logique `keep_pending_on_timeout`/`lost` (le score est déjà à jour ; la fin affiche juste `S.score`).
`renderHud()` : `el.pnum.textContent = Math.round(S.score);` (au lieu de pending).
Retirer les refs `el.bank`, `el.pending` inutiles (ou les garder inertes).

- [ ] **Step 3 : Vérifier**

Bump `?v=20`, recharger, jouer 3 hops. Le `SCORE` doit monter directement à chaque mot (pas de pending séparé), pas de bouton Encaisser :
```javascript
return { bouton_encaisser: !!document.getElementById('bank'),
         score: document.getElementById('pnum').textContent };
```
Attendu : `bouton_encaisser:false`, `score` > 0 après avoir joué.

- [ ] **Step 4 : Commit**

```bash
git add web/index.html web/app.js
git commit -m "feat(score): scoring direct (retrait du bank-or-push)"
```

---

### Task 8 : Écran de fin + carte de partage (emoji)

**Files:**
- Modify: `web/index.html` (contenu écran `#end` : récap + boutons Partager/Rejouer + slot pub)
- Modify: `web/app.js` (`endRun` : récap lettres survécues + génération grille emoji + partage)

- [ ] **Step 1 : HTML de l'écran de fin**

Remplacer le contenu de `#end` :
```html
  <div class="end" id="end">
    <h1>Partie terminée</h1>
    <div class="final" id="final">0</div>
    <div class="recap" id="recap"></div>
    <pre class="sharegrid" id="sharegrid"></pre>
    <div class="endbtns">
      <button id="share">Partager</button>
      <button id="again">Rejouer</button>
    </div>
    <div class="adslot adslot-end" id="adEnd"><!-- AdSense (fin) --></div>
  </div>
```

- [ ] **Step 2 : Récap + grille emoji + partage dans `app.js`**

Dans `endRun()`, après avoir figé le score :
```javascript
  const letters = Letters.forbiddenCount(S.wordCount, LETTER_EVERY);
  el.final.textContent = Math.round(S.score);
  el.recap.innerHTML = `${S.wordCount} mots · survécu à <b>${letters}</b> lettre${letters>1?'s':''} interdite${letters>1?'s':''}`;
  // grille : une case par mot, verte (fort) / jaune (faible). On stocke les zones jouées.
  const grid = S.zonesPlayed.map(z => z === "strong" ? "🟩" : "🟨");
  const rows = [];
  for (let i = 0; i < grid.length; i += 10) rows.push(grid.slice(i, i+10).join(""));
  const share = `Vocabulium — ${S.wordCount} mots, ${letters} lettres interdites 🔥\n`
    + rows.join("\n") + `\nvocabulium.up.railway.app`;   // adapter l'URL
  el.sharegrid.textContent = rows.join("\n");
  el.share.onclick = () => {
    if (navigator.share) navigator.share({ text: share }).catch(()=>{});
    else navigator.clipboard.writeText(share).then(()=> el.share.textContent = "Copié !");
  };
```
Ajouter à l'état `S` : `zonesPlayed: []`, et dans le bloc accepté de `submitHop` : `S.zonesPlayed.push(res.zone === "strong" ? "strong" : "weak");`. Reset dans `prepareRun`.
Refs `el` : `recap, sharegrid, share` (déjà `final`, `again`).

- [ ] **Step 3 : CSS (boutons + grille)**

```css
.endbtns { display: flex; gap: 12px; margin-top: 16px; }
.end .sharegrid { font-size: 20px; line-height: 1.15; margin-top: 12px; letter-spacing: 2px; }
#share { background: var(--cool); color: #04120f; border: none; font-weight: 900;
  font-size: 15px; padding: 12px 24px; border-radius: 12px; cursor: pointer; }
.adslot { margin-top: 18px; min-height: 90px; width: 100%; max-width: 336px;
  display: flex; align-items: center; justify-content: center; }
```

- [ ] **Step 4 : Vérifier**

Bump `?v=21`, recharger, jouer quelques mots puis forcer la fin (`S.gauge=0`) ou attendre. Vérifier :
```javascript
S.zonesPlayed = ["strong","strong","weak","strong"]; S.wordCount = 4; S.score = 900;
endRun();
return { recap: document.getElementById('recap').textContent,
         grille: document.getElementById('sharegrid').textContent,
         a_bouton_partager: !!document.getElementById('share') };
```
Attendu : recap « 4 mots · survécu à 0 lettre… », grille `🟩🟩🟨🟩`, bouton présent.

- [ ] **Step 5 : Commit**

```bash
git add web/index.html web/app.js web/style.css
git commit -m "feat(fin): ecran de fin + carte de partage emoji"
```

---

### Task 9 : Deux saveurs (endless / défi du jour) sur l'écran de départ

**Files:**
- Modify: `web/index.html` (écran `#start` : deux boutons + slot pub)
- Modify: `web/app.js` (choix du mode -> `location.search`, ordre des lettres déterministe daily)

- [ ] **Step 1 : Deux boutons sur l'écran de départ**

Dans `#start`, remplacer le bouton unique par :
```html
    <div class="endbtns">
      <button id="playDaily">Défi du jour</button>
      <button id="play">Sans fin</button>
    </div>
    <div class="adslot adslot-start" id="adStart"><!-- AdSense (départ) --></div>
```

- [ ] **Step 2 : Câbler les modes**

Dans `app.js`, remplacer le listener `el.play` :
```javascript
el.play.addEventListener("click", () => startWith("random"));
$("playDaily").addEventListener("click", () => startWith("daily"));
function startWith(mode) {
  S.mode = mode;                       // mémorise pour l'ordre des lettres
  startRun();
}
```
Dans l'init de l'ordre des lettres (Task 2, Step 2), lire `S.mode` au lieu de l'URL :
```javascript
const rand = S.mode === "daily"
  ? Letters.rng(Letters.seedFromString(dateKey))
  : Math.random;
```
Et pour le mot de départ : `fetchSeed()` doit appeler `/api/seed?mode=${S.mode==="daily"?"daily":"random"}`. Positionner `S.mode` par défaut à `"random"` dans l'état.

- [ ] **Step 3 : Vérifier détermination du daily**

Bump `?v=22`, recharger. Simuler deux inits daily et comparer l'ordre :
```javascript
S.mode="daily"; const dk=(new Date()).toISOString().slice(0,10);
const o1=Letters.drawOrder(Letters.rng(Letters.seedFromString(dk)));
const o2=Letters.drawOrder(Letters.rng(Letters.seedFromString(dk)));
return { daily_identique: JSON.stringify(o1)===JSON.stringify(o2),
         boutons: !!document.getElementById('playDaily') && !!document.getElementById('play') };
```
Attendu : `daily_identique:true`, `boutons:true`.

- [ ] **Step 4 : Commit**

```bash
git add web/index.html web/app.js
git commit -m "feat(modes): defi du jour (deterministe) + sans fin, sur l'ecran de depart"
```

---

### Task 10 : Passe mobile-first + slots pub

**Files:**
- Modify: `web/style.css` (media queries mobile, tailles tactiles, slots pub)
- Modify: `web/index.html` (meta viewport déjà présent — vérifier)

- [ ] **Step 1 : Layout mobile**

Objectif : sur mobile, `bande lettres + mot courant + saisie` tiennent AU-DESSUS du clavier. Ajouter à `style.css` :
```css
@media (max-width: 560px) {
  #app { padding: 12px; }
  .current .word { font-size: clamp(34px, 12vw, 56px); }
  .forbid-letters .fl { width: 34px; height: 40px; font-size: 21px; }  /* cibles tactiles */
  #guess { font-size: 18px; padding: 14px 14px; }
  .hud .val { font-size: 26px; }
  /* les jauges rareté/vitesse + portail passent sous la saisie, compacts */
  .detail, .portal { margin-bottom: 10px; }
  .end .b2, .beat .b2 { font-size: 44px; }
  .adslot-end, .adslot-start { min-height: 100px; }
}
```

- [ ] **Step 2 : Slots pub (conteneurs prêts, code AdSense à ajouter par le proprio)**

Les slots `#adStart` et `#adEnd` existent déjà (Task 8/9). Ajouter un commentaire clair dans `index.html` près de chacun :
```html
<!-- Emplacement AdSense : coller ici le <ins class="adsbygoogle"> + le script.
     JAMAIS près de la saisie/boutons de jeu (mis-clic = violation policy). -->
```
Pas de footer pub en jeu sur mobile (le clavier le masque). Desktop : un footer optionnel pourra être ajouté plus tard.

- [ ] **Step 3 : Vérifier (responsive)**

Bump `?v=23`. `resize_window {preset:"mobile"}` (375×812), recharger, jouer :
```javascript
// vérifie qu'il n'y a pas de scroll horizontal et que la saisie est visible
return { scroll_h: document.documentElement.scrollWidth <= window.innerWidth + 1,
         saisie_visible: document.getElementById('guess').getBoundingClientRect().top < window.innerHeight };
```
Attendu : `scroll_h:true`, `saisie_visible:true`. Faire une capture (`computer screenshot`) pour contrôle visuel.

- [ ] **Step 4 : Commit**

```bash
git add web/style.css web/index.html
git commit -m "feat(mobile): passe responsive mobile-first + slots pub depart/fin"
```

---

## Self-Review (couverture du spec)

- Mécanique lettre interdite + escalade +1/10 → Tasks 1,2,3,4. ✓
- Tirage pondéré rareté + accents repliés + déterminisme daily → Task 1, 9. ✓
- Refus sans casser le combo → Task 3. ✓
- Compteur N/10 → Task 4. ✓
- Clignotement lettre au refus + highlight live saisie → Task 5. ✓
- Beat nouvelle lettre → Task 6. ✓
- Scoring direct (retrait bank-or-push), jauges rareté/vitesse gardées → Task 7 (les jauges ne sont PAS touchées, donc conservées ✓). ✓
- Écran de fin + carte de partage emoji → Task 8. ✓
- Endless + défi du jour → Task 9. ✓
- Mobile-first + slots pub (départ/fin, jamais près saisie) → Task 10. ✓
- Hors périmètre (target-word, leaderboard serveur, son) → non planifié, conforme au spec. ✓

**Points d'attention à l'exécution :**
- Bien **bumper `?v=`** et recharger avec `?cb=` à chaque tâche (le HTML est `no-cache` désormais, mais les assets versionnés doivent changer de version).
- Les stubs (`flashForbidden`, `maybeEscalate`, `newForbiddenBeat`) sont posés tôt puis remplis — ne pas oublier de retirer les stubs quand la vraie fonction arrive.
- L'URL de partage (Task 8) doit être mise à jour avec le vrai domaine Railway.
