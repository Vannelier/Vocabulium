"use strict";

const $ = (id) => document.getElementById(id);
const el = {
  score: $("score").querySelector(".val"),
  pnum: $("pnum"),
  rank: $("rank"), rankltr: $("rankltr"), mult: $("mult"),
  jeop: $("jeop"),
  gauge: $("timerbar"),
  trail: $("trail"),
  current: $("current"),
  guess: $("guess"),
  toast: $("toast"),
  beat: $("beat"),
  detail: $("detail"),
  dword: $("dword"), dpts: $("dpts"),
  bRar: $("b-rar"), bSpeed: $("b-speed"),
  vRar: $("v-rar"), vSpeed: $("v-speed"),
  portal: $("portal"), pprox: $("pprox"), pverdict: $("pverdict"), pmark: $("pmark"),
  pzRej: $("pz-rej"), pzFar: $("pz-far"), pzSweet: $("pz-sweet"), pzSyno: $("pz-syno"),
  end: $("end"), final: $("final"), recap: $("recap"),
  sharegrid: $("sharegrid"), share: $("share"),
  menu: $("menu"), start: $("start"), play: $("play"),
  forbidLetters: $("forbidLetters"), forbidNext: $("forbidNext"),
  recordbeat: $("recordbeat"), endrecord: $("endrecord"),
  cible: $("cible"), cibleWord: $("cibleWord"), cibleBonus: $("cibleBonus"),
  hiscore: $("hiscore"), brand: $("brand"), levelflash: $("levelflash"),
};

let cfg = {
  tau: 0.30, tau_grace: 0.22, combo_step: 0.18, combo_floor: 0.4, mult_max: 4.0,
  gauge_seconds: 15, weak_refill: 0.45,
};
let seedWord = null;

const S = {
  mode: "random",
  current: null, played: new Set(), score: 0, mult: 1, rankIndex: 0, rankFill: 0,
  lastHopTs: 0, started: false, running: false,
  gauge: 1, lastFrame: 0, hops: 0, weakHops: 0, misses: 0, bestBridge: null,
  forbiddenOrder: [], wordCount: 0, zonesPlayed: [],
  best: 0, recordBeaten: false,
  target: null, targetBonus: 0, captures: 0,
};

const BEST_KEY = "Vocabulium_best";
const loadBest = () => Number(localStorage.getItem(BEST_KEY) || 0);

const MISS_LIMIT = 2;   // 1er raté : le rang chute d'un cran · 2e raté consécutif : shatter
const RARE_THRESHOLD = 0.6;   // au-delà : juice "rare" (étincelles + glow)
const RARE_HI = 0.85;         // au-delà : juice renforcé "très rare"

// --- Rang (le multiplicateur relooké : D -> SSS, la lettre EST la jauge) -----
const RANK_NAMES = ["D", "C", "B", "A", "S", "SS", "SSS"];
const RANK_MULT  = [1.0, 1.4, 1.8, 2.3, 3.0, 4.0, 5.5];
const RANK_COLOR = ["#9385c4", "#20ffb2", "#22e6ff", "#b25cff", "#ffd23f", "#ff7a2f", "#ff2e5b"];
// Remplissage du rang (le palier monte VITE). Un hop fort remplit selon sa
// QUALITÉ = rareté + vitesse : amount = FILL_STEP * (FILL_FLOOR + rareté + FILL_SPEED*vitesse).
// Un mot rare ET donné rapidement (rareté~1, vitesse~1) dépasse 1.0 -> prend un
// palier entier d'un coup (le surplus est reporté par addFill).
const FILL_STEP = 0.6, FILL_FLOOR = 0.5, FILL_SPEED = 0.6, FILL_WEAK = 0.12, DROP_FILL = 0.30;
// Capture du mot bonus : remplit EN PLUS le rang, proportionnellement à la rareté
// du bonus (300 -> ~0.45 palier, 600 -> ~0.9 palier). Le plus rare des bonus.
const CAPTURE_FILL_MAX = 0.9, TARGET_BONUS_TOP = 600;
const captureFill = (bonus) => CAPTURE_FILL_MAX * Math.min(1, bonus / TARGET_BONUS_TOP);

