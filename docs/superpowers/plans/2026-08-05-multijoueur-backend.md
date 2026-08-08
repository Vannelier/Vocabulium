# Multijoueur — Backend (salons + WebSocket) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construire le backend autoritaire du mode multijoueur : gestion des salons en mémoire, machine à états de partie (tours, vies, lettres interdites partagées, élimination) et couche WebSocket, en réutilisant la validation de hop existante.

**Architecture:** Approche 1 — un seul process FastAPI, salons dans un `dict` en mémoire derrière un `RoomManager` (seule porte d'accès à l'état → couture pour Redis plus tard). Toute la logique de partie est **pure Python** (aucun modèle, réseau ou horloge à l'intérieur des transitions) donc testable en TDD. La couche WebSocket valide chaque mot via les fonctions de scoring existantes (`score_hop`, `db.*`) puis applique le résultat à la `Room`. Une tâche de fond balaie les salons pour trancher les timeouts.

**Tech Stack:** Python 3.12, FastAPI (WebSockets natifs), pytest (nouveau), numpy/uvicorn (existants). Front vanilla — hors périmètre de ce plan.

**Référence spec :** `docs/superpowers/specs/2026-08-05-multijoueur-design.md`

---

## File Structure

- Create: `app/letters.py` — portage Python du module `web/letters.js` (ordre des lettres interdites, comptage, lettres fautives). Autorité serveur sur les lettres interdites. Pur, déterministe.
- Create: `app/rooms.py` — `Player`, `Room`, `RoomManager`. État en mémoire + toutes les transitions de partie. Pur (pas de réseau, pas de modèle, pas d'horloge interne).
- Create: `app/ws.py` — endpoint WebSocket, registre des connexions par salon, handlers de messages, broadcast, `validate_hop()` (le seul point qui touche le modèle → monkeypatchable en test), boucle de timeout.
- Modify: `app/main.py` — monter le router WebSocket + démarrer la boucle de timeout au startup.
- Create: `requirements-dev.txt` — `pytest`, `httpx` (client WebSocket de test de Starlette).
- Create: `tests/__init__.py`, `tests/test_letters.py`, `tests/test_rooms.py`, `tests/test_ws.py`.

**Convention de test :** `pytest` depuis la racine. Les tests de `letters`/`rooms` n'importent **jamais** `db`/le modèle (rapides). `test_ws` monkeypatch `validate_hop` pour ne pas charger le modèle.

---

## Task 0: Mise en place des tests

**Files:**
- Create: `requirements-dev.txt`
- Create: `tests/__init__.py`
- Create: `tests/test_smoke.py`

- [ ] **Step 1: Créer `requirements-dev.txt`**

```
pytest>=8.0
httpx>=0.27
```

- [ ] **Step 2: Installer (venv emprunté de Discoverix, comme le reste du projet)**

Run:
```bash
../Discoverix/.venv/Scripts/python.exe -m pip install pytest httpx
```
Expected: installation OK (ou déjà présents).

- [ ] **Step 3: Créer `tests/__init__.py` (vide) et un test smoke**

`tests/test_smoke.py` :
```python
def test_smoke():
    assert True
```

- [ ] **Step 4: Lancer pytest pour valider le harnais**

Run:
```bash
../Discoverix/.venv/Scripts/python.exe -m pytest tests/test_smoke.py -q
```
Expected: `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add requirements-dev.txt tests/__init__.py tests/test_smoke.py
git commit -m "test: harnais pytest (multijoueur backend)"
```

---

## Task 1: `app/letters.py` — portage des lettres interdites

Miroir Python de `web/letters.js` (mêmes règles → même feel que le solo). Déterministe avec un `rand` injecté.

**Files:**
- Create: `app/letters.py`
- Test: `tests/test_letters.py`

- [ ] **Step 1: Écrire les tests**

`tests/test_letters.py` :
```python
import random
from app import letters


def test_fold_strips_accents_and_case():
    assert letters.fold("É") == "e"
    assert letters.fold("ç") == "c"
    assert letters.fold("A") == "a"


def test_forbidden_count_progression():
    # +1 lettre tous les 5 mots, cumulatif, 0 au départ
    assert letters.forbidden_count(0, every=5) == 0
    assert letters.forbidden_count(4, every=5) == 0
    assert letters.forbidden_count(5, every=5) == 1
    assert letters.forbidden_count(12, every=5) == 2


def test_draw_order_is_deterministic_and_full_alphabet():
    r1 = random.Random(42).random
    r2 = random.Random(42).random
    o1 = letters.draw_order(r1)
    o2 = letters.draw_order(r2)
    assert o1 == o2                      # même graine -> même ordre
    assert sorted(o1) == sorted(letters.ALPHABET)   # 26 lettres, sans doublon


def test_draw_order_starts_mid_not_frequent():
    # les 2 premières interdites viennent du groupe MID (jamais e/a/s tout de suite)
    order = letters.draw_order(random.Random(1).random)
    assert order[0] in letters.MID
    assert order[1] in letters.MID


def test_active_forbidden_skips_target_letters():
    order = ["o", "u", "l", "d", "c"]
    # 2 lettres actives après 10 mots, en sautant 'u' (lettre de la cible)
    active = letters.active_forbidden(order, words=10, every=5, target_letters=["u"])
    assert "u" not in active
    assert active == ["o", "l"]


def test_offending_letters_accent_insensitive():
    assert set(letters.offending_letters("étage", ["e"])) == {"e"}   # é -> e
    assert letters.offending_letters("mot", ["z"]) == []
```

- [ ] **Step 2: Lancer les tests (doivent échouer)**

Run: `../Discoverix/.venv/Scripts/python.exe -m pytest tests/test_letters.py -q`
Expected: FAIL (`ModuleNotFoundError: app.letters`).

- [ ] **Step 3: Implémenter `app/letters.py`**

```python
"""Portage Python de web/letters.js — autorité serveur sur les lettres interdites.
Mêmes règles que le solo : +1 lettre tous les `every` mots, ordre dosé (MID puis
fréquente puis reste), accent-insensible. `rand` = callable renvoyant [0,1)."""
from __future__ import annotations

import unicodedata
from typing import Callable, Sequence

FREQ = {
    "a": 7.6, "b": 0.9, "c": 3.3, "d": 3.7, "e": 14.7, "f": 1.1, "g": 0.9,
    "h": 0.7, "i": 7.5, "j": 0.5, "k": 0.05, "l": 5.5, "m": 3.0, "n": 7.1,
    "o": 5.4, "p": 3.0, "q": 1.4, "r": 6.6, "s": 7.9, "t": 7.2, "u": 6.3,
    "v": 1.6, "w": 0.04, "x": 0.4, "y": 0.3, "z": 0.1,
}
ALPHABET = list(FREQ.keys())
MID = ["o", "u", "l", "d", "c", "p", "m", "v", "g", "b", "f", "h"]
FREQUENT = ["e", "a", "s", "r", "t", "i", "n"]


def fold(ch: str) -> str:
    """é->e, ç->c, À->a. Replie accents + minuscule."""
    return "".join(
        c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c)
    ).lower()


def _shuffle(arr: list[str], rand: Callable[[], float]) -> list[str]:
    a = list(arr)
    for i in range(len(a) - 1, 0, -1):
        j = int(rand() * (i + 1))
        a[i], a[j] = a[j], a[i]
    return a


def draw_order(rand: Callable[[], float]) -> list[str]:
    """2 lettres MID, puis 1 FRÉQUENTE, puis le reste au hasard. Déterministe."""
    mid = _shuffle(MID, rand)
    freq = _shuffle(FREQUENT, rand)
    order = [mid[0], mid[1], freq[0]]
    used = set(order)
    rest = _shuffle([L for L in ALPHABET if L not in used], rand)
    return order + rest


def forbidden_count(words: int, every: int = 5, start: int = 0) -> int:
    return start + words // every


def active_forbidden(order: Sequence[str], words: int, every: int = 5,
                     start: int = 0, target_letters: Sequence[str] = ()) -> list[str]:
    """Les `forbidden_count` premières de l'ordre, en sautant les lettres de la cible."""
    skip = set(target_letters)
    avail = [L for L in order if L not in skip] if skip else list(order)
    return avail[: forbidden_count(words, every, start)]


def offending_letters(word: str, active: Sequence[str]) -> list[str]:
    """Lettres interdites (parmi `active`) présentes dans `word`, accents repliés."""
    aset = set(active)
    hit = []
    for ch in word:
        f = fold(ch)
        if f in aset and f not in hit:
            hit.append(f)
    return hit
```

- [ ] **Step 4: Lancer les tests (doivent passer)**

Run: `../Discoverix/.venv/Scripts/python.exe -m pytest tests/test_letters.py -q`
Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add app/letters.py tests/test_letters.py
git commit -m "feat: portage Python des lettres interdites (app/letters.py)"
```

---

## Task 2: `app/rooms.py` — salons, joueurs, lobby

État + création + lobby. Pas encore la partie (Task 3-4).

**Files:**
- Create: `app/rooms.py`
- Test: `tests/test_rooms.py`

- [ ] **Step 1: Écrire les tests (lobby)**

`tests/test_rooms.py` :
```python
import pytest
from app.rooms import RoomManager, Room, LIVES, MAX_PLAYERS, MIN_PLAYERS


def test_create_room_has_unique_readable_code():
    mgr = RoomManager()
    a = mgr.create()
    b = mgr.create()
    assert a.code != b.code
    assert len(a.code) == 4
    assert all(c not in a.code for c in "O0I1L")   # code lisible


def test_get_room_by_code():
    mgr = RoomManager()
    room = mgr.create()
    assert mgr.get(room.code) is room
    assert mgr.get("ZZZZ") is None


def test_add_players_assigns_host_and_colors():
    room = Room(code="ROSE")
    p1 = room.add_player("toi")
    p2 = room.add_player("Léa")
    assert p1.is_host is True and p2.is_host is False
    assert p1.lives == LIVES
    assert p1.color != p2.color            # couleurs distinctes


def test_room_full_rejects_extra_player():
    room = Room(code="ROSE")
    for i in range(MAX_PLAYERS):
        assert room.add_player(f"p{i}") is not None
    assert room.add_player("trop") is None


def test_can_start_needs_min_players():
    room = Room(code="ROSE")
    room.add_player("solo")
    assert room.can_start() is False
    room.add_player("deux")
    assert room.can_start() is True


def test_start_sets_playing_state_and_seed():
    room = Room(code="ROSE")
    room.add_player("a"); room.add_player("b")
    room.start(seed_word="orage", forbidden_order=list("abcdef"))
    assert room.state == "playing"
    assert room.current_word == "orage"
    assert "orage" in room.played
    assert room.active_player().name == "a"
```

- [ ] **Step 2: Lancer (échec attendu)**

Run: `../Discoverix/.venv/Scripts/python.exe -m pytest tests/test_rooms.py -q`
Expected: FAIL (`ModuleNotFoundError: app.rooms`).

- [ ] **Step 3: Implémenter `app/rooms.py` (partie lobby)**

```python
"""Salons multijoueur en mémoire — état + transitions PURES (ni réseau, ni modèle,
ni horloge interne). La couche ws.py valide les mots et appelle ces méthodes."""
from __future__ import annotations

import secrets
from dataclasses import dataclass, field

from app import letters

CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"   # sans O/0/I/1/L ambigus
CODE_LEN = 4
LIVES = 3
MIN_PLAYERS = 2
MAX_PLAYERS = 6
LETTER_EVERY = 5
# palette (style.css) : pink, cyan, gold, green, violet, orange
COLORS = ["#ff2e97", "#22e6ff", "#ffd23f", "#20ffb2", "#b25cff", "#ff7a2f"]


@dataclass
class Player:
    id: str
    name: str
    color: str
    lives: int = LIVES
    alive: bool = True
    is_host: bool = False
    score: int = 0            # décoratif, reporté par le client


@dataclass
class Room:
    code: str
    players: list[Player] = field(default_factory=list)
    state: str = "lobby"                 # "lobby" | "playing" | "over"
    current_word: str | None = None
    played: set[str] = field(default_factory=set)
    forbidden_order: list[str] = field(default_factory=list)
    word_count: int = 0
    active_index: int = 0
    turn_deadline: float = 0.0           # monotonic, posé par ws.py
    winner_id: str | None = None

    # --- lobby ---
    def add_player(self, name: str, pid: str | None = None) -> Player | None:
        if self.state != "lobby" or len(self.players) >= MAX_PLAYERS:
            return None
        used = {p.color for p in self.players}
        color = next((c for c in COLORS if c not in used), COLORS[0])
        p = Player(id=pid or secrets.token_hex(4), name=name, color=color,
                   is_host=(len(self.players) == 0))
        self.players.append(p)
        return p

    def player(self, pid: str) -> Player | None:
        return next((p for p in self.players if p.id == pid), None)

    def remove_player(self, pid: str) -> None:
        self.players = [p for p in self.players if p.id != pid]

    def can_start(self) -> bool:
        return self.state == "lobby" and len(self.players) >= MIN_PLAYERS

    def start(self, seed_word: str, forbidden_order: list[str]) -> None:
        self.state = "playing"
        self.current_word = seed_word
        self.played = {seed_word}
        self.forbidden_order = forbidden_order
        self.word_count = 0
        self.active_index = 0
        self.winner_id = None

    def active_player(self) -> Player | None:
        if not self.players:
            return None
        return self.players[self.active_index]

    def alive_players(self) -> list[Player]:
        return [p for p in self.players if p.alive]

    def active_forbidden(self) -> list[str]:
        return letters.active_forbidden(self.forbidden_order, self.word_count, LETTER_EVERY)


class RoomManager:
    def __init__(self) -> None:
        self.rooms: dict[str, Room] = {}

    def _new_code(self) -> str:
        while True:
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LEN))
            if code not in self.rooms:
                return code

    def create(self) -> Room:
        room = Room(code=self._new_code())
        self.rooms[room.code] = room
        return room

    def get(self, code: str) -> Room | None:
        return self.rooms.get(code)

    def drop(self, code: str) -> None:
        self.rooms.pop(code, None)
