"use strict";

const $ = (id) => document.getElementById(id);
const el = {
  score: $("score").querySelector(".val"),
  pnum: $("pnum"),
  mult: $("mult"),
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
  end: $("end"), final: $("final"), best: $("best"), recap: $("recap"),
  sharegrid: $("sharegrid"), share: $("share"),
  again: $("again"), start: $("start"), play: $("play"),
  forbidLetters: $("forbidLetters"), forbidNext: $("forbidNext"),
};

let cfg = {
  tau: 0.30, tau_grace: 0.22, combo_step: 0.18, combo_floor: 0.4, mult_max: 4.0,
  gauge_seconds: 15, weak_refill: 0.45,
};
let seedWord = null;

const S = {
  current: null, played: new Set(), score: 0, mult: 1,
  lastHopTs: 0, started: false, running: false,
  gauge: 1, lastFrame: 0, hops: 0, weakHops: 0, misses: 0, bestBridge: null,
  forbiddenOrder: [], wordCount: 0, zonesPlayed: [],
};

const MISS_LIMIT = 2;   // 1er raté : le mult tressaille · 2e raté consécutif : reset ×1
const RARE_THRESHOLD = 0.6;   // au-delà : juice "rare" (étincelles + glow)
const RARE_HI = 0.85;         // au-delà : juice renforcé "très rare"
const LETTER_EVERY = 10;

// --- init -------------------------------------------------------------------
async function fetchSeed() {
  const r = await fetch("/api/seed?mode=random").then((x) => x.json());
  seedWord = r.word;
  cfg = { ...cfg, ...r.config };

  // mode "daily" -> ordre déterministe depuis la date ; sinon aléatoire local.
  const mode = new URLSearchParams(location.search).get("mode") || "random";
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
    score: 0, mult: 1, lastHopTs: 0,
    started: false, running: false, gauge: 1, lastFrame: 0,
    hops: 0, weakHops: 0, misses: 0, bestBridge: null, wordCount: 0,
    zonesPlayed: [],
  });
  el.trail.innerHTML = "";
  el.current.textContent = seedWord;
  el.guess.value = ""; el.guess.disabled = true;
  el.end.classList.remove("show");
  el.gauge.style.transform = "scaleX(1)";
  el.detail.className = "detail";
  el.dword.textContent = "—"; el.dpts.textContent = "";
  setupGate();
  renderGate(null);
  setBars(0, 0, true);
  renderHud();
  renderMult(null);
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
}

// Le multiplicateur, avec juice. evt: "grow" (montée), "warn" (1er raté, tressaille),
// "break" (retour ×1), null (silencieux : reset encaissement / init).
let _tilt = 1;   // signe d'inclinaison, alterné à chaque montée -> l'orientation change
function renderMult(evt) {
  const m = S.mult;
  el.mult.textContent = "×" + m.toFixed(2);
  const t = Math.max(0, Math.min(1, (m - 1) / (cfg.mult_max - 1)));  // ×1..MAX -> 0..1
  el.mult.style.setProperty("--s", (1 + t * 0.95).toFixed(3));       // plus gros à mesure que ça monte
  if (m <= 1.001) {
    el.mult.style.color = "";                         // -> muted (CSS de base)
    el.mult.style.textShadow = "none";
  } else {
    el.mult.style.color = `hsl(${Math.round(42 * (1 - t))},100%,${Math.round(62 - t * 12)}%)`;
    el.mult.style.textShadow =
      `0 0 ${Math.round(6 + t * 32)}px rgba(255,${(130 - t * 130) | 0},40,${(0.4 + t * 0.55).toFixed(2)})`;
  }
  el.mult.classList.remove("bump", "brk", "warn");
  if (evt === "grow") {
    _tilt = -_tilt;                                   // alterne l'orientation du pop
    el.mult.style.setProperty("--tilt", _tilt);
    void el.mult.offsetWidth; el.mult.classList.add("bump");
  } else if (evt === "warn") {
    void el.mult.offsetWidth; el.mult.classList.add("warn");
  } else if (evt === "break") {
    void el.mult.offsetWidth; el.mult.classList.add("brk");
  }
}

function breakCombo() {
  if (S.mult > 1.001) { S.mult = 1; renderMult("break"); renderHud(); }
}

