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

    def remove_player(self, pid: str) -> dict:
        """Retire un joueur. En lobby : simple retrait (+ promotion d'hôte). En cours
        de partie : gère l'attrition (fin si 1 survivant) et, si le joueur ACTIF part,
        passe la main au prochain vivant en invalidant la deadline. Retourne des infos
        pour que la couche réseau sache quoi diffuser."""
        idx = next((i for i, p in enumerate(self.players) if p.id == pid), None)
        if idx is None:
            return {"removed": False}
        was_host = self.players[idx].is_host
        was_active = (self.state == "playing" and idx == self.active_index)
        self.players.pop(idx)
        if not self.players:
            self.active_index = 0
            return {"removed": True, "empty": True}
        # garder active_index pointé sur le même joueur logique et jamais hors bornes
        if idx < self.active_index:
            self.active_index -= 1
        if self.active_index >= len(self.players):
            self.active_index = 0
        if was_host and not any(p.is_host for p in self.players):
            self.players[0].is_host = True

        result = {"removed": True, "empty": False, "over": False, "turn_handoff": False}
        if self.state != "playing":
            return result
        # attrition : s'il ne reste qu'un vivant, la partie se termine
        if self._finish_if_over():
            result["over"] = True
            result["winner"] = self.winner_id
            return result
        # le joueur ACTIF est parti : passer la main au prochain vivant (en sautant les
        # éliminés) et invalider la deadline -> ws relancera le tour.
        if was_active:
            if not self.players[self.active_index].alive:
                self.active_index = self._next_alive_index(self.active_index)
            self.turn_deadline = 0.0
            result["turn_handoff"] = True
        return result

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
        forbidden = self.active_forbidden()
        if letters.offending_letters(canonical_word, forbidden):
            return {"ok": False, "reason": "forbidden_letter"}
        if not accepted:
            return {"ok": False, "reason": "too_far"}

        before = letters.forbidden_count(self.word_count, LETTER_EVERY)
        self.played.add(canonical_word)
        self.current_word = canonical_word
        self.word_count += 1
        after = letters.forbidden_count(self.word_count, LETTER_EVERY)
        active_now = self.active_forbidden()
        # borne : le pool de lettres peut être épuisé -> pas de nouvelle lettre
        new_forbidden = active_now[after - 1] if before < after <= len(active_now) else None

        self.active_index = self._next_alive_index(self.active_index)
        self.turn_deadline = 0.0   # invalidée jusqu'à ce que ws relance le tour (évite un timeout sur le nouveau joueur)
        return {
            "ok": True,
            "current": self.current_word,
            "word_count": self.word_count,
            "active": self.active_player().id,
            "new_forbidden": new_forbidden,
            "scored_by": pid,
        }

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
        if eliminated and self._finish_if_over():
            res["over"] = True
            res["winner"] = self.winner_id
            res["active"] = None
            return res
        self.active_index = self._next_alive_index(self.active_index)
        self.turn_deadline = 0.0
        res["active"] = self.active_player().id
        return res

    def _finish_if_over(self) -> bool:
        alive = self.alive_players()
        if len(alive) <= 1:
            self.state = "over"
            self.winner_id = alive[0].id if alive else None
            return True
        return False


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