const LETTER_EVERY = 5;           // une nouvelle lettre interdite tous les 5 mots
const START_FORBIDDEN = 0;        // aucune lettre interdite au départ (la 1re arrive après LETTER_EVERY mots)
const FIRST_GAUGE_FACTOR = 2.0;   // le 1er chrono dure 2× plus longtemps (le temps de comprendre)

// --- init -------------------------------------------------------------------
async function fetchSeed() {
  const r = await fetch(`/api/seed?mode=${S.mode === "daily" ? "daily" : "random"}`).then((x) => x.json());
  seedWord = r.word;
  cfg = { ...cfg, ...r.config };

  // mode "daily" -> ordre déterministe depuis la date ; sinon aléatoire local.
  const mode = S.mode;
  const dateKey = (new Date()).toISOString().slice(0, 10);
  const rand = mode === "daily"
    ? Letters.rng(Letters.seedFromString(dateKey))
    : Math.random;
  S.forbiddenOrder = Letters.drawOrder(rand);
}

// Prépare une partie (mot, état) MAIS ne lance rien : input désactivé, chrono à
// l'arrêt. Le chrono ne partira qu'au clic sur Jouer/Rejouer (startRun).
async function prepareRun() {
  await fetchSeed();
  Object.assign(S, {
    current: seedWord, played: new Set([seedWord]),
    score: 0, mult: 1, rankIndex: 0, rankFill: 0, lastHopTs: 0,
    started: false, running: false, gauge: 1, lastFrame: 0,
    hops: 0, weakHops: 0, misses: 0, bestBridge: null, wordCount: 0,
    zonesPlayed: [], best: loadBest(), recordBeaten: false,
    target: null, targetBonus: 0, captures: 0,
  });
  el.trail.innerHTML = "";
  el.current.textContent = seedWord;
  el.guess.value = ""; el.guess.disabled = true;
  el.end.classList.remove("show");
  el.pnum.classList.remove("record");
  el.hiscore.textContent = S.best;
  el.gauge.style.transform = "scaleX(1)";
  el.detail.className = "detail";
  el.dword.textContent = "—"; el.dpts.textContent = "";
  setupGate();
  renderGate(null);
  setBars(0, 0, true);
  renderHud();
  renderRank(true);
  await fetchTarget();     // cible initiale (fetchTarget rend aussi la bande + les lettres)
  renderForbidden();
}

// Lance la partie : le chrono démarre ICI (au clic), pas au premier mot. Le
// premier hop est donc chronométré depuis ce clic -> plus de vitesse gratuite.
function startRun() {
  el.start.classList.remove("show");
  S.running = true;
  S.started = true;
  S.lastFrame = performance.now();
  S.lastHopTs = performance.now();
  el.guess.disabled = false;
  el.guess.focus();
  requestAnimationFrame(tick);
}

// --- rendering --------------------------------------------------------------
function renderHud() {
  el.pnum.textContent = Math.round(S.score);
  // Une fois le record dépassé en jeu, le compteur du header grimpe avec le score.
  if (S.recordBeaten) el.hiscore.textContent = Math.round(S.score);
}