// Un mot refusé (trop loin) ou inexistant (typo) : filet en DEUX temps, sans texte.
// 1er raté  -> le multiplicateur tressaille (avertissement) mais tient.
// 2e raté   -> il casse et retombe à ×1. Un bon mot réarme le filet.
function registerMiss() {
  S.misses += 1;
  if (S.misses >= MISS_LIMIT) { S.misses = 0; breakCombo(); }
  else if (S.mult > 1.001) { renderMult("warn"); }
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

function activeForbidden() {
  return Letters.activeForbidden(S.forbiddenOrder, S.wordCount, LETTER_EVERY);
}

function renderForbidden() {
  const active = activeForbidden();
  const box = el.forbidLetters;
  box.innerHTML = active.length
    ? active.map(L => `<span class="fl" data-l="${L}">${L}</span>`).join("")
    : `<span class="forbid-empty">aucune — profite !</span>`;
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
  const before = Letters.forbiddenCount(S.wordCount - 1, LETTER_EVERY);
  const after = Letters.forbiddenCount(S.wordCount, LETTER_EVERY);
  if (after > before) newForbiddenBeat(activeForbidden()[after - 1]);
  renderForbidden();
}

// --- gauge loop -------------------------------------------------------------
function tick(now) {
  if (!S.running) return;
  const dt = (now - S.lastFrame) / 1000;
  S.lastFrame = now;
  S.gauge = Math.max(0, S.gauge - dt / cfg.gauge_seconds);
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

  if (!res.valid) {                          // mot hors vocab (typo) / identique
    el.dword.innerHTML = `${res.input || raw} <small>mot inconnu</small>`;
    el.dpts.textContent = ""; el.detail.className = "detail live reject";
    renderGate(null); setBars(0, 0, true); registerMiss(); shake();
    el.guess.value = ""; return;
  }
  if (S.played.has(res.word)) {              // déjà joué : contrainte, pas une faute
    el.dword.innerHTML = `${res.word} <small>déjà joué</small>`;
    el.dpts.textContent = ""; el.detail.className = "detail live reject";
    shake(); return;
  }

  if (res.zone === "reject") {               // trop loin : compte comme un raté (filet)
    showDetail(res, 0, "reject");
    registerMiss(); shake(); el.guess.value = "";
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
    // le combo monte selon la QUALITÉ du hop (surprise), plafonné -> qualité > longueur
    const gain = cfg.combo_step * (cfg.combo_floor + res.rarete);
    S.mult = Math.min(cfg.mult_max, S.mult + gain);
    S.gauge = 1;                             // recharge pleine
    S.hops += 1;
    renderMult("grow");
  } else {                                   // weak
    S.gauge = Math.max(S.gauge, cfg.weak_refill);
    S.weakHops += 1;
  }
  el.gauge.style.transform = `scaleX(${S.gauge})`;

  const hot = res.zone === "strong" && res.rarete >= 0.55;
  if (res.zone === "strong" && (!S.bestBridge || gained > S.bestBridge.points))
    S.bestBridge = { word: res.word, points: gained };

  pushTrail(res.word, hot, res.zone === "weak", gained);
  showDetail(res, gained, res.zone);
  toastScore(gained, res.zone === "weak" ? "weakt" : "", res.rarete);
  if (res.rarete >= RARE_THRESHOLD) rareJuice(res.rarete);
  renderHud();
}

function endRun() {
  S.running = false;
  renderHud();
  el.guess.disabled = true;

  const key = "Vocabulium_best";
  const prev = Number(localStorage.getItem(key) || 0);
  const best = Math.max(prev, S.score);
  localStorage.setItem(key, String(best));

  const letters = Letters.forbiddenCount(S.wordCount, LETTER_EVERY);
  el.final.textContent = Math.round(S.score);
  el.recap.innerHTML = `${S.wordCount} mots · survécu à <b>${letters}</b> lettre${letters>1?'s':''} interdite${letters>1?'s':''}`;
  const grid = S.zonesPlayed.map(z => z === "strong" ? "🟩" : "🟨");
  const rows = [];
  for (let i = 0; i < grid.length; i += 10) rows.push(grid.slice(i, i + 10).join(""));
  const share = `Vocabulium — ${S.wordCount} mots, ${letters} lettres interdites 🔥\n`
    + rows.join("\n") + `\nvocabulium.up.railway.app`;
  el.sharegrid.textContent = rows.join("\n");
  el.share.onclick = () => {
    if (navigator.share) navigator.share({ text: share }).catch(() => {});
    else navigator.clipboard.writeText(share).then(() => (el.share.textContent = "Copié !"));
  };
  el.end.classList.add("show");
}

// --- events -----------------------------------------------------------------
el.guess.addEventListener("keydown", (e) => {
  if (e.key === "Enter") { e.preventDefault(); submitHop(); }
});
el.guess.addEventListener("input", () => {
  const bad = Letters.offendingLetters(el.guess.value.toLowerCase(), activeForbidden());
  el.guess.classList.toggle("hasforbidden", bad.length > 0);
});
el.play.addEventListener("click", startRun);                       // Jouer : lance + chrono
el.again.addEventListener("click", async () => {                   // Rejouer : nouvelle partie + chrono immédiat
  await prepareRun();
  startRun();
});

// Au chargement : on prépare la partie et on montre l'écran "Jouer" (chrono à l'arrêt).
prepareRun().then(() => el.start.classList.add("show"));