```

- [ ] **Step 4: Lancer (doivent passer)**

Run: `../Discoverix/.venv/Scripts/python.exe -m pytest tests/test_rooms.py -q`
Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add app/rooms.py tests/test_rooms.py
git commit -m "feat: salons + lobby (app/rooms.py)"
```

---

## Task 3: Mécanique de tour — `Room.submit`

Appliquer un coup validé : contrôle du tour, lettre interdite, déjà joué, proximité ; avancement du tour + escalade des lettres.

**Files:**
- Modify: `app/rooms.py` (ajouter méthodes `_next_alive_index`, `submit`)
- Test: `tests/test_rooms.py` (ajouter)

- [ ] **Step 1: Ajouter les tests de `submit`**

Ajouter à `tests/test_rooms.py` :
```python
def _playing_room():
    room = Room(code="ROSE")
    room.add_player("a"); room.add_player("b")
    # ordre où 'z' est interdite dès 5 mots (pour tester le refus lettre)
    room.start(seed_word="orage", forbidden_order=["z"] + [c for c in "abcdefghij"])
    return room


def test_submit_rejects_when_not_your_turn():
    room = _playing_room()
    b = room.players[1]
    res = room.submit(b.id, "foudre", accepted=True)   # ce n'est pas le tour de b
    assert res["ok"] is False and res["reason"] == "not_your_turn"


def test_submit_accepted_advances_word_and_turn():
    room = _playing_room()
    a = room.players[0]
    res = room.submit(a.id, "foudre", accepted=True)
    assert res["ok"] is True
    assert res["current"] == "foudre"
    assert room.current_word == "foudre"
    assert room.word_count == 1
    assert "foudre" in room.played
    assert res["active"] == room.players[1].id       # tour passé à b


def test_submit_rejects_already_played():
    room = _playing_room()
    a = room.players[0]
    res = room.submit(a.id, "orage", accepted=True)   # = seed, déjà joué
    assert res["ok"] is False and res["reason"] == "already_played"


def test_submit_rejects_too_far():
    room = _playing_room()
    a = room.players[0]
    res = room.submit(a.id, "foudre", accepted=False)   # proximité insuffisante
    assert res["ok"] is False and res["reason"] == "too_far"
    assert room.word_count == 0                          # rien n'avance


def test_submit_rejects_forbidden_letter():
    # forcer 1 lettre interdite active ('z') : word_count doit être >=5.
    room = _playing_room()
    room.word_count = 5           # 1 lettre active = 'z' (1re de l'ordre)
    a = room.active_player()
    res = room.submit(a.id, "zebre", accepted=True)
    assert res["ok"] is False and res["reason"] == "forbidden_letter"


def test_submit_signals_new_forbidden_letter_on_escalation():
    room = _playing_room()
    a = room.players[0]
    room.word_count = 4                       # le prochain mot accepté -> 5 -> escalade
    res = room.submit(a.id, "foudre", accepted=True)
    assert res["ok"] is True
    assert res["new_forbidden"] == "z"        # 1re lettre de l'ordre devient active
```