// High score : dès que le score EN COURS dépasse le record précédent (>0), on le
// fête une seule fois — bannière dorée plein écran + score qui pulse en or. S'il
// n'y avait pas de record antérieur, on ne déclenche rien en jeu (rien à battre).
function maybeRecord() {
  if (S.recordBeaten || S.best <= 0) return;
  if (S.score > S.best) {
    S.recordBeaten = true;
    recordFlash();
  }
}
function recordFlash() {
  el.recordbeat.innerHTML = `<div class="rb1">★ nouveau record ★</div>`;
  el.recordbeat.classList.remove("play"); void el.recordbeat.offsetWidth;
  el.recordbeat.classList.add("play");
  el.pnum.classList.remove("record"); void el.pnum.offsetWidth;
  el.pnum.classList.add("record");     // le nombre reste doré : on tient le record
  el.hiscore.classList.remove("bump"); void el.hiscore.offsetWidth;
  el.hiscore.classList.add("bump");    // le record du header tressaute au passage
}

// --- Rang : la lettre-jauge. `S.mult` reste le MIROIR de RANK_MULT[rankIndex]
// pour ne rien changer à la ligne de scoring (gained = hop_points * S.mult).
function syncMult() { S.mult = RANK_MULT[S.rankIndex]; }
// instant=true : coupe la transition du remplissage (changement de lettre) ;
// sinon le remplissage GLISSE jusqu'à sa nouvelle valeur.
function renderRank(instant) {
  const i = S.rankIndex, col = RANK_COLOR[i];
  el.rankltr.dataset.l = RANK_NAMES[i];
  el.rankltr.textContent = RANK_NAMES[i];
  el.rank.style.setProperty("--rank-color", col);
  el.mult.textContent = "×" + RANK_MULT[i].toFixed(2);
  el.mult.style.color = col;
  el.rank.classList.toggle("hot", i >= 5);   // SS/SSS : pulse "en feu"
  const pct = (Math.max(0, Math.min(1, S.rankFill)) * 100).toFixed(1) + "%";
  if (instant) {
    el.rank.classList.add("instant");
    el.rank.style.setProperty("--rank-fill", pct);
    void el.rankltr.offsetWidth;              // commit sans transition
    el.rank.classList.remove("instant");
  } else {
    el.rank.style.setProperty("--rank-fill", pct);   // glisse (transition CSS)
  }
}
// Relance une animation CSS (retire la classe, reflow, remet).
function replay(elm, cls) { elm.classList.remove(cls); void elm.offsetWidth; elm.classList.add(cls); }
function screenShake(kind) {              // "s" | "m" | "l"
  const c = "shake-" + kind, app = document.getElementById("app");
  app.classList.remove("shake-s", "shake-m", "shake-l"); void app.offsetWidth; app.classList.add(c);
  setTimeout(() => app.classList.remove(c), 450);
}
// Flash plein écran à la couleur du NOUVEAU rang : gros pop visuel au level-up.
function flashLevel() {
  el.levelflash.style.background = RANK_COLOR[S.rankIndex];
  replay(el.levelflash, "play");
}
function rankUp() { replay(el.rankltr, "slam"); flashLevel(); screenShake("m"); }
// Remplit la lettre ; déborde -> monte d'un rang (report du surplus). Plafonné à SSS.
function addFill(amount) {
  let leveled = false;
  S.rankFill += amount;
  while (S.rankFill >= 1 - 1e-9 && S.rankIndex < RANK_NAMES.length - 1) {
    S.rankFill = Math.max(0, S.rankFill - 1); S.rankIndex += 1; leveled = true; rankUp();
  }
  if (S.rankIndex >= RANK_NAMES.length - 1) S.rankFill = Math.min(S.rankFill, 1);
  syncMult(); renderRank(leveled);            // glisse si pas de rang-up ; instantané sinon
  if (!leveled) replay(el.rankltr, "bump");   // pas de rang-up : simple rebond
}
function rankDown() {
  if (S.rankIndex > 0) { S.rankIndex -= 1; S.rankFill = DROP_FILL; }
  else S.rankFill = 0;                        // déjà à D : on vide, sans descendre
  syncMult(); renderRank(true);
  replay(el.rankltr, "crack"); screenShake("s");
}
function shatter() {
  S.rankIndex = 0; S.rankFill = 0; syncMult(); renderRank(true);
  replay(el.rankltr, "shatter"); screenShake("l");
}

