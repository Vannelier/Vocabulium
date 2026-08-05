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
