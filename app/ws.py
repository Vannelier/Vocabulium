"""Couche WebSocket du mode multijoueur. Valide les mots via le scoring existant
(isolé dans validate_hop pour les tests) puis applique à la Room, et broadcast."""
from __future__ import annotations

import asyncio
import logging
import random
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app import letters
from app.rooms import RoomManager

router = APIRouter()
manager = RoomManager()
log = logging.getLogger("vocabulium.ws")

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
    return {"ok": True, "accepted": res.zone != "reject", "canonical": canon,
            "score": {"zone": res.zone, "rarete": res.rarete, "speed": res.speed,
                      "hop_points": res.hop_points, "prox": res.prox,
                      "reason": res.reason}}


def pick_seed() -> str:
    from app.main import db
    from app.seed import random_seed
    return random_seed(db.seed_pool())


def make_forbidden_order() -> list[str]:
    return letters.draw_order(random.Random().random)


def _room_state(room) -> dict:
    return {
        "code": room.code, "state": room.state, "public": room.public,
        "current": room.current_word, "word_count": room.word_count,
        "active": room.active_player().id if (room.state == "playing" and room.active_player()) else None,
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
            try:
                data = await ws.receive_json()
            except WebSocketDisconnect:
                raise
            except Exception:
                # trame non-JSON / illisible : on signale sans tuer la connexion
                await ws.send_json({"type": "error", "reason": "bad_message"})
                continue
            if not isinstance(data, dict):
                await ws.send_json({"type": "error", "reason": "bad_message"})
                continue
            action = data.get("action")

            if action in ("create", "join", "quick_join") and ws in _who:
                await ws.send_json({"type": "error", "reason": "already_in_room"})
                continue

            if action == "quick_join":
                # matchmaking : rejoint un salon public en attente, sinon en crée un.
                room, p = manager.quick_join(data.get("name", "?"))
                _conns.setdefault(room.code, {})[p.id] = ws
                _who[ws] = (room.code, p.id)
                await ws.send_json({"type": "joined", "code": room.code,
                                    "you": p.id, "state": _room_state(room)})
                # ne prévenir les autres que si on a REJOINT un salon existant
                # (salon fraîchement créé = 1 joueur -> rien à diffuser, comme create).
                if len(room.players) > 1:
                    await _broadcast(room.code, {"type": "state", "state": _room_state(room)})

            elif action == "create":
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
                me = room.player(pid) if room else None
                if room is None or me is None or not me.is_host:
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
                    await ws.send_json({"type": "error", "reason": "no_room"}); continue
                if room.state != "playing":
                    await ws.send_json({"type": "hop_rejected", "reason": "not_playing"}); continue
                word = data.get("word")
                if not isinstance(word, str) or not word.strip():
                    await ws.send_json({"type": "error", "reason": "bad_message"}); continue
                v = validate_hop(room.current_word, word)
                if not v["ok"]:
                    await ws.send_json({"type": "hop_rejected", "reason": v["reason"]}); continue
                res = room.submit(pid, v["canonical"], v["accepted"])
                if not res["ok"]:
                    rej = {"type": "hop_rejected", "reason": res["reason"]}
                    # proximité connue (mot du dico) : on la renvoie pour que le client
                    # affiche la barre de proximité au refus, comme en solo.
                    if v.get("score"):
                        rej["score"] = v["score"]
                    await ws.send_json(rej); continue
                await _broadcast(room.code, {
                    "type": "hop_accepted", "current": res["current"],
                    "word_count": res["word_count"], "active": res["active"],
                    "scored_by": res["scored_by"], "new_forbidden": res["new_forbidden"],
                    "score": v["score"],
                    "state": _room_state(room)})
                await _broadcast(room.code, _start_turn(room))
    except WebSocketDisconnect:
        pass
    finally:
        await _cleanup(ws)


async def _cleanup(ws: WebSocket) -> None:
    code, pid = _who.pop(ws, (None, None))
    if code is None:
        return
    _conns.get(code, {}).pop(pid, None)
    room = manager.get(code)
    if room is None:
        return
    res = room.remove_player(pid)
    if not res.get("removed"):
        return
    if res.get("empty"):
        manager.drop(code)
        return
    await _broadcast(code, {"type": "state", "state": _room_state(room)})
    if res.get("over"):
        await _broadcast(code, {"type": "game_over", "winner": res["winner"],
                                "state": _room_state(room)})
    elif res.get("turn_handoff"):
        await _broadcast(code, _start_turn(room))


async def timeout_loop() -> None:
    """Balaie les salons en jeu ; à deadline dépassée, applique le timeout au
    joueur actif et broadcast (life_lost / game_over / turn suivant). Un salon en
    erreur ne doit jamais tuer la boucle globale."""
    while True:
        now = time.monotonic()
        for code, room in list(manager.rooms.items()):
            try:
                if room.state != "playing":
                    continue
                if not (room.turn_deadline and now >= room.turn_deadline):
                    continue
                active = room.active_player()
                if active is None:
                    continue
                res = room.timeout(active.id)
                if not res["ok"]:
                    continue
                await _broadcast(code, {"type": "life_lost", "pid": res["life_lost"],
                                        "lives": res["lives"],
                                        "eliminated": res["eliminated"],
                                        "state": _room_state(room)})
                if res["over"]:
                    await _broadcast(code, {"type": "game_over", "winner": res["winner"],
                                            "state": _room_state(room)})
                else:
                    await _broadcast(code, _start_turn(room))
            except Exception:
                log.exception("timeout_loop: erreur sur le salon %s", code)
        await asyncio.sleep(0.05)