// Un mot refusé (trop loin) ou inexistant (typo) : filet en DEUX temps.
// 1er raté -> le rang chute d'un cran. 2e raté consécutif -> SHATTER (retour à D).
// Un bon mot réarme le filet (clearMisses).
function registerMiss() {
  S.misses += 1;
  if (S.misses >= MISS_LIMIT) { S.misses = 0; shatter(); }
  else rankDown();
}

function clearMisses() {
  S.misses = 0;
}

let synoRes = 0.457;   // seuil de ressemblance = onset synonyme (recalé depuis cfg)

// LE SCORE : les deux jauges (rareté, vitesse).
function setBars(rar, speed, blank) {
  el.bRar.style.width = rar * 100 + "%";
  el.bSpeed.style.width = speed * 100 + "%";
  const f = (x) => blank ? "—" : x.toFixed(2);
  el.vRar.textContent = f(rar);
  el.vSpeed.textContent = f(speed);
}

// Le portail : où tombe la proximité (rejet / un peu loin / sweet spot / trop proche).
function setupGate() {
  el.pzRej.style.width = (cfg.tau_grace * 100) + "%";
  el.pzFar.style.width = ((cfg.tau - cfg.tau_grace) * 100) + "%";
  el.pzSweet.style.width = ((cfg.syno - cfg.tau) * 100) + "%";
  el.pzSyno.style.width = ((1 - cfg.syno) * 100) + "%";
  synoRes = (cfg.syno - cfg.tau) / (1 - cfg.tau);
}

// Le portail = proximité AVEC la ressemblance fusionnée : une dérivation (racine
// commune) a un cosinus moyen mais est un ÉCHO -> on pousse le curseur dans la
// zone "trop proche". Le curseur montre donc la closeness EFFECTIVE.
function renderGate(prox, zone, reason) {
  el.pprox.textContent = prox == null ? "—" : prox.toFixed(2);
  const echo = reason === "root";                        // écho malgré un cosinus moyen
  const pos = echo ? Math.max(prox || 0, cfg.syno + (1 - cfg.syno) * 0.45) : (prox || 0);
  el.pmark.style.left = Math.max(0, Math.min(100, pos * 100)) + "%";
  el.portal.classList.toggle("echo", echo || (prox != null && prox >= cfg.syno));
  let txt = "", col = "";
  if (prox != null) {
    if (zone === "reject")        { txt = "✗ trop loin";  col = "var(--bail)"; }
    else if (reason === "root")   { txt = "⚠ écho (même racine)"; col = "var(--bail)"; }
    else if (reason === "syno")   { txt = "⚠ trop proche"; col = "var(--bail)"; }
    else if (reason === "far")    { txt = "⚠ un peu loin"; col = "var(--warm)"; }
    else                          { txt = "✓ pont valide"; col = "var(--bank)"; }
  }
  el.pverdict.textContent = txt;
  el.pverdict.style.color = col;
}

function showDetail(res, gained, zone) {
  el.detail.className = "detail live" + (zone === "strong" ? "" : " " + zone);
  renderGate(res.prox, zone, res.reason);
  if (zone === "reject") {
    el.dword.innerHTML = `${res.input || res.word} <small>trop loin</small>`;
    el.dpts.textContent = "—";
    setBars(0, 0);
    return;
  }
  const weakTag = zone !== "weak" ? ""
    : res.reason === "root" ? "écho — même racine"
    : res.reason === "syno" ? "trop proche (synonyme)"
    : "un peu loin";
  el.dword.innerHTML =
    `${res.word} <small style="color:var(--muted)">${weakTag || "pont valide"}</small>`;
  el.dpts.textContent = "+" + Math.round(gained);
  setBars(res.rarete, res.speed);
}