- [ ] **Step 2: Lancer (échec attendu)**

Run: `../Discoverix/.venv/Scripts/python.exe -m pytest tests/test_rooms.py -q`
Expected: FAIL (`AttributeError: 'Room' object has no attribute 'submit'`).

- [ ] **Step 3: Implémenter `_next_alive_index` et `submit` dans `Room`**

Ajouter dans la classe `Room` :
```python
    def _next_alive_index(self, start: int) -> int:
        n = len(self.players)
        for step in range(1, n + 1):
            i = (start + step) % n
            if self.players[i].alive:
                return i
        return start

    def submit(self, pid: str, canonical_word: str, accepted: bool) -> dict:
        """Applique un coup DÉJÀ validé côté proximité (`accepted`). Contrôle le
        tour, la lettre interdite, l'anti-rejouage ; avance le tour + l'escalade."""
        active = self.active_player()
        if self.state != "playing" or active is None or active.id != pid:
            return {"ok": False, "reason": "not_your_turn"}
        if canonical_word in self.played:
            return {"ok": False, "reason": "already_played"}
        if letters.offending_letters(canonical_word, self.active_forbidden()):
            return {"ok": False, "reason": "forbidden_letter"}
        if not accepted:
            return {"ok": False, "reason": "too_far"}

        before = letters.forbidden_count(self.word_count, LETTER_EVERY)
        self.played.add(canonical_word)
        self.current_word = canonical_word
        self.word_count += 1
        after = letters.forbidden_count(self.word_count, LETTER_EVERY)
        new_forbidden = self.active_forbidden()[after - 1] if after > before else None

        self.active_index = self._next_alive_index(self.active_index)
        return {
            "ok": True,
            "current": self.current_word,
            "word_count": self.word_count,
            "active": self.active_player().id,
            "new_forbidden": new_forbidden,
            "scored_by": pid,
        }
```

