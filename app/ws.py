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

TURN_SECONDS = 15.0


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
                await ws.send_json({"type": "joined", "code": room.code,
                                    "you": p.id, "state": _room_state(room)})

            elif action == "join":
                room = manager.get(data.get("code", ""))
                if room is None:
                    await ws.send_json({"type": "error", "reason": "no_room"}); continue
                p = room.add_player(data.get("name", "?"))
                if p is None:
                    await ws.send_json({"type": "error", "reason": "full_or_started"}); continue
                _conns.setdefault(room.code, {})[p.id] = ws
                _who[ws] = (room.code, p.id)
                await ws.send_json({"type": "joined", "code": room.code,
                                    "you": p.id, "state": _room_state(room)})
                await _broadcast(room.code, {"type": "state", "state": _room_state(room)})

            elif action == "start":
                code, pid = _who.get(ws, (None, None))
                room = manager.get(code) if code else None
                if room is None or room.player(pid) is None or not room.player(pid).is_host:
                    await ws.send_json({"type": "error", "reason": "not_host"}); continue
                if not room.can_start():
                    await ws.send_json({"type": "error", "reason": "need_players"}); continue
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
                    await ws.send_json({"type": "hop_rejected", "reason": v["reason"]}); continue
                res = room.submit(pid, v["canonical"], v["accepted"])
                if not res["ok"]:
                    await ws.send_json({"type": "hop_rejected", "reason": res["reason"]}); continue
                await _broadcast(room.code, {
                    "type": "hop_accepted", "current": res["current"],
                    "word_count": res["word_count"], "active": res["active"],
                    "scored_by": res["scored_by"], "new_forbidden": res["new_forbidden"],
                    "state": _room_state(room)})
                await _broadcast(room.code, _start_turn(room))

    except WebSocketDisconnect:
        await _cleanup(ws)


async def _cleanup(ws: WebSocket) -> None:
    code, pid = _who.pop(ws, (None, None))
    if code is None:
        return
    _conns.get(code, {}).pop(pid, None)
    room = manager.get(code)
    if room is None:
        return
    was_playing = room.state == "playing"
    room.remove_player(pid)
    if not room.players:
        manager.drop(code)
        return
    await _broadcast(code, {"type": "state", "state": _room_state(room)})
    # une déconnexion en cours de partie peut terminer la partie (attrition)
    if was_playing and room.state == "over":
        await _broadcast(code, {"type": "game_over", "winner": room.winner_id,
                                "state": _room_state(room)})