function pushTrail(word, hot, weak, gained) {
  if (el.trail.children.length) {
    const sep = document.createElement("span");
    sep.className = "sep"; sep.textContent = "→";
    el.trail.appendChild(sep);
  }
  const w = document.createElement("span");
  w.className = "w" + (hot ? " hot" : "") + (weak ? " weak" : "");
  w.textContent = word;
  const p = document.createElement("span");
  p.className = "p"; p.textContent = "+" + Math.round(gained);
  w.appendChild(p);
  el.trail.appendChild(w);
  trimTrail();
}

// Garde la trace à ~3 lignes max : tant que ça déborde, on retire les plus
// vieux (FIFO) — le mot et son séparateur — pour que l'écran ne soit pas envahi.
function trimTrail() {
  while (el.trail.scrollHeight > el.trail.clientHeight + 1
         && el.trail.children.length > 1) {
    el.trail.removeChild(el.trail.firstChild);                     // mot le plus ancien
    if (el.trail.firstChild && el.trail.firstChild.classList.contains("sep"))
      el.trail.removeChild(el.trail.firstChild);                   // son séparateur
  }
}

function toastScore(n, cls, rare) {
  rare = rare || 0;
  const tag = rare >= RARE_HI ? '<div class="sub rare">✦✦ TRÈS RARE</div>'
    : rare >= RARE_THRESHOLD ? '<div class="sub rare">✦ RARE</div>' : "";
  el.toast.className = "toast pop " + (cls || "") + (rare >= RARE_THRESHOLD ? " rare" : "");
  el.toast.innerHTML = `<div class="big">+${Math.round(n)}</div>${tag}`;
  el.toast.style.animation = "none"; void el.toast.offsetWidth;
  el.toast.style.animation = "";
}

// Juice quand le mot est rare : glow doré sur le mot + gerbe d'étincelles,
// intensité ∝ rareté.
function rareJuice(rarity) {
  const w = el.current;
  w.classList.remove("rareglow"); void w.offsetWidth; w.classList.add("rareglow");
  const n = Math.round(8 + rarity * 16);
  for (let i = 0; i < n; i++) {
    const s = document.createElement("i");
    s.className = "spark";
    const ang = Math.random() * Math.PI * 2;
    const dist = (36 + Math.random() * 80) * (0.6 + rarity);
    s.style.setProperty("--dx", (Math.cos(ang) * dist).toFixed(0) + "px");
    s.style.setProperty("--dy", (Math.sin(ang) * dist).toFixed(0) + "px");
    s.style.animationDelay = (Math.random() * 0.08).toFixed(3) + "s";
    w.appendChild(s);
    setTimeout(() => s.remove(), 820);
  }
}
function shake() {
  el.guess.classList.add("shake");
  setTimeout(() => el.guess.classList.remove("shake"), 300);
}

// Le mot était trop loin -> on n'avance pas, le mot d'ancrage reste le même.
// On le fait pulser une fois en bleu pour montrer qu'il n'a PAS changé.
function blinkUnchanged() {
  el.current.classList.remove("samehold");
  void el.current.offsetWidth;
  el.current.classList.add("samehold");
}

// Lettres (repliées, dédupliquées) de la cible — jamais interdites.
function targetLetters() {
  return S.target ? [...new Set([...S.target].map(Letters.fold))] : [];
}
function activeForbidden() {
  return Letters.activeForbidden(S.forbiddenOrder, S.wordCount, LETTER_EVERY,
                                 START_FORBIDDEN, targetLetters());
}
function renderTarget() {
  if (!S.target) { el.cible.style.display = "none"; return; }
  el.cible.style.display = "";
  el.cibleWord.textContent = S.target;
  el.cibleBonus.textContent = "+" + S.targetBonus;
}
// Tire une nouvelle cible : rare, sans lettre interdite active, pas déjà jouée.
async function fetchTarget() {
  const avoid = activeForbidden().join("");
  for (let tries = 0; tries < 4; tries++) {
    let r;
    try {
      r = await fetch(`/api/target?current=${encodeURIComponent(S.current)}`
        + `&avoid=${avoid}&captures=${S.captures}`).then((x) => x.json());
    } catch (e) { return; }
    if (!r.word) { S.target = null; break; }
    if (!S.played.has(r.word)) { S.target = r.word; S.targetBonus = r.bonus_base; break; }
  }
  renderTarget();
  renderForbidden();   // la protection dépend de la cible -> re-render
}