- [ ] **Step 4: Lancer (doivent passer)**

Run: `../Discoverix/.venv/Scripts/python.exe -m pytest tests/test_rooms.py -q`
Expected: tous verts (12 passed).

- [ ] **Step 5: Commit**

```bash
git add app/rooms.py tests/test_rooms.py
git commit -m "feat: mécanique de tour Room.submit (validation + escalade)"
```

---

## Task 4: Timeout, perte de vie, élimination, fin de partie

**Files:**
- Modify: `app/rooms.py` (ajouter `timeout`, `_finish_if_over`)
- Test: `tests/test_rooms.py` (ajouter)

- [ ] **Step 1: Ajouter les tests**

Ajouter à `tests/test_rooms.py` :
```python
def test_timeout_costs_a_life_and_passes_turn():
    room = _playing_room()
    a = room.players[0]
    res = room.timeout(a.id)
    assert a.lives == LIVES - 1
    assert a.alive is True
    assert res["life_lost"] == a.id
    assert res["active"] == room.players[1].id        # tour passé
    assert room.current_word == "orage"               # le mot NE change pas


def test_timeout_ignored_if_not_active_player():
    room = _playing_room()
    b = room.players[1]                                # pas le joueur actif
    res = room.timeout(b.id)
    assert res["ok"] is False
    assert b.lives == LIVES


def test_third_timeout_eliminates_player():
    room = _playing_room()
    a = room.players[0]
    room.timeout(a.id); room.active_index = 0
    room.timeout(a.id); room.active_index = 0
    res = room.timeout(a.id)
    assert a.lives == 0 and a.alive is False
    assert res["eliminated"] is True


def test_last_survivor_ends_game():
    room = _playing_room()
    a, b = room.players
    # a se fait éliminer (3 timeouts), b reste seul -> fin
    for _ in range(3):
        room.active_index = 0
        res = room.timeout(a.id)
    assert room.state == "over"
    assert room.winner_id == b.id
    assert res["over"] is True and res["winner"] == b.id
```

