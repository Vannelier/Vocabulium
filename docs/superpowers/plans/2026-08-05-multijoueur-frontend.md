# Multijoueur — Frontend (lobby + écran de jeu piloté serveur) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter le client multijoueur (lobby + écran de jeu temps réel) comme un **mod** du mode aléatoire : on enveloppe `web/app.js` (on réutilise ses fonctions de rendu, sa DOM et sa palette) et on pilote l'affichage par l'état poussé en WebSocket par le backend déjà livré.

**Architecture:** Scripts classiques sans bundler (comme le reste du projet). `web/app.js` reste le moteur **solo** ; un nouveau `web/multi.js` (chargé après) réutilise le même `el` (DOM), `cfg`, `Letters` et les fonctions de rendu globales d'`app.js`, mais remplace la boucle par un client WebSocket piloté serveur. L'état de partie (mot courant, tour, vies, joueurs, lettres interdites) vient du serveur ; le **score/rang du joueur local est décoratif**, calculé côté client en réutilisant la math de rang d'`app.js` (via l'objet global `S`). Vérification **au navigateur** (le projet n'a pas de framework de test JS).

**Tech Stack:** HTML/CSS/JS vanilla, WebSocket natif, FastAPI (backend déjà en place). Backend Python : un petit ajout au protocole (Task 1) testé en pytest.

**Référence spec :** `docs/superpowers/specs/2026-08-05-multijoueur-design.md`
**Backend déjà livré :** `app/ws.py` (protocole), `app/rooms.py`, `app/letters.py`. Voir le plan backend `docs/superpowers/plans/2026-08-05-multijoueur-backend.md`.

---

## Rappel du protocole serveur (déjà implémenté)

Client → serveur : `{"action":"create","name"}` · `{"action":"join","code","name"}` · `{"action":"start"}` · `{"action":"hop","word"}`.

Serveur → client (chaque message a `type`) :
- `joined` `{code, you, state}` · `state` `{state}` · `error` `{reason}`
- `hop_accepted` `{current, word_count, active, scored_by, new_forbidden, state}` (+ `score` ajouté en Task 1)
- `hop_rejected` `{reason}` (au seul émetteur)
- `turn` `{active, current, deadline_ms}`
- `life_lost` `{pid, lives, eliminated, state}`
- `game_over` `{winner, state}`

`state` = `{code, state, current, word_count, active, forbidden:[...], players:[{id,name,color,lives,alive,host}]}`.

## Fonctions/globales d'`app.js` réutilisées par `multi.js`

Scripts classiques : `const el`, `let S`, `let cfg` et les `function` de haut niveau d'`app.js` sont dans la portée globale partagée → `multi.js` (chargé après) y accède par leur nom.

- **DOM only (réutilisées telles quelles) :** `pushTrail(word,hot,weak,gained)`, `showDetail(res,gained,zone)`, `renderGate(prox,zone,reason)`, `setBars(rar,speed,blank)`, `toastScore(n,cls,rare)`, `rareJuice(rarity)`, `screenShake(kind)`, `flashLevel()`, `replay(elm,cls)`, `blinkUnchanged()`, `flashForbidden(letters)`, `newForbiddenBeat(letter)`, `setupGate()`.
- **Score/rang décoratif (via l'objet global `S`) :** `addFill(amount)`, `renderRank(instant)`, `syncMult()`, `renderHud()`. `multi.js` réinitialise `S` au début d'une partie multi et appelle ces fonctions pour le joueur local uniquement.
- **`el.gauge`, `el.current`, `el.trail`, `el.forbidLetters`, `el.forbidNext`, `el.beat`, `el.levelflash`** : éléments DOM partagés.
- **`Letters.offendingLetters(word, active)`** : highlight live des lettres interdites dans la saisie.

`multi.js` ne réutilise PAS `submitHop`/`tick`/`prepareRun`/`endRun` (spécifiques solo).

---

## File Structure

- Modify: `app/ws.py` — `validate_hop` renvoie la décomposition de score ; `hop_accepted` la transmet. Test: `tests/test_ws.py`.
- Modify: `web/index.html` — bandeau joueurs `#players`, écrans lobby `#mpmenu`/`#lobby`/`#mpend`, bouton menu « Multijoueur », `<script src="/multi.js">`. Classe `body.multi` pour masquer record + mot bonus.
- Create: `web/multi.js` — tout le client multijoueur (WS, lobby, rendu piloté serveur, juice, fin).
- Modify: `web/style.css` — styles bandeau joueurs (avatars + cœurs), lobby, règles `body.multi` (masquage record/cible), écran de fin multi.
- `web/app.js` — **aucune modification fonctionnelle attendue** : la boucle solo est déjà gardée par `if (!S.running) return;` (jamais vraie en multi), et `multi.js` pose ses propres écouteurs (dont le bouton « Multijoueur »). Task 5 Step 2 ne fait que *vérifier* ce point (case à cocher, pas d'édition). Si une régression apparaît en Task 7, un correctif ciblé y est prévu.

**Vérification :** au navigateur via le serveur de dev. Démarrer le serveur (préciser au besoin `.claude/launch.json`), ouvrir **deux onglets** pour simuler deux joueurs.

---

## Task 1 (backend) : exposer la décomposition de score dans `hop_accepted`

Le juice « à mort » (rang qui monte, jauges rareté/vitesse, étincelles rares) a besoin, pour le joueur qui a marqué, de `zone`/`rarete`/`speed`/`hop_points`/`prox`/`reason`. Le serveur les calcule déjà dans `validate_hop` (via `score_hop`) mais les jette.

**Files:**
- Modify: `app/ws.py` (`validate_hop`, handler `hop`)
- Test: `tests/test_ws.py`

- [ ] **Step 1: Adapter le stub de test + asserter les nouveaux champs.** Dans `tests/test_ws.py`, remplacer le `fake_validate` de `_app` par une version qui renvoie une décomposition, et ajouter un test :
```python
def _app(monkeypatch):
    def fake_validate(current, word):
        canon = word.lower()
        if canon in {"foudre", "pluie", "vent"}:
            return {"ok": True, "accepted": True, "canonical": canon,
                    "score": {"zone": "strong", "rarete": 0.5, "speed": 0.4,
                              "hop_points": 120.0, "prox": 0.4, "reason": ""}}
        return {"ok": False, "reason": "unknown_word"}
    monkeypatch.setattr(ws, "validate_hop", fake_validate)
    monkeypatch.setattr(ws, "pick_seed", lambda: "orage")
    monkeypatch.setattr(ws, "make_forbidden_order", lambda: list("zqxwkjbfmgpv"))
    app = FastAPI()
    app.include_router(ws.router)
    return app


def test_hop_accepted_carries_score_decomposition(monkeypatch):
    client = TestClient(_app(monkeypatch))
    with client.websocket_connect("/ws") as host, \
         client.websocket_connect("/ws") as guest:
        host.send_json({"action": "create", "name": "toi"})
        code = host.receive_json()["code"]
        guest.send_json({"action": "join", "code": code, "name": "B"})
        guest.receive_json(); host.receive_json()
        host.send_json({"action": "start"})
        m = host.receive_json()
        while m["type"] != "turn":
            m = host.receive_json()
        host.send_json({"action": "hop", "word": "foudre"})
        acc = host.receive_json()
        while acc["type"] != "hop_accepted":
            acc = host.receive_json()
        assert acc["score"]["zone"] == "strong"
        assert acc["score"]["hop_points"] == 120.0
```

- [ ] **Step 2: Lancer, voir échouer.** Run: `../Discoverix/.venv/Scripts/python.exe -m pytest tests/test_ws.py::test_hop_accepted_carries_score_decomposition -q` — Expected: FAIL (`KeyError: 'score'`).

- [ ] **Step 3: `validate_hop` renvoie la décomposition.** Dans `app/ws.py`, remplacer le corps de `validate_hop` (partie succès) pour inclure `score` :
```python
def validate_hop(current: str, word: str) -> dict:
    from app.main import db
    from app.scoring import score_hop, same_lemma
    canon = db.canonical(word)
    if canon is None:
        return {"ok": False, "reason": "unknown_word"}
    prev = db.canonical(current)
    if canon == prev or same_lemma(prev, canon):
        return {"ok": False, "reason": "already_played"}
    prox = db.prox(prev, canon)
    res = score_hop(prox, db.zipf(canon), 0.0)
    return {"ok": True, "accepted": res.zone != "reject", "canonical": canon,
            "score": {"zone": res.zone, "rarete": res.rarete, "speed": res.speed,
                      "hop_points": res.hop_points, "prox": res.prox,
                      "reason": res.reason}}
```

- [ ] **Step 4: le handler `hop` transmet `score` dans `hop_accepted`.** Dans le broadcast `hop_accepted` du handler `hop`, ajouter `"score": v["score"]` :
```python
                await _broadcast(room.code, {
                    "type": "hop_accepted", "current": res["current"],
                    "word_count": res["word_count"], "active": res["active"],
                    "scored_by": res["scored_by"], "new_forbidden": res["new_forbidden"],
                    "score": v["score"],
                    "state": _room_state(room)})
```

- [ ] **Step 5: Lancer les tests.** Run: `../Discoverix/.venv/Scripts/python.exe -m pytest tests/test_ws.py -q` — Expected: tout vert (13 passed).

- [ ] **Step 6: Commit.**
```bash
git add app/ws.py tests/test_ws.py
git commit -m "feat: hop_accepted transmet la décomposition de score (pour le juice front)"
```

---

## Task 2 : markup HTML — bandeau joueurs + écrans lobby (cachés par défaut)

**Files:** Modify: `web/index.html`

- [ ] **Step 1: Ajouter le bandeau joueurs dans `#app`.** Juste après la ligne `<div class="topbar">…</div>` (et avant `<div class="hud">`), insérer :
```html
    <div class="players" id="players" hidden></div>
    <div class="turnlbl" id="turnlbl" hidden></div>
```

- [ ] **Step 2: Ajouter le bouton « Multijoueur » au menu.** Dans `#start`, remplacer le bloc `.endbtns` existant par :
```html
    <div class="endbtns">
      <button id="playMulti">Multijoueur</button>
      <button id="play">Mot aléatoire</button>
    </div>
```
(On retire le bouton « Mot du jour » : remplacé par le multi, conformément à la spec.)

- [ ] **Step 3: Ajouter les écrans lobby après le `#end` existant.**
```html
  <!-- Multi : menu créer/rejoindre -->
  <div class="end" id="mpmenu">
    <h1>Multijoueur</h1>
    <div class="recap">Crée un salon et partage le code, ou rejoins celui d'un ami.</div>
    <input id="mpName" class="mpfield" maxlength="14" autocomplete="off" placeholder="ton pseudo">
    <div class="endbtns">
      <button id="mpCreate">Créer un salon</button>
    </div>
    <div class="mpjoin">
      <input id="mpCode" class="mpfield" maxlength="4" autocomplete="off"
             placeholder="CODE" style="text-transform:uppercase">
      <button id="mpJoin">Rejoindre</button>
    </div>
    <div class="mperr" id="mpErr"></div>
    <div class="endbtns"><button id="mpBack">Retour</button></div>
  </div>

  <!-- Multi : salon (lobby) -->
  <div class="end" id="lobby">
    <h1>Salon <span id="lobbyCode" class="lobbycode">····</span></h1>
    <div class="recap">Partage ce lien : <span id="lobbyLink" class="lobbylink"></span></div>
    <div class="lobbyplayers" id="lobbyPlayers"></div>
    <div class="endbtns">
      <button id="lobbyStart" disabled>Lancer</button>
      <button id="lobbyLeave">Quitter</button>
    </div>
    <div class="mperr" id="lobbyHint">En attente de joueurs… (2 minimum)</div>
  </div>

  <!-- Multi : fin de partie -->
  <div class="end" id="mpend">
    <h1 id="mpendTitle">Partie terminée</h1>
    <div class="mpwinner" id="mpWinner"></div>
    <div class="lobbyplayers" id="mpScores"></div>
    <div class="endbtns">
      <button id="mpRematch">Retour au salon</button>
      <button id="mpMenu">Menu</button>
    </div>
  </div>
```

- [ ] **Step 4: Charger `multi.js` après `app.js`.** Juste avant `<script src="/ads.js?v=3"></script>`, ajouter :
```html
  <script src="/multi.js?v=1"></script>
```

- [ ] **Step 5: Vérifier au navigateur (structure).** Démarrer le serveur de dev (voir la note « Vérification » plus haut ; créer `.claude/launch.json` avec `uvicorn app.main:app --port 8077` si besoin). Charger la page : elle doit se charger sans erreur console, le menu montre **« Multijoueur »** et **« Mot aléatoire »**. Les écrans `#mpmenu`/`#lobby`/`#mpend` et le bandeau `#players` sont présents mais cachés (`hidden` / classe `end` sans `show`). Confirmer via `read_page` / capture qu'aucune régression du solo n'est visible.

- [ ] **Step 6: Commit.**
```bash
git add web/index.html
git commit -m "feat(front): markup bandeau joueurs + écrans lobby multi (cachés)"
```

---

## Task 3 : CSS — bandeau joueurs (avatars + cœurs), lobby, masquage record/cible en multi

**Files:** Modify: `web/style.css`

- [ ] **Step 1: Ajouter les styles à la fin de `web/style.css`.** (Palette réutilisée ; cœurs roses ; joueur actif qui pulse ; « toi » cadre cyan ; masquage record + cible sous `body.multi`.)
```css
/* ======================= MULTIJOUEUR ======================= */
/* Bandeau joueurs (récupère la place du record + mot bonus, masqués en multi). */
body.multi .hiscore { display: none; }
body.multi .cible { display: none !important; }

.players { display: flex; gap: 5px; margin: 4px 0 10px; }
.players .pl { flex: 1; display: flex; flex-direction: column; align-items: center;
  gap: 3px; padding: 5px 2px; border-radius: 11px; border: 1.5px solid transparent; }
.players .pl.me { border-color: rgba(34,230,255,.55); }
.players .pl.active { border-color: var(--pink); background: rgba(255,46,151,.12);
  box-shadow: 0 0 16px rgba(255,46,151,.55); animation: plpulse 1.1s ease-in-out infinite; }
@keyframes plpulse { 0%,100%{box-shadow:0 0 10px rgba(255,46,151,.4)}
  50%{box-shadow:0 0 20px rgba(255,46,151,.75)} }
.players .pl.dead { opacity: .3; }
.players .av { width: 30px; height: 30px; border-radius: 50%; display: flex;
  align-items: center; justify-content: center; font-weight: 700; font-size: 14px;
  color: #0d0722; }
.players .pl.active .av { box-shadow: 0 0 0 2px var(--bg), 0 0 0 3px var(--pink); }
.players .nm { font-size: 9px; color: var(--muted); max-width: 52px; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap; }
.players .pl.me .nm { color: var(--cyan); font-weight: 700; }
.players .pl.active .nm { color: var(--ink); }
.players .hearts { display: flex; gap: 2px; }
.players .hp { font-size: 11px; line-height: 1; }
.players .hp.full { color: var(--pink); text-shadow: 0 0 5px var(--pink); }
.players .hp.empty { color: var(--line); }

.turnlbl { text-align: center; font-family: var(--pixel); font-size: 10px;
  letter-spacing: .06em; color: var(--pink); margin-bottom: 8px; }
.turnlbl.wait { color: var(--muted); }

/* Champs & écrans lobby (réutilisent la carte .end existante). */
.mpfield { width: 100%; max-width: 320px; margin: 6px auto; display: block;
  background: var(--bg2); border: 1.5px solid var(--line); border-radius: 12px;
  color: var(--ink); font-family: var(--body); font-size: 16px; padding: 12px 14px;
  text-align: center; }
.mpfield:focus { outline: none; border-color: var(--pink); box-shadow: var(--glow); }
.mpjoin { display: flex; gap: 8px; max-width: 320px; margin: 10px auto; }
.mpjoin .mpfield { margin: 0; letter-spacing: .3em; font-family: var(--pixel); font-size: 14px; }
.mpjoin button { white-space: nowrap; }
.mperr { color: var(--bail); font-size: 13px; min-height: 18px; margin-top: 8px; }
.lobbycode { font-family: var(--pixel); color: var(--gold); letter-spacing: .2em; }
.lobbylink { color: var(--cyan); word-break: break-all; }
.lobbyplayers { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center;
  margin: 14px 0; }
.lobbyplayers .lp { display: flex; align-items: center; gap: 6px; padding: 6px 10px;
  background: var(--bg2); border: 1px solid var(--line); border-radius: 20px; font-size: 13px; }
.lobbyplayers .lp .dot { width: 12px; height: 12px; border-radius: 50%; }
.lobbyplayers .lp .host { color: var(--gold); font-size: 11px; }
.mpwinner { font-family: var(--pixel); font-size: 18px; color: var(--gold);
  text-shadow: 0 0 16px var(--gold); margin: 10px 0; }
```

- [ ] **Step 2: Vérifier au navigateur.** Recharger. Aucune régression visuelle du solo. (Les écrans multi restent cachés ; on les stylera « en vrai » en les affichant aux tâches suivantes.) Confirmer par capture que le menu et le jeu solo sont intacts.

- [ ] **Step 3: Commit.**
```bash
git add web/style.css
git commit -m "feat(front): styles bandeau joueurs + lobby + masquage record/cible en multi"
```

---

## Task 4 : `multi.js` — connexion, menu, lobby (créer/rejoindre/liste/lancer)

**Files:** Create: `web/multi.js` ; Modify: `web/index.html` (rien de plus — script déjà inclus en Task 2).

- [ ] **Step 1: Écrire le squelette `web/multi.js`** (namespace `window.Multi`, gestion d'écrans, WebSocket, lobby). Ce fichier grandira aux tâches 5-6.
```javascript
"use strict";
// Client multijoueur. Enveloppe app.js : réutilise el/S/cfg/Letters + fonctions de
// rendu globales. L'état de partie vient du serveur (WebSocket).
(function () {
  const $ = (id) => document.getElementById(id);
  const scr = {
    start: $("start"), mpmenu: $("mpmenu"), lobby: $("lobby"),
    mpend: $("mpend"), end: $("end"),
  };
  const M = { ws: null, code: null, you: null, players: [], state: "idle",
              raf: 0, deadline: 0, turnMs: 15000 };

  // --- écrans : montre exactement un overlay .end (ou aucun pour le jeu) -------
  function show(name) {
    for (const k in scr) scr[k].classList.remove("show");
    if (name && scr[name]) scr[name].classList.add("show");
  }

  // --- WebSocket --------------------------------------------------------------
  function wsUrl() {
    const p = location.protocol === "https:" ? "wss" : "ws";
    return `${p}://${location.host}/ws`;
  }
  function connect(onOpen) {
    M.ws = new WebSocket(wsUrl());
    M.ws.onopen = onOpen;
    M.ws.onmessage = (e) => handle(JSON.parse(e.data));
    M.ws.onclose = () => { if (M.state !== "idle") lobbyError("connexion perdue"); };
  }
  function send(obj) { if (M.ws && M.ws.readyState === 1) M.ws.send(JSON.stringify(obj)); }

  // --- routage des messages serveur ------------------------------------------
  function handle(msg) {
    switch (msg.type) {
      case "joined":   M.code = msg.code; M.you = msg.you; applyState(msg.state);
                       document.body.classList.add("multi"); show("lobby"); renderLobby(); break;
      case "state":    applyState(msg.state);
                       if (M.state === "lobby") renderLobby(); else renderPlayers(); break;
      case "turn":       onTurn(msg); break;              // Task 5
      case "hop_accepted": onHopAccepted(msg); break;     // Task 5
      case "hop_rejected": onHopRejected(msg); break;     // Task 5
      case "life_lost":    onLifeLost(msg); break;        // Task 6
      case "game_over":    onGameOver(msg); break;        // Task 6
      case "error":        lobbyError(errText(msg.reason)); break;
    }
  }
  function applyState(st) {
    M.players = st.players;
    M.state = st.state;                       // "lobby" | "playing" | "over"
  }
  function errText(r) {
    return ({ no_room: "salon introuvable", full_or_started: "salon plein ou démarré",
              not_host: "seul l'hôte peut lancer", need_players: "il faut au moins 2 joueurs",
              already_in_room: "déjà dans un salon" }[r]) || r;
  }

  // --- LOBBY ------------------------------------------------------------------
  function me() { return M.players.find((p) => p.id === M.you); }
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
  function esc(s) { return String(s).replace(/[<>&]/g, (c) =>
    ({ "<": "&lt;", ">": "&gt;", "&": "&amp;" }[c])); }

  // --- rendu du bandeau joueurs (utilisé aussi en jeu, Task 5) ----------------
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

  // --- ouverture depuis le menu ----------------------------------------------
  function open() {
    document.body.classList.add("multi");
    $("mpErr").textContent = "";
    const pre = new URLSearchParams(location.search).get("room");
    if (pre) $("mpCode").value = pre.toUpperCase();
    show("mpmenu");
  }
  function backToMenu() {
    if (M.ws) { try { M.ws.close(); } catch (e) {} M.ws = null; }
    M.state = "idle"; document.body.classList.remove("multi");
    $("players").hidden = true; $("turnlbl").hidden = true;
    show("start");
  }

  function name() { return ($("mpName").value.trim() || "Joueur"); }

  // --- wiring -----------------------------------------------------------------
  document.addEventListener("DOMContentLoaded", () => {
    $("playMulti").addEventListener("click", open);
    $("mpBack").addEventListener("click", backToMenu);
    $("mpCreate").addEventListener("click", () =>
      connect(() => send({ action: "create", name: name() })));
    $("mpJoin").addEventListener("click", () => {
      const code = $("mpCode").value.trim().toUpperCase();
      if (code.length !== 4) return ($("mpErr").textContent = "code à 4 lettres");
      connect(() => send({ action: "join", code, name: name() }));
    });
    $("lobbyStart").addEventListener("click", () => send({ action: "start" }));
    $("lobbyLeave").addEventListener("click", backToMenu);
    $("mpMenu").addEventListener("click", backToMenu);
    $("mpRematch").addEventListener("click", backToMenu);   // v1 : retour menu (re-création)
  });

  // exposé (app.js s'y branche pour le bouton menu si besoin)
  window.Multi = { open, _M: M, renderPlayers };
  // placeholders remplacés en Task 5-6 :
  window.Multi.onTurn = window.Multi.onHopAccepted = window.Multi.onHopRejected =
    window.Multi.onLifeLost = window.Multi.onGameOver = function () {};
})();
```
Note : `onTurn`/`onHopAccepted`/`onHopRejected`/`onLifeLost`/`onGameOver` sont référencés par `handle` mais définis aux tâches 5-6. Pour que ce fichier tourne dès maintenant, **déclare ces 5 fonctions comme des no-ops en haut du module** (ex. `function onTurn(){}` etc.), qu'on remplacera par la vraie implémentation aux tâches suivantes. `M.activePid` commence à `undefined`.

- [ ] **Step 2: Ajouter les 5 no-ops temporaires.** En haut du module (après `const M = {…}`), ajouter :
```javascript
  let onTurn = () => {}, onHopAccepted = () => {}, onHopRejected = () => {},
      onLifeLost = () => {}, onGameOver = () => {};
```
(Elles seront redéfinies aux tâches 5-6 en remplaçant ces lignes par de vraies `function`.)

- [ ] **Step 3: Vérifier le lobby au navigateur (contre le vrai backend).** Démarrer le serveur. Ouvrir **deux onglets** sur `http://localhost:8077`.
  - Onglet A : Menu → « Multijoueur » → saisir un pseudo → « Créer un salon ». Vérifier : l'écran lobby s'affiche, un **code à 4 lettres** apparaît, le lien `localhost:8077/?room=XXXX`, et la liste montre le joueur (hôte). Le bouton « Lancer » est visible mais **désactivé** (1 joueur).
  - Onglet B : Menu → « Multijoueur » → pseudo → saisir le code → « Rejoindre ». Vérifier : l'onglet B entre dans le lobby ; **les deux onglets** voient maintenant 2 joueurs (temps réel) ; « Lancer » s'active côté hôte (onglet A).
  - Utiliser `read_page`, `read_console_messages` (aucune erreur), et une capture des 2 états.

- [ ] **Step 4: Commit.**
```bash
git add web/multi.js
git commit -m "feat(front): client multi — connexion + lobby (créer/rejoindre/liste/lancer)"
```

---

## Task 5 : `multi.js` — écran de jeu (tour, jauge, hop, trail, portail, juice local)

Remplace les no-ops `onTurn`/`onHopAccepted`/`onHopRejected` par la vraie logique. Réutilise les fonctions de rendu d'`app.js`.

**Files:** Modify: `web/multi.js` ; Modify: `web/app.js` (exposer une init de config, Step 2).

- [ ] **Step 1: Config du portail.** `showDetail`/`renderGate` ont besoin de `cfg.tau/tau_grace/syno` et de `setupGate()`. Au démarrage d'une partie multi, `multi.js` récupère la config via l'endpoint existant. Ajouter dans `multi.js` :
```javascript
  async function ensureConfig() {
    try {
      const r = await fetch("/api/seed?mode=random").then((x) => x.json());
      Object.assign(cfg, r.config);          // cfg est le global d'app.js
      setupGate();
    } catch (e) {}
  }
```

- [ ] **Step 2: Neutraliser la boucle solo pendant le multi.** Dans `web/app.js`, dans la fonction `tick(now)`, la première ligne est `if (!S.running) return;`. C'est déjà suffisant : en multi on ne met jamais `S.running=true`, donc la jauge solo ne tourne pas. **Aucune modification d'`app.js` nécessaire ici** — cocher après avoir vérifié que `S.running` reste `false` en multi (grep `S.running = true` → seulement dans `startRun`, jamais appelé en multi).

- [ ] **Step 3: Démarrage de partie + rendu d'état de jeu.** Ajouter dans `multi.js` :
```javascript
  // Réinitialise le rang/score décoratif du joueur local (réutilise S d'app.js).
  function resetLocalScore() {
    S.score = 0; S.mult = 1; S.rankIndex = 0; S.rankFill = 0;
    el.trail.innerHTML = "";
    el.dword.textContent = "—"; el.dpts.textContent = "";
    setBars(0, 0, true); renderHud(); renderRank(true);
  }

  function enterGame() {
    show(null);                       // aucun overlay : on voit l'écran de jeu
    $("players").hidden = false; $("turnlbl").hidden = false;
    resetLocalScore();
  }

  function renderForbiddenBand(forbidden, wordCount) {
    el.forbidLetters.innerHTML = forbidden.map((L) =>
      `<span class="fl" data-l="${L}">${L}</span>`).join("");
    const into = 5 - (wordCount % 5);
    el.forbidNext.textContent = "prochaine dans " + into;
  }

  function myTurn() { return M.activePid === M.you && isAlive(M.you); }
  function isAlive(pid) { const p = M.players.find((x) => x.id === pid); return p && p.alive; }
```

- [ ] **Step 4: `onTurn` — nouveau tour (jauge pilotée par la deadline serveur).** Remplacer la ligne no-op `onTurn = () => {};` par :
```javascript
  onTurn = (msg) => {
    M.activePid = msg.active;
    M.deadline = msg.deadline_ms;
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
  };

  // Anime el.gauge de 1 -> 0 sur la fenêtre [now, deadline]. Le serveur reste juge.
  function startGauge() {
    cancelAnimationFrame(M.raf);
    const span = M.turnMs;
    const loop = () => {
      const left = Math.max(0, M.deadline - Date.now());
      el.gauge.style.transform = `scaleX(${Math.max(0, Math.min(1, left / span))})`;
      if (left > 0 && M.state === "playing") M.raf = requestAnimationFrame(loop);
    };
    loop();
  }
```
Note : `M.turnMs` = 15000 (aligné sur `TURN_SECONDS` backend). Si tu changes l'un, change l'autre.

- [ ] **Step 5: `onHopAccepted` — chaîne partagée + juice local si c'est mon coup.** Remplacer le no-op par :
```javascript
  onHopAccepted = (msg) => {
    applyState(msg.state);
    const sc = msg.score || {};
    const weak = sc.zone === "weak";
    // chaîne PARTAGÉE : tout le monde voit le mot + le portail/jauges du dernier coup
    const res = { word: msg.current, input: msg.current, prox: sc.prox,
                  reason: sc.reason, rarete: sc.rarete || 0, speed: sc.speed || 0 };
    showDetail(res, Math.round(sc.hop_points || 0), sc.zone || "strong");
    pushTrail(msg.current, sc.zone === "strong" && (sc.rarete || 0) >= 0.55, weak,
              Math.round(sc.hop_points || 0));
    renderForbiddenBand(msg.state.forbidden, msg.word_count);
    if (msg.new_forbidden) newForbiddenBeat(msg.new_forbidden);
    // score/rang décoratifs : seulement pour l'auteur du coup
    if (msg.scored_by === M.you) {
      const gained = (sc.hop_points || 0) * S.mult;
      S.score += gained;
      if (sc.zone === "strong") addFill(0.6 * (0.5 + (sc.rarete || 0) + 0.6 * (sc.speed || 0)));
      else addFill(0.12);
      renderHud();
      toastScore(gained, weak ? "weakt" : "", sc.rarete || 0);
      if ((sc.rarete || 0) >= 0.6) rareJuice(sc.rarete);
    }
    el.current.textContent = msg.current;
    renderPlayers();
  };
```

- [ ] **Step 6: `onHopRejected` — feedback de refus (pas de perte de vie).** Remplacer le no-op par :
```javascript
  onHopRejected = (msg) => {
    const r = msg.reason;
    if (r === "forbidden_letter") {
      const bad = Letters.offendingLetters(el.guess.value.toLowerCase(),
        [...el.forbidLetters.querySelectorAll(".fl")].map((n) => n.dataset.l));
      flashForbidden(bad);
    }
    el.guess.classList.add("shake");
    setTimeout(() => el.guess.classList.remove("shake"), 300);
    el.dword.innerHTML = `${esc(el.guess.value)} <small>${rejText(r)}</small>`;
    el.dpts.textContent = ""; el.detail.className = "detail live reject";
    if (r !== "forbidden_letter") el.guess.value = "";
  };
  function rejText(r) {
    return ({ too_far: "trop loin", already_played: "déjà joué",
              forbidden_letter: "lettre interdite", unknown_word: "mot inconnu",
              not_your_turn: "pas ton tour", not_playing: "partie non lancée",
              bad_message: "entrée invalide" }[r]) || r;
  }
```

- [ ] **Step 7: Envoyer un hop + highlight live des lettres interdites.** Ajouter le wiring dans le bloc `DOMContentLoaded` de `multi.js` :
```javascript
    el.guess.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && M.state === "playing" && myTurn()) {
        e.preventDefault();
        const w = el.guess.value.trim();
        if (w) send({ action: "hop", word: w });
      }
    }, true);   // capture : passe avant le handler solo d'app.js
```
Note : `app.js` a déjà un handler `keydown` sur `el.guess` qui appelle `submitHop` (solo). En multi, `submitHop` sortirait tôt (`if (!S.running) return;`), donc il ne fait rien de nuisible ; mais on ajoute notre handler en **capture** pour envoyer le hop multi. Vérifier que le hop solo ne part pas (il ne part pas car `S.running` est faux et `submitHop` `return` avant tout appel réseau après le check — en fait `submitHop` teste `if (!S.running) return;` juste après avoir lu la valeur : OK, aucun `/api/hop` solo n'est émis).

- [ ] **Step 8: Router `enterGame` au premier `turn`.** Dans `handle`, le premier `turn` d'une partie doit basculer sur l'écran de jeu. Modifier le `case "turn"` :
```javascript
      case "turn":
        if (M.state !== "playing") { M.state = "playing"; }
        if (scr.lobby.classList.contains("show") || scr.mpend.classList.contains("show")
            || M.justStarted !== M.code) { M.justStarted = M.code; ensureConfig().then(enterGame).then(() => onTurn(msg)); }
        else onTurn(msg);
        break;
```
Simplifie si besoin, l'important : à la première `turn` d'une partie, appeler `ensureConfig()` puis `enterGame()` **avant** `onTurn`. (Sur les tours suivants, appeler seulement `onTurn`.)

- [ ] **Step 9: Vérifier au navigateur (2 onglets, une manche).** Serveur lancé. Onglet A crée, onglet B rejoint, A lance.
  - Les deux passent à l'écran de jeu ; le bandeau joueurs montre 2 avatars avec 3 cœurs, l'un « toi » (cadre cyan), l'actif pulse.
  - Le libellé de tour et l'activation de la saisie sont corrects (seul l'actif peut taper).
  - Sur l'onglet actif, taper un mot proche du mot courant (ex. réel : voir le mot affiché) → `hop_accepted` : le mot courant change chez **les deux**, le trail s'allonge, le portail/jauges s'affichent, et **le score/rang montent chez l'auteur**. Une lettre interdite tapée → highlight rouge, pas de perte de vie.
  - `read_console_messages` (0 erreur), captures des deux onglets.

- [ ] **Step 10: Commit.**
```bash
git add web/multi.js
git commit -m "feat(front): écran de jeu multi — tour, jauge serveur, hop, trail, juice local"
```

---

## Task 6 : `multi.js` — perte de vie (juice blanc/rose), fin de partie, garde-fous

**Files:** Modify: `web/multi.js`

- [ ] **Step 1: `onLifeLost` — cœurs + flash (blanc pour les autres, rose pour toi).** Remplacer le no-op par :
```javascript
  onLifeLost = (msg) => {
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
  };
```

- [ ] **Step 2: `onGameOver` — écran de fin (gagnant + scores + partage).** Remplacer le no-op par :
```javascript
  onGameOver = (msg) => {
    applyState(msg.state);
    cancelAnimationFrame(M.raf);
    el.guess.disabled = true;
    const w = M.players.find((p) => p.id === msg.winner);
    const iWon = msg.winner === M.you;
    $("mpendTitle").textContent = iWon ? "Tu as gagné !" : "Partie terminée";
    $("mpWinner").textContent = w ? `🏆 ${w.name}` : "—";
    $("mpScores").innerHTML = M.players.map((p) =>
      `<span class="lp"><i class="dot" style="background:${p.color}"></i>${esc(p.name)}`
      + `${p.id === M.you ? " · <b>" + Math.round(S.score) + " pts</b>" : ""}</span>`).join("");
    show("mpend");
  };
```
Note : le score par joueur étant décoratif et **local**, seul le score du joueur courant est connu de son client ; on n'affiche « pts » que pour soi (les autres = juste le pseudo + couleur, gagnant mis en avant par le trophée). C'est cohérent avec « score décoratif ».

- [ ] **Step 3: Pré-remplissage via lien `?room=CODE`.** Améliorer `open()` (déjà écrit en Task 4) est suffisant : il lit `?room=` et pré-remplit `#mpCode`. Vérifier au Step 5. (Aucun code neuf ici — cocher après vérif.)

- [ ] **Step 4: Garde-fou anti double-connexion.** Dans `mpCreate`/`mpJoin`, si `M.ws` existe déjà et est ouvert, le fermer avant d'en rouvrir un, pour éviter deux sockets. Modifier les deux handlers pour appeler d'abord :
```javascript
    function freshConnect(onOpen) {
      if (M.ws) { try { M.ws.close(); } catch (e) {} }
      connect(onOpen);
    }
```
et remplacer `connect(() => …)` par `freshConnect(() => …)` dans `mpCreate` et `mpJoin`.

- [ ] **Step 5: Vérifier au navigateur (manche complète à 2, jusqu'à la fin).** Serveur lancé.
  - Rejouer le flux Task 5, puis laisser **un chrono expirer sans jouer** sur l'onglet actif → cet onglet voit un **flash rose + shake fort + « −1 ❤ »**, l'autre voit un **flash blanc** ; le cœur correspondant s'éteint dans le bandeau chez les deux ; la main passe.
  - Épuiser les 3 vies d'un joueur → l'autre voit l'écran **« Tu as gagné ! 🏆 »**, le perdant « Partie terminée ». Le lien `?room=` pré-remplit bien le code sur un 3e onglet.
  - Tester un `game_over` par **déconnexion** : à 2 joueurs en partie, fermer l'onglet actif → l'autre reçoit `game_over` et voit l'écran de victoire.
  - `read_console_messages` (0 erreur), captures : bandeau vies, flash de perte de vie, écran de fin.

- [ ] **Step 6: Commit.**
```bash
git add web/multi.js
git commit -m "feat(front): perte de vie (flash blanc/rose), écran de fin + partage, garde-fous"
```

---

## Task 7 : Vérification d'ensemble + non-régression du solo

**Files:** aucun (vérification), sauf correctifs éventuels.

- [ ] **Step 1: Non-régression solo.** Depuis le menu, lancer **« Mot aléatoire »** : le jeu solo doit fonctionner exactement comme avant (jauge, lettres interdites, rang, mot bonus, fin + partage). Vérifier que `body.multi` n'est pas actif (record + mot bonus **visibles** en solo). Capture.

- [ ] **Step 2: Bascule solo↔multi.** Menu → Multijoueur → Retour → Mot aléatoire → Menu → Multijoueur : aucun état résiduel (pas de socket fantôme, `body.multi` correctement posé/retiré, bandeau joueurs caché en solo). Vérifier `read_console_messages`.

- [ ] **Step 3: Suite backend toujours verte.** Run: `../Discoverix/.venv/Scripts/python.exe -m pytest -q` — Expected: tout vert (56 passed : 55 + le test Task 1).

- [ ] **Step 4: Commit éventuel des correctifs** trouvés aux steps 1-2 (sinon rien).
```bash
git add -A && git commit -m "fix(front): correctifs de non-régression solo/multi"
```

---

## Self-Review — couverture spec

- Menu « Mot du jour » → « Multijoueur » ; solo « Mot aléatoire » conservé → Task 2. ✅
- Lobby : créer/rejoindre par code, lien partageable `?room=`, liste temps réel, hôte lance dès 2 → Task 4. ✅
- Écran de jeu = mod du solo (mêmes DOM/fonctions de rendu) ; bandeau joueurs (avatars + cœurs, toi/actif/mort) ; record + mot bonus masqués → Tasks 2/3/5. ✅
- Chaîne partagée, 1 mot/tour, jauge pilotée par la deadline serveur, saisie activée au seul tour actif → Task 5. ✅
- Lettres interdites partagées (bande + beat), highlight live, refus sans perte de vie → Task 5. ✅
- Score/rang **décoratif** côté client, réutilise la math d'`app.js` ; juice « à mort » (rang, jauges rareté/vitesse, toast, étincelles) pour l'auteur du coup → Tasks 1/5. ✅
- Perte de vie : flash **blanc** (autre) / **rose** (toi) + shake + beat, cœur éteint → Task 6. ✅
- Dernier en vie gagne : écran de fin (gagnant + trophée + score perso) + partage/rejouer → Task 6. ✅
- Déconnexion → `game_over` géré côté client → Task 6. ✅
- Non-régression du solo → Task 7. ✅

**Dépendance backend :** Task 1 (décomposition de score dans `hop_accepted`) doit être faite en premier — le reste du front en dépend pour le juice.

**Vérification :** navigateur (2 onglets) + suite pytest. Pas de framework de test JS (le projet n'en a pas ; on suit le pattern existant).
