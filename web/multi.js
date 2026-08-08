"use strict";
// Client multijoueur. Enveloppe app.js : réutilise el/S/cfg/Letters + les fonctions
// de rendu globales d'app.js. L'état de partie vient du serveur (WebSocket) ; le
// score/rang du joueur local est décoratif (calculé côté client comme en solo).
(function () {
  const $ = (id) => document.getElementById(id);
  const scr = {
    start: $("start"), mpmenu: $("mpmenu"), lobby: $("lobby"),
    mpend: $("mpend"), end: $("end"),
  };
  const M = { ws: null, code: null, you: null, players: [], state: "idle",
              activePid: null, raf: 0, turnMs: 15000, gameCode: null, lastWord: "" };

  // --- écrans : montre exactement un overlay .end (ou aucun = écran de jeu) ----
  function show(name) {
    for (const k in scr) scr[k].classList.remove("show");
    if (name && scr[name]) scr[name].classList.add("show");
  }
  const esc = (s) => String(s).replace(/[<>&]/g,
    (c) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;" }[c]));
  const pseudo = () => ($("mpName").value.trim() || "Joueur");

  // --- WebSocket --------------------------------------------------------------
  function wsUrl() {
    const p = location.protocol === "https:" ? "wss" : "ws";
    return `${p}://${location.host}/ws`;
  }
  function connect(onOpen) {
    M.ws = new WebSocket(wsUrl());
    M.ws.onopen = onOpen;
    M.ws.onmessage = (e) => handle(JSON.parse(e.data));
    M.ws.onclose = () => { if (M.state !== "idle" && M.state !== "over") lobbyError("connexion perdue"); };
  }
  function freshConnect(onOpen) {
    if (M.ws) { try { M.ws.close(); } catch (e) {} }
    connect(onOpen);
  }
  function send(obj) { if (M.ws && M.ws.readyState === 1) M.ws.send(JSON.stringify(obj)); }

  // --- routage des messages serveur ------------------------------------------
  function handle(msg) {
    switch (msg.type) {
      case "joined":
        M.code = msg.code; M.you = msg.you; applyState(msg.state);
        document.body.classList.add("multi"); show("lobby"); renderLobby();
        break;
      case "state":
        applyState(msg.state);
        if (M.state === "lobby") { show("lobby"); renderLobby(); }
        else renderPlayers();
        break;
      case "turn":
        M.state = "playing";
        if (M.gameCode !== M.code) {                 // première 'turn' de cette partie
          M.gameCode = M.code;
          ensureConfig().then(() => { enterGame(); onTurn(msg); });
        } else onTurn(msg);
        break;
      case "hop_accepted": onHopAccepted(msg); break;
      case "hop_rejected": onHopRejected(msg); break;
      case "life_lost":    onLifeLost(msg); break;
      case "game_over":    onGameOver(msg); break;
      case "error":        lobbyError(errText(msg.reason)); break;
    }
  }
  function applyState(st) { M.players = st.players; M.state = st.state; }
  function errText(r) {
    return ({ no_room: "salon introuvable", full_or_started: "salon plein ou démarré",
              not_host: "seul l'hôte peut lancer", need_players: "il faut au moins 2 joueurs",
              already_in_room: "déjà dans un salon" }[r]) || r;
  }
  function me() { return M.players.find((p) => p.id === M.you); }
  function isAlive(pid) { const p = M.players.find((x) => x.id === pid); return p && p.alive; }
  function myTurn() { return M.activePid === M.you && isAlive(M.you); }

  // --- LOBBY ------------------------------------------------------------------
  function lobbyError(t) { const e = $("lobbyHint") || $("mpErr"); if (e) e.textContent = t; }
  function renderLobby() {
    $("lobbyCode").textContent = M.code;
    $("lobbyLink").textContent = `${location.host}/?room=${M.code}`;
    $("lobbyPlayers").innerHTML = M.players.map((p) =>
      `<span class="lp"><i class="dot" style="background:${p.color}"></i>${esc(p.name)}`
      + `${p.host ? ' <b class="host">hôte</b>' : ""}</span>`).join("");
    const amHost = me() && me().host;
    const canStart = M.players.length >= 2;
    const btn = $("lobbyStart");
    btn.hidden = !amHost;
    btn.disabled = !(amHost && canStart);
    $("lobbyHint").textContent = canStart
      ? (amHost ? "Prêt : clique Lancer." : "En attente de l'hôte…")
      : "En attente de joueurs… (2 minimum)";
  }

  // --- bandeau joueurs (lobby + jeu) -----------------------------------------
  function renderPlayers() {
    const box = $("players");
    box.hidden = false;
    box.innerHTML = M.players.map((p) => {
      const cls = ["pl"];
      if (p.id === M.you) cls.push("me");
      if (M.activePid && p.id === M.activePid) cls.push("active");
      if (!p.alive) cls.push("dead");
      const hearts = [0, 1, 2].map((i) =>
        `<span class="hp ${i < p.lives ? "full" : "empty"}">♥</span>`).join("");
      const initial = esc((p.name[0] || "?").toUpperCase());
      return `<div class="${cls.join(" ")}"><div class="av" style="background:${p.color}">`
        + `${initial}</div><div class="nm">${esc(p.name)}</div>`
        + `<div class="hearts">${hearts}</div></div>`;
    }).join("");
  }

  // --- config du portail (réutilise setupGate/cfg d'app.js) -------------------
  async function ensureConfig() {
    try {
      const r = await fetch("/api/seed?mode=random").then((x) => x.json());
      Object.assign(cfg, r.config);            // cfg = global d'app.js
      setupGate();
    } catch (e) {}
  }

  // --- entrée en jeu ----------------------------------------------------------
  function resetLocalScore() {
    S.score = 0; S.mult = 1; S.rankIndex = 0; S.rankFill = 0;
    el.trail.innerHTML = "";
    el.dword.textContent = "—"; el.dpts.textContent = "";
    setBars(0, 0, true); renderHud(); renderRank(true);
  }
  function enterGame() {
    show(null);                                // aucun overlay : écran de jeu visible
    $("players").hidden = false; $("turnlbl").hidden = false;
    resetLocalScore();
    // Repart d'un écran propre : sans ça, le bandeau des lettres interdites (et le
    // panneau de détail) gardait l'état de la partie précédente (bug : « lettre
    // interdite déjà présente » au lancement d'une nouvelle partie).
    renderForbiddenBand([], 0);
    el.detail.className = "detail";
    el.dword.textContent = "—"; el.dpts.textContent = "";
    renderGate(null); setBars(0, 0, true);
    el.guess.classList.remove("hasforbidden");
  }
  function renderForbiddenBand(forbidden, wordCount) {
    el.forbidLetters.innerHTML = (forbidden || []).map((L) =>
      `<span class="fl" data-l="${L}">${L}</span>`).join("");
    el.forbidNext.textContent = "prochaine dans " + (5 - (wordCount % 5));
  }

  // --- TOUR -------------------------------------------------------------------
  function onTurn(msg) {
    M.activePid = msg.active;
    el.current.textContent = msg.current;
    renderPlayers();
    const active = M.players.find((p) => p.id === msg.active);
    const mine = myTurn();
    $("turnlbl").classList.toggle("wait", !mine);
    $("turnlbl").textContent = mine ? "◆ À TOI DE JOUER ◆"
      : `◆ AU TOUR DE ${(active ? active.name : "?").toUpperCase()} ◆`;
    el.guess.disabled = !mine;
    el.guess.value = "";
    if (mine) el.guess.focus();
    startGauge();
  }
  // Anime el.gauge sur une fenêtre locale de turnMs (le serveur reste juge du
  // timeout ; deadline_ms serveur est sur une horloge monotone -> inutilisable ici).
  function startGauge() {
    cancelAnimationFrame(M.raf);
    const start = Date.now(), span = M.turnMs;
    const loop = () => {
      const frac = Math.max(0, 1 - (Date.now() - start) / span);
      el.gauge.style.transform = `scaleX(${frac})`;
      if (frac > 0 && M.state === "playing" && M.activePid) M.raf = requestAnimationFrame(loop);
    };
    loop();
  }

  // --- HOP accepté (chaîne partagée + juice local si c'est mon coup) -----------
  function onHopAccepted(msg) {
    applyState(msg.state);
    const sc = msg.score || {};
    const weak = sc.zone === "weak";
    const res = { word: msg.current, input: msg.current, prox: sc.prox,
                  reason: sc.reason, rarete: sc.rarete || 0, speed: sc.speed || 0 };
    showDetail(res, Math.round(sc.hop_points || 0), sc.zone || "strong");
    pushTrail(msg.current, sc.zone === "strong" && (sc.rarete || 0) >= 0.55, weak,
              Math.round(sc.hop_points || 0));
    renderForbiddenBand(msg.state.forbidden, msg.word_count);
    if (msg.new_forbidden) newForbiddenBeat(msg.new_forbidden);
    // Pas de score en multi : seul le juice « mot rare » (étincelles) est conservé
    // pour l'auteur du coup — le reste (compteur, rang, toast +N) est retiré.
    if (msg.scored_by === M.you && (sc.rarete || 0) >= 0.6) rareJuice(sc.rarete);
    el.current.textContent = msg.current;
    el.guess.classList.remove("hasforbidden");
    renderPlayers();
  }

  // --- HOP refusé (pas de perte de vie, feedback seulement) -------------------
  // Aligné sur le solo : lettre interdite -> tuile qui clignote + saisie rouge ;
  // trop loin -> position réelle sur la barre de proximité + « trop loin » ; mot
  // inconnu / déjà joué -> texte de gate. Le mot d'ancrage pulse (blinkUnchanged).
  function onHopRejected(msg) {
    const r = msg.reason;
    const sc = msg.score;
    const typed = M.lastWord || "";             // la saisie est déjà vidée à l'envoi

    if (r === "forbidden_letter") {             // filet serveur (le pré-contrôle local prime)
      flashForbidden(Letters.offendingLetters(typed.toLowerCase(), domForbidden()));
      shake();
      return;
    }

    if (sc) {                                   // mot du dico : on connaît la proximité
      const res = { word: typed, input: typed, prox: sc.prox, reason: sc.reason,
                    rarete: sc.rarete || 0, speed: sc.speed || 0 };
      showDetail(res, 0, r === "too_far" ? "reject" : (sc.zone || "reject"));
    } else {                                    // inconnu / déjà joué : pas de proximité
      el.dword.innerHTML = `${esc(typed)} <small>${rejText(r)}</small>`;
      el.dpts.textContent = ""; el.detail.className = "detail live reject";
      renderGate(null); setBars(0, 0, true);
    }
    shake();
    blinkUnchanged();
  }
  function rejText(r) {
    return ({ too_far: "trop loin", already_played: "déjà joué",
              forbidden_letter: "lettre interdite", unknown_word: "mot inconnu",
              not_your_turn: "pas ton tour", not_playing: "partie non lancée",
              bad_message: "entrée invalide" }[r]) || r;
  }

  // --- PERTE DE VIE (flash blanc pour les autres, rose pour toi) ---------------
  function onLifeLost(msg) {
    applyState(msg.state);
    renderPlayers();
    const mine = msg.pid === M.you;
    el.levelflash.style.background = mine ? "#ff2e97" : "#ffffff";
    replay(el.levelflash, "play");
    screenShake(mine ? "l" : "s");
    if (mine) {
      el.beat.innerHTML = `<div class="b1">− 1</div><div class="b2">❤</div>`;
      replay(el.beat, "play");
    }
  }

  // --- FIN DE PARTIE ----------------------------------------------------------
  function onGameOver(msg) {
    applyState(msg.state);
    cancelAnimationFrame(M.raf);
    el.guess.disabled = true;
    M.state = "over"; M.activePid = null;
    const w = M.players.find((p) => p.id === msg.winner);
    const iWon = msg.winner === M.you;
    $("mpendTitle").textContent = iWon ? "Tu as gagné !" : "Partie terminée";
    $("mpWinner").textContent = w ? `🏆 ${w.name}` : "—";
    // Le vainqueur est le dernier survivant (pas de score en multi).
    $("mpScores").innerHTML = M.players.map((p) =>
      `<span class="lp"><i class="dot" style="background:${p.color}"></i>${esc(p.name)}`
      + `${!p.alive ? ' <span class="host">éliminé</span>' : ""}</span>`).join("");
    show("mpend");
  }

  // --- ouverture / sortie -----------------------------------------------------
  function open() {
    document.body.classList.add("multi");
    $("mpErr").textContent = "";
    const pre = new URLSearchParams(location.search).get("room");
    if (pre) $("mpCode").value = pre.toUpperCase();
    show("mpmenu");
  }
  function backToMenu() {
    if (M.ws) { try { M.ws.close(); } catch (e) {} M.ws = null; }
    M.state = "idle"; M.gameCode = null; M.activePid = null;
    document.body.classList.remove("multi");
    $("players").hidden = true; $("turnlbl").hidden = true;
    show("start");
  }

  // --- wiring (les éléments existent : ce script est chargé après le HTML) -----
  $("playMulti").addEventListener("click", open);
  $("mpBack").addEventListener("click", backToMenu);
  $("mpCreate").addEventListener("click", () =>
    freshConnect(() => send({ action: "create", name: pseudo() })));
  $("mpJoin").addEventListener("click", () => {
    const code = $("mpCode").value.trim().toUpperCase();
    if (code.length !== 4) return ($("mpErr").textContent = "code à 4 lettres");
    freshConnect(() => send({ action: "join", code, name: pseudo() }));
  });
  $("lobbyStart").addEventListener("click", () => send({ action: "start" }));
  $("lobbyLeave").addEventListener("click", backToMenu);
  $("mpMenu").addEventListener("click", backToMenu);
  $("mpRematch").addEventListener("click", backToMenu);   // v1 : retour menu

  // Envoi d'un hop en capture (passe avant le handler solo d'app.js, inerte en multi).
  el.guess.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && M.state === "playing" && myTurn()) {
      e.preventDefault();
      const w = el.guess.value.trim();
      if (!w) return;
      // Pré-contrôle lettre interdite EN LOCAL, comme en solo : feedback immédiat
      // (tuile qui clignote + secousse), pas d'aller-retour, saisie conservée.
      const bad = Letters.offendingLetters(w.toLowerCase(), domForbidden());
      if (bad.length) { flashForbidden(bad); shake(); return; }
      M.lastWord = w;
      send({ action: "hop", word: w });
      el.guess.value = "";
      el.guess.classList.remove("hasforbidden");
    }
  }, true);

  window.Multi = { open, _M: M };
})();