function renderForbidden() {
  const active = activeForbidden();
  el.forbidLetters.innerHTML =
    active.map(L => `<span class="fl" data-l="${L}">${L}</span>`).join("");
  const into = LETTER_EVERY - (S.wordCount % LETTER_EVERY);
  el.forbidNext.textContent = "prochaine dans " + into;
}

function flashForbidden(letters) {
  for (const L of letters) {
    const el2 = el.forbidLetters.querySelector(`.fl[data-l="${L}"]`);
    if (el2) { el2.classList.remove("blink"); void el2.offsetWidth; el2.classList.add("blink"); }
  }
}
function newForbiddenBeat(letter) {
  el.beat.innerHTML = `<div class="b1">⛔ lettre interdite</div><div class="b2">${letter}</div>`;
  el.beat.classList.remove("play"); void el.beat.offsetWidth; el.beat.classList.add("play");
}

// Appelé après chaque mot accepté : détecte le franchissement d'un palier de 10.
function maybeEscalate() {
  const before = Letters.forbiddenCount(S.wordCount - 1, LETTER_EVERY, START_FORBIDDEN);
  const after = Letters.forbiddenCount(S.wordCount, LETTER_EVERY, START_FORBIDDEN);
  if (after > before) newForbiddenBeat(activeForbidden()[after - 1]);
  renderForbidden();
}

// --- gauge loop -------------------------------------------------------------
function tick(now) {
  if (!S.running) return;
  const dt = (now - S.lastFrame) / 1000;
  S.lastFrame = now;
  // Le TOUT premier chrono (avant le 1er mot posé) est allongé en douce, pour
  // laisser le temps de comprendre. Rien n'est affiché : la jauge se vide juste
  // plus lentement tant que wordCount === 0, puis revient à la normale.
  const secs = cfg.gauge_seconds * (S.wordCount === 0 ? FIRST_GAUGE_FACTOR : 1);
  S.gauge = Math.max(0, S.gauge - dt / secs);
  el.gauge.style.transform = `scaleX(${S.gauge})`;
  if (S.gauge <= 0) return endRun();
  requestAnimationFrame(tick);
}