- [ ] **Step 2: Lancer (échec attendu)**

Run: `../Discoverix/.venv/Scripts/python.exe -m pytest tests/test_rooms.py -q`
Expected: FAIL (`AttributeError: ... 'timeout'`).

- [ ] **Step 3: Implémenter `timeout` et `_finish_if_over`**

Ajouter dans la classe `Room` :
```python
    def timeout(self, pid: str) -> dict:
        """Le joueur actif n'a pas répondu à temps : -1 vie, éventuelle élimination,
        on passe au suivant (le mot courant NE change pas). Fin si 1 survivant."""
        active = self.active_player()
        if self.state != "playing" or active is None or active.id != pid:
            return {"ok": False}
        active.lives -= 1
        eliminated = active.lives <= 0
        if eliminated:
            active.alive = False
        res = {
            "ok": True, "life_lost": pid, "lives": active.lives,
            "eliminated": eliminated, "over": False, "winner": None,
        }
        if self._finish_if_over():
            res["over"] = True
            res["winner"] = self.winner_id
            res["active"] = None
            return res
        self.active_index = self._next_alive_index(self.active_index)
        res["active"] = self.active_player().id
        return res

    def _finish_if_over(self) -> bool:
        alive = self.alive_players()
        if len(alive) <= 1:
            self.state = "over"
            self.winner_id = alive[0].id if alive else None
            return True
        return False
```

- [ ] **Step 4: Lancer (doivent passer)**

Run: `../Discoverix/.venv/Scripts/python.exe -m pytest tests/test_rooms.py -q`
Expected: tous verts (16 passed).

- [ ] **Step 5: Commit**

```bash
git add app/rooms.py tests/test_rooms.py
git commit -m "feat: timeout, élimination et fin de partie (Room.timeout)"
```

---

## Task 5: Couche WebSocket — `app/ws.py`

Protocole client↔serveur, registre de connexions, broadcast, validation branchée sur le modèle (isolée pour les tests).

### Protocole (interface pour le plan Frontend)

Messages **client → serveur** (JSON) :
- `{"action": "create", "name": "toi"}` → crée un salon, l'émetteur devient hôte.
- `{"action": "join", "code": "ROSE", "name": "Léa"}` → rejoint le lobby.
- `{"action": "start"}` → hôte only ; lance la partie.
- `{"action": "hop", "word": "foudre"}` → joueur actif ; tente un mot.

