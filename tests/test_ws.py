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