// --- game actions -----------------------------------------------------------
async function submitHop() {
  const raw = el.guess.value.trim();
  if (!raw) { el.guess.focus(); return; }
  if (!S.running) return;

  const active = activeForbidden();
  const offending = Letters.offendingLetters(raw.toLowerCase(), active);
  if (offending.length) {
    // refusé : ni raté, ni casse de combo. Juste illégal -> feedback + retry.
    flashForbidden(offending);
    shake();
    el.guess.value = "";
    return;                             // la jauge continue de tourner (le coût = temps)
  }

  const t = (performance.now() - S.lastHopTs) / 1000;
  let res;
  try {
    res = await fetch("/api/hop", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prev: S.current, next: raw, t }),
    }).then((x) => x.json());
  } catch (e) { return; }
  if (!S.running) return;

  if (!res.valid) {
    // Refus "doux" (même mot, ou son singulier/pluriel) : c'est une contrainte,
    // pas une faute -> ni raté ni casse de combo. Un mot inconnu (typo) reste un raté.
    const soft = res.reason === "same_word" || res.reason === "same_lemma";
    const msg = res.reason === "same_lemma" ? "même mot (sing./plur.)"
              : res.reason === "same_word" ? "même mot"
              : "mot inconnu";
    el.dword.innerHTML = `${res.input || res.word || raw} <small>${msg}</small>`;
    el.dpts.textContent = ""; el.detail.className = "detail live reject";
    renderGate(null); setBars(0, 0, true);
    if (!soft) registerMiss();
    shake(); blinkUnchanged();
    el.guess.value = ""; return;
  }
  if (S.played.has(res.word)) {              // déjà joué : contrainte, pas une faute
    el.dword.innerHTML = `${res.word} <small>déjà joué</small>`;
    el.dpts.textContent = ""; el.detail.className = "detail live reject";
    shake(); return;
  }

  if (res.zone === "reject") {               // trop loin : compte comme un raté (filet)
    showDetail(res, 0, "reject");
    registerMiss(); shake(); blinkUnchanged(); el.guess.value = "";
    return;
  }

  // hop accepté (strong ou weak) : réarme le filet
  clearMisses();
  const gained = res.hop_points * S.mult;
  S.score += gained;
  S.played.add(res.word);
  S.wordCount += 1;
  S.zonesPlayed.push(res.zone === "strong" ? "strong" : "weak");
  maybeEscalate();
  S.current = res.word;
  S.lastHopTs = performance.now();
  el.current.textContent = res.word;
  el.guess.value = "";

  if (res.zone === "strong") {
    // le rang monte selon la QUALITÉ du hop (rareté + vitesse) -> qualité > longueur.
    // Un mot rare donné vite peut franchir un palier d'un seul hop.
    addFill(FILL_STEP * (FILL_FLOOR + res.rarete + FILL_SPEED * res.speed));
    S.gauge = 1;                             // recharge pleine
    S.hops += 1;
  } else {                                   // weak : petit remplissage seulement
    addFill(FILL_WEAK);
    S.gauge = Math.max(S.gauge, cfg.weak_refill);
    S.weakHops += 1;
  }
  el.gauge.style.transform = `scaleX(${S.gauge})`;

  let captureBonus = 0;
  if (res.word === S.target) {                   // CAPTURE : mot bonus exact & accepté
    captureBonus = S.targetBonus;                // fixe et prédictible, EN PLUS des points du mot
    S.score += captureBonus;
    addFill(captureFill(S.targetBonus));         // ... et fait aussi grimper le palier
    S.captures += 1;
    el.cible.classList.remove("captured"); void el.cible.offsetWidth;
    el.cible.classList.add("captured");
    await fetchTarget();                          // nouvelle cible (plus rare) + re-render protection
  }

  const hot = res.zone === "strong" && res.rarete >= 0.55;
  if (res.zone === "strong" && (!S.bestBridge || gained > S.bestBridge.points))
    S.bestBridge = { word: res.word, points: gained };

  pushTrail(res.word, hot, res.zone === "weak", gained);
  showDetail(res, gained, res.zone);
  toastScore(gained, res.zone === "weak" ? "weakt" : "", res.rarete);
  if (res.rarete >= RARE_THRESHOLD) rareJuice(res.rarete);
  renderHud();
  if (!el.pnum.classList.contains("record")) replay(el.pnum, "pop");
  maybeRecord();
  if (captureBonus) toastScore(captureBonus, "", 1);   // le toast capture prime sur celui du hop
}

