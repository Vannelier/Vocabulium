import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import ws


@pytest.fixture(autouse=True)
def _reset_ws_state():
    ws.manager.rooms.clear()
    ws._conns.clear()
    ws._who.clear()
    yield


def _app(monkeypatch):
    # validate_hop stub : "foudre"/"pluie"/"vent" acceptés, le reste rejeté. Pas de modèle.
    def fake_validate(current, word):
        canon = word.lower()
        if canon in {"foudre", "pluie", "vent"}:
            return {"ok": True, "accepted": True, "canonical": canon}
        return {"ok": False, "reason": "unknown_word"}
    monkeypatch.setattr(ws, "validate_hop", fake_validate)
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
            state = host.receive_json()          # broadcast d'état après le join
            names = [p["name"] for p in state["state"]["players"]]
            assert names == ["toi", "Léa"]


def test_full_turn_flow(monkeypatch):
    client = TestClient(_app(monkeypatch))
    with client.websocket_connect("/ws") as host, \
         client.websocket_connect("/ws") as guest:
        host.send_json({"action": "create", "name": "toi"})
        code = host.receive_json()["code"]
        guest.send_json({"action": "join", "code": code, "name": "Léa"})
        guest.receive_json(); host.receive_json()          # joined + state
        host.send_json({"action": "start"})
        t = host.receive_json()
        while t["type"] != "turn":
            t = host.receive_json()
        assert t["current"] == "orage"
        host.send_json({"action": "hop", "word": "foudre"})
        acc = host.receive_json()
        while acc["type"] != "hop_accepted":
            acc = host.receive_json()
        assert acc["current"] == "foudre"


def test_malformed_frame_replies_error_and_survives(monkeypatch):
    client = TestClient(_app(monkeypatch))
    with client.websocket_connect("/ws") as sock:
        sock.send_text("not json {{{")
        r = sock.receive_json()
        assert r["type"] == "error" and r["reason"] == "bad_message"
        sock.send_json({"action": "create", "name": "toi"})   # la connexion survit
        assert sock.receive_json()["type"] == "joined"


def test_second_create_on_same_socket_rejected(monkeypatch):
    client = TestClient(_app(monkeypatch))
    with client.websocket_connect("/ws") as sock:
        sock.send_json({"action": "create", "name": "toi"})
        assert sock.receive_json()["type"] == "joined"
        sock.send_json({"action": "create", "name": "again"})
        r = sock.receive_json()
        assert r["type"] == "error" and r["reason"] == "already_in_room"


def test_join_nonexistent_room(monkeypatch):
    client = TestClient(_app(monkeypatch))
    with client.websocket_connect("/ws") as sock:
        sock.send_json({"action": "join", "code": "ZZZZ", "name": "x"})
        r = sock.receive_json()
        assert r["type"] == "error" and r["reason"] == "no_room"


def test_start_with_one_player_needs_players(monkeypatch):
    client = TestClient(_app(monkeypatch))
    with client.websocket_connect("/ws") as sock:
        sock.send_json({"action": "create", "name": "solo"})
        sock.receive_json()
        sock.send_json({"action": "start"})
        r = sock.receive_json()
        assert r["type"] == "error" and r["reason"] == "need_players"


def test_hop_rejected_not_your_turn(monkeypatch):
    client = TestClient(_app(monkeypatch))
    with client.websocket_connect("/ws") as host, \
         client.websocket_connect("/ws") as guest:
        host.send_json({"action": "create", "name": "toi"})
        code = host.receive_json()["code"]
        guest.send_json({"action": "join", "code": code, "name": "Léa"})
        guest.receive_json(); host.receive_json()
        host.send_json({"action": "start"})
        m = guest.receive_json()
        while m["type"] != "turn":
            m = guest.receive_json()
        guest.send_json({"action": "hop", "word": "foudre"})   # guest n'est pas actif
        r = guest.receive_json()
        assert r["type"] == "hop_rejected" and r["reason"] == "not_your_turn"


def test_disconnect_midgame_broadcasts_game_over(monkeypatch):
    client = TestClient(_app(monkeypatch))
    with client.websocket_connect("/ws") as host:
        host.send_json({"action": "create", "name": "toi"})
        jm = host.receive_json(); code = jm["code"]; you = jm["you"]
        with client.websocket_connect("/ws") as guest:
            guest.send_json({"action": "join", "code": code, "name": "Léa"})
            guest.receive_json(); host.receive_json()
            host.send_json({"action": "start"})
            m = host.receive_json()
            while m["type"] != "turn":
                m = host.receive_json()
        # guest s'est déconnecté (fin du with) -> host seul -> partie terminée
        go = None
        for _ in range(6):
            msg = host.receive_json()
            if msg["type"] == "game_over":
                go = msg; break
        assert go is not None and go["winner"] == you