Messages **serveur → client** (JSON), tous incluent `type` :
- `{"type": "joined", "code": "ROSE", "you": "<pid>", "state": {...}}` (à l'émetteur).
- `{"type": "state", "state": {...}}` (broadcast lobby/partie — voir `_room_state`).
- `{"type": "hop_accepted", "current": "foudre", "word_count": 1, "active": "<pid>", "scored_by": "<pid>", "new_forbidden": null, "state": {...}}`
- `{"type": "hop_rejected", "reason": "forbidden_letter|too_far|already_played|not_your_turn|unknown_word"}` (à l'émetteur only).
- `{"type": "turn", "active": "<pid>", "current": "orage", "deadline_ms": 1234567890}` (broadcast à chaque nouveau tour).
- `{"type": "life_lost", "pid": "<pid>", "lives": 2, "eliminated": false, "state": {...}}` (broadcast → juice).
- `{"type": "game_over", "winner": "<pid>", "state": {...}}` (broadcast).
- `{"type": "error", "reason": "..."}` (à l'émetteur).

`_room_state(room)` (dict sérialisable) :
```json
{"code":"ROSE","state":"playing","current":"orage","word_count":6,
 "active":"<pid>","forbidden":["k","w"],
 "players":[{"id":"..","name":"toi","color":"#ff2e97","lives":2,"alive":true,"host":true}]}
```

**Files:**
- Create: `app/ws.py`
- Test: `tests/test_ws.py`

- [ ] **Step 1: Écrire les tests (validate_hop monkeypatché → pas de modèle)**

`tests/test_ws.py` :
```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import ws


def _app(monkeypatch):
    # validate_hop stub : "foudre"/"pluie" acceptés, le reste rejeté. Pas de modèle.
    def fake_validate(current, word):
        canon = word.lower()
        if canon in {"foudre", "pluie", "vent"}:
            return {"ok": True, "accepted": True, "canonical": canon}
        return {"ok": False, "reason": "unknown_word"}
    monkeypatch.setattr(ws, "validate_hop", fake_validate)
    # seed déterministe pour le test
    monkeypatch.setattr(ws, "pick_seed", lambda: "orage")
    monkeypatch.setattr(ws, "make_forbidden_order", lambda: list("zqxwkjbfmgpv"))
    app = FastAPI()
    app.include_router(ws.router)
    return app


def test_create_and_join_lobby(monkeypatch):
    client = TestClient(_app(monkeypatch))
    with client.websocket_connect("/ws") as host:
        host.send_json({"action": "create", "name": "toi"})
        msg = host.receive_json()
        assert msg["type"] == "joined"
        code = msg["code"]
        with client.websocket_connect("/ws") as guest:
            guest.send_json({"action": "join", "code": code, "name": "Léa"})
            assert guest.receive_json()["type"] == "joined"
            # l'hôte reçoit un broadcast d'état avec 2 joueurs
            state = host.receive_json()
            names = [p["name"] for p in state["state"]["players"]]
            assert names == ["toi", "Léa"]


def test_full_turn_flow(monkeypatch):
    client = TestClient(_app(monkeypatch))
    with client.websocket_connect("/ws") as host, \
         client.websocket_connect("/ws") as guest:
        host.send_json({"action": "create", "name": "toi"}); host.receive_json()
        code = ws.manager.rooms and list(ws.manager.rooms)[0]
        guest.send_json({"action": "join", "code": code, "name": "Léa"})
        guest.receive_json(); host.receive_json()          # joined + state
        host.send_json({"action": "start"})
        # les deux reçoivent 'turn'
        t = host.receive_json()
        while t["type"] != "turn":
            t = host.receive_json()
        assert t["current"] == "orage"
        # l'hôte (actif) joue un mot accepté
        host.send_json({"action": "hop", "word": "foudre"})
        acc = host.receive_json()
        while acc["type"] != "hop_accepted":
            acc = host.receive_json()
        assert acc["current"] == "foudre"
```

- [ ] **Step 2: Lancer (échec attendu)**

Run: `../Discoverix/.venv/Scripts/python.exe -m pytest tests/test_ws.py -q`
Expected: FAIL (`ModuleNotFoundError: app.ws`).

- [ ] **Step 3: Implémenter `app/ws.py`**

```python
"""Couche WebSocket du mode multijoueur. Valide les mots via le scoring existant
(isolé dans validate_hop pour les tests) puis applique à la Room, et broadcast."""
from __future__ import annotations

import random
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app import letters
from app.rooms import RoomManager

router = APIRouter()
manager = RoomManager()

# connexions : code salon -> { pid: WebSocket }
_conns: dict[str, dict[str, WebSocket]] = {}
# lien inverse pour le nettoyage à la déconnexion
_who: dict[WebSocket, tuple[str, str]] = {}   # ws -> (code, pid)


# --- points d'intégration (monkeypatchés en test pour éviter le modèle) --------
def validate_hop(current: str, word: str) -> dict:
    """Validation proximité via le scoring existant. Importé paresseusement pour
    ne charger le modèle qu'en prod (les tests monkeypatchent cette fonction)."""
    from app.main import db                       # db = Vocab() (modèle chargé)
    from app.scoring import score_hop, same_lemma
    canon = db.canonical(word)
    if canon is None:
        return {"ok": False, "reason": "unknown_word"}
    prev = db.canonical(current)
    if canon == prev or same_lemma(prev, canon):
        return {"ok": False, "reason": "already_played"}
    prox = db.prox(prev, canon)
    res = score_hop(prox, db.zipf(canon), 0.0)
    return {"ok": True, "accepted": res.zone != "reject", "canonical": canon}


def pick_seed() -> str:
    from app.main import db
    from app.seed import random_seed
    return random_seed(db.seed_pool())


def make_forbidden_order() -> list[str]:
    return letters.draw_order(random.Random().random)


TURN_SECONDS = 15.0


def _room_state(room) -> dict:
    return {
        "code": room.code, "state": room.state, "current": room.current_word,
        "word_count": room.word_count,
        "active": room.active_player().id if room.active_player() else None,
        "forbidden": room.active_forbidden() if room.state == "playing" else [],
        "players": [
            {"id": p.id, "name": p.name, "color": p.color, "lives": p.lives,
             "alive": p.alive, "host": p.is_host}
            for p in room.players
        ],
    }


async def _send(ws: WebSocket, msg: dict) -> None:
    await ws.send_json(msg)


async def _broadcast(code: str, msg: dict) -> None:
    for ws in list(_conns.get(code, {}).values()):
        try:
            await ws.send_json(msg)
        except Exception:
            pass


def _start_turn(room) -> dict:
    room.turn_deadline = time.monotonic() + TURN_SECONDS
    return {"type": "turn", "active": room.active_player().id,
            "current": room.current_word,
            "deadline_ms": int(room.turn_deadline * 1000)}


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    try:
        while True:
            data = await ws.receive_json()
            action = data.get("action")

            if action == "create":
                room = manager.create()
                p = room.add_player(data.get("name", "?"))
                _conns.setdefault(room.code, {})[p.id] = ws
                _who[ws] = (room.code, p.id)
                await _send(ws, {"type": "joined", "code": room.code,
                                 "you": p.id, "state": _room_state(room)})

            elif action == "join":
                room = manager.get(data.get("code", ""))
                if room is None:
                    await _send(ws, {"type": "error", "reason": "no_room"}); continue
                p = room.add_player(data.get("name", "?"))
                if p is None:
                    await _send(ws, {"type": "error", "reason": "full_or_started"}); continue
                _conns.setdefault(room.code, {})[p.id] = ws
                _who[ws] = (room.code, p.id)
                await _send(ws, {"type": "joined", "code": room.code,
                                 "you": p.id, "state": _room_state(room)})
                await _broadcast(room.code, {"type": "state", "state": _room_state(room)})

            elif action == "start":
                code, pid = _who.get(ws, (None, None))
                room = manager.get(code) if code else None
                if room is None or room.player(pid) is None or not room.player(pid).is_host:
                    await _send(ws, {"type": "error", "reason": "not_host"}); continue
                if not room.can_start():
                    await _send(ws, {"type": "error", "reason": "need_players"}); continue
                room.start(pick_seed(), make_forbidden_order())
                await _broadcast(room.code, {"type": "state", "state": _room_state(room)})
                await _broadcast(room.code, _start_turn(room))

            elif action == "hop":
                code, pid = _who.get(ws, (None, None))
                room = manager.get(code) if code else None
                if room is None:
                    continue
                v = validate_hop(room.current_word, data.get("word", ""))
                if not v["ok"]:
                    await _send(ws, {"type": "hop_rejected", "reason": v["reason"]}); continue
                res = room.submit(pid, v["canonical"], v["accepted"])
                if not res["ok"]:
                    await _send(ws, {"type": "hop_rejected", "reason": res["reason"]}); continue
                await _broadcast(room.code, {
                    "type": "hop_accepted", "current": res["current"],
                    "word_count": res["word_count"], "active": res["active"],
                    "scored_by": res["scored_by"], "new_forbidden": res["new_forbidden"],
                    "state": _room_state(room)})
                await _broadcast(room.code, _start_turn(room))

    except WebSocketDisconnect:
        _cleanup(ws)


def _cleanup(ws: WebSocket) -> None:
    code, pid = _who.pop(ws, (None, None))
    if code is None:
        return
    _conns.get(code, {}).pop(pid, None)
    room = manager.get(code)
    if room:
        room.remove_player(pid)
        if not room.players:
            manager.drop(code)
```

- [ ] **Step 4: Lancer (doivent passer)**

Run: `../Discoverix/.venv/Scripts/python.exe -m pytest tests/test_ws.py -q`
Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add app/ws.py tests/test_ws.py
git commit -m "feat: couche WebSocket + protocole multijoueur (app/ws.py)"
```

---

## Task 6: Boucle de timeout + branchement dans `main.py`

Une tâche de fond balaie les salons `playing` et tranche les tours expirés.

**Files:**
- Modify: `app/ws.py` (ajouter `timeout_loop`)
- Modify: `app/main.py` (inclure le router + lancer la boucle au startup)
- Test: `tests/test_ws.py` (ajouter un test de timeout à deadline courte)

- [ ] **Step 1: Ajouter le test de timeout**

Ajouter à `tests/test_ws.py` :
```python
import asyncio


def test_timeout_loses_life(monkeypatch):
    monkeypatch.setattr(ws, "TURN_SECONDS", 0.05)   # deadline quasi immédiate
    client = TestClient(_app(monkeypatch))
    with client.websocket_connect("/ws") as host, \
         client.websocket_connect("/ws") as guest:
        host.send_json({"action": "create", "name": "toi"}); host.receive_json()
        code = list(ws.manager.rooms)[0]
        guest.send_json({"action": "join", "code": code, "name": "Léa"})
        guest.receive_json(); host.receive_json()
        host.send_json({"action": "start"})
        # on ne joue pas -> la boucle doit émettre life_lost
        seen = None
        for _ in range(20):
            m = host.receive_json()
            if m["type"] == "life_lost":
                seen = m; break
        assert seen is not None and seen["lives"] == 2
```

- [ ] **Step 2: Lancer (échec attendu)**

Run: `../Discoverix/.venv/Scripts/python.exe -m pytest tests/test_ws.py::test_timeout_loses_life -q`
Expected: FAIL (aucune boucle → pas de `life_lost`).

- [ ] **Step 3: Ajouter `timeout_loop` dans `app/ws.py`**

```python
import asyncio


async def timeout_loop() -> None:
    """Balaie les salons en jeu ; à deadline dépassée, applique le timeout au
    joueur actif et broadcast (life_lost / game_over / turn suivant)."""
    while True:
        now = time.monotonic()
        for code, room in list(manager.rooms.items()):
            if room.state != "playing":
                continue
            if room.turn_deadline and now >= room.turn_deadline:
                active = room.active_player()
                if active is None:
                    continue
                res = room.timeout(active.id)
                if not res.get("ok"):
                    continue
                await _broadcast(code, {"type": "life_lost", "pid": res["life_lost"],
                                        "lives": res["lives"],
                                        "eliminated": res["eliminated"],
                                        "state": _room_state(room)})
                if res["over"]:
                    await _broadcast(code, {"type": "game_over", "winner": res["winner"],
                                            "state": _room_state(room)})
                    room.turn_deadline = 0.0
                else:
                    await _broadcast(code, _start_turn(room))
        await asyncio.sleep(0.05)
```

- [ ] **Step 4: Brancher dans `app/main.py`**

Modifier `app/main.py` — après la création de `app = FastAPI(...)` et **avant** `app.mount("/", StaticFiles...)` (le mount `/` capte tout, il doit rester dernier). Ajouter :
```python
import asyncio
from app import ws as ws_module

app.include_router(ws_module.router)


@app.on_event("startup")
async def _start_timeout_loop() -> None:
    asyncio.create_task(ws_module.timeout_loop())
```

- [ ] **Step 5: Lancer tous les tests**

Run: `../Discoverix/.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: tout vert (letters 6 + rooms 16 + ws 3 = 25 passed).

- [ ] **Step 6: Commit**

```bash
git add app/ws.py app/main.py tests/test_ws.py
git commit -m "feat: boucle de timeout + branchement WebSocket dans main.py"
```

---

## Task 7: Smoke test manuel (serveur réel)

**Files:** aucun (vérification).

- [ ] **Step 1: Démarrer le serveur**

Run:
```bash
../Discoverix/.venv/Scripts/python.exe -m uvicorn app.main:app --port 8077
```
Expected: démarrage OK (~4 s de chargement du modèle), pas d'erreur d'import `app.ws`.

- [ ] **Step 2: Tester le WebSocket au navigateur**

Dans la console du navigateur sur `http://127.0.0.1:8077` :
```javascript
const w = new WebSocket("ws://127.0.0.1:8077/ws");
w.onmessage = (e) => console.log(JSON.parse(e.data));
w.onopen = () => w.send(JSON.stringify({action: "create", name: "moi"}));
```
Expected : un message `{type:"joined", code:"XXXX", you:"...", state:{...}}` s'affiche.

- [ ] **Step 3: Vérifier `create` → `start` (à 1 joueur, doit refuser)**

```javascript
w.send(JSON.stringify({action: "start"}));
```
Expected : `{type:"error", reason:"need_players"}` (moins de 2 joueurs).

- [ ] **Step 4: Arrêter le serveur (Ctrl+C).**

Pas de commit (vérification seulement). Le backend est prêt pour le plan Frontend.

---

## Self-Review — couverture spec

- Chaîne partagée, 1 mot/tour, jauge=chrono → `Room.current_word`, `submit` avance le tour, `_start_turn` (deadline). ✅
- Jauge à sec = −1 vie + passe au suivant, mot inchangé → `Room.timeout`. ✅
- Validité : cos ≥ seuil (`validate_hop`), lettre interdite (`offending_letters`), déjà joué, refus = temps seulement → `submit` + `hop_rejected` sans perte de vie. ✅
- Lettres interdites partagées, +1/5 mots, module réutilisé → `app/letters.py` + `active_forbidden` sur `word_count`. ✅
- 3 vies, 2–6 joueurs, dernier en vie gagne → `LIVES`, `MIN/MAX_PLAYERS`, `_finish_if_over`. ✅
- Score décoratif client → `Player.score` reporté, non utilisé pour la victoire. ✅
- État serveur autoritaire + WebSocket, Approche 1, `RoomManager` seule porte → `app/rooms.py` + `app/ws.py`. ✅
- Salon : créer/rejoindre par code, hôte lance, lien partageable → actions `create`/`join`/`start`, code lisible. ✅ (l'UI du lien = plan Frontend)
- Déconnexion simple (retrait + saut de tour) → `_cleanup` + `_next_alive_index`. ✅
- Couture scaling (Redis plus tard) → tout l'état dans `RoomManager`. ✅

**Hors périmètre de ce plan (→ plan Frontend) :** menu/lobby UI, bandeau joueurs + cœurs, rendu piloté par l'état serveur, juice (flash blanc/rose), écran de fin + partage, remplacement du bouton « Mot du jour ».