function endRun() {
  S.running = false;
  renderHud();
  el.guess.disabled = true;

  const prev = S.best;                          // record AU DÉBUT de cette partie
  const score = Math.round(S.score);
  const beaten = prev > 0 && score > prev;      // record existant battu ?
  const best = Math.max(prev, score);
  localStorage.setItem(BEST_KEY, String(best));
  el.hiscore.textContent = best;

  el.endrecord.classList.remove("hit");
  if (beaten) {
    el.endrecord.innerHTML = `★ nouveau record ★ <b>${best}</b>`;
    void el.endrecord.offsetWidth; el.endrecord.classList.add("hit");
  } else if (prev <= 0) {
    el.endrecord.innerHTML = `premier record <b>${best}</b>`;
  } else {
    el.endrecord.innerHTML = `record à battre <b>${best}</b>`;
  }

  const letters = Letters.forbiddenCount(S.wordCount, LETTER_EVERY, START_FORBIDDEN);
  el.final.textContent = Math.round(S.score);
  el.recap.innerHTML = `${S.wordCount} mots · survécu à <b>${letters}</b> lettre${letters>1?'s':''} interdite${letters>1?'s':''}`;
  const grid = S.zonesPlayed.map(z => z === "strong" ? "🟩" : "🟨");
  const rows = [];
  for (let i = 0; i < grid.length; i += 10) rows.push(grid.slice(i, i + 10).join(""));
  const share = `Vocabulium — ${S.wordCount} mots, ${letters} lettres interdites 🔥\n`
    + rows.join("\n") + `\n${location.host}`;
  el.sharegrid.textContent = rows.join("\n");
  el.share.onclick = () => {
    if (navigator.share) navigator.share({ text: share }).catch(() => {});
    else navigator.clipboard.writeText(share).then(() => (el.share.textContent = "Copié !"));
  };
  el.end.classList.add("show");
}

// --- clavier virtuel mobile -------------------------------------------------
// Le vrai problème : beaucoup de navigateurs mobiles ne redimensionnent PAS la
// page quand le clavier s'ouvre — il la RECOUVRE. La page reste haute (100dvh ne
// tient pas compte du clavier) donc non défilable, et la saisie est piégée sous
// le clavier. On force alors la hauteur du body à la zone RÉELLEMENT visible
// (visualViewport) : le body devient un conteneur défilable calé au-dessus du
// clavier, et on y ramène la saisie. Sur les navigateurs qui redimensionnent
// déjà (Chrome interactive-widget), l'opération est neutre.
(function mobileKeyboard() {
  const vv = window.visualViewport;
  if (!vv) return;
  const sync = () => {
    const h = vv.height + "px";
    document.body.style.height = h;
    document.body.style.minHeight = h;     // écrase le 100dvh, sinon la page reste trop haute
  };
  const reveal = () => {
    if (document.activeElement === el.guess)
      el.guess.scrollIntoView({ block: "end", behavior: "smooth" });
  };
  vv.addEventListener("resize", () => { sync(); setTimeout(reveal, 60); });
  vv.addEventListener("scroll", sync);
  el.guess.addEventListener("focus", () => setTimeout(reveal, 250));
  sync();
})();

// --- events -----------------------------------------------------------------
el.guess.addEventListener("keydown", (e) => {
  if (e.key === "Enter") { e.preventDefault(); submitHop(); }
});
el.guess.addEventListener("input", () => {
  const bad = Letters.offendingLetters(el.guess.value.toLowerCase(), activeForbidden());
  el.guess.classList.toggle("hasforbidden", bad.length > 0);
});
el.play.addEventListener("click", () => startWith("random"));
document.getElementById("playDaily").addEventListener("click", () => startWith("daily"));
async function startWith(mode) {
  S.mode = mode;
  await prepareRun();     // re-fetch le seed + re-tire les lettres selon le mode choisi
  startRun();
}
// Retour au menu : stoppe une partie en cours (le chrono s'arrête) et montre l'écran des modes.
function goToMenu() {
  S.running = false;
  el.guess.disabled = true;
  el.end.classList.remove("show");
  el.start.classList.add("show");
}
el.menu.addEventListener("click", goToMenu);
// Le titre "Vocabulium" du header ramène au menu (clic ou Entrée/Espace au clavier).
el.brand.addEventListener("click", goToMenu);
el.brand.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); goToMenu(); }
});

// Au chargement : on prépare la partie et on montre l'écran "Jouer" (chrono à l'arrêt).
prepareRun().then(() => el.start.classList.add("show"));
