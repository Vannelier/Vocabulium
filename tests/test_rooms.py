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


def test_remove_host_promotes_new_host():
    room = Room(code="ROSE")
    a = room.add_player("a"); b = room.add_player("b")
    room.remove_player(a.id)
    assert room.player(b.id).is_host is True


def test_remove_player_before_active_keeps_same_active():
    room = Room(code="ROSE")
    a = room.add_player("a"); b = room.add_player("b"); c = room.add_player("c")
    room.active_index = 2                 # c est actif
    room.remove_player(a.id)              # on retire un joueur AVANT l'actif
    assert room.active_player().id == c.id


def test_remove_active_player_advances_to_next():
    room = Room(code="ROSE")
    a = room.add_player("a"); b = room.add_player("b"); c = room.add_player("c")
    room.active_index = 1                 # b actif
    room.remove_player(b.id)
    assert room.active_player().id == c.id   # passe au suivant


def test_remove_last_indexed_active_wraps_to_zero():
    room = Room(code="ROSE")
    a = room.add_player("a"); b = room.add_player("b"); c = room.add_player("c")
    room.active_index = 2                 # c actif (dernier)
    room.remove_player(c.id)
    assert room.active_player().id == a.id


def test_remove_unknown_player_is_noop():
    room = Room(code="ROSE")
    a = room.add_player("a")
    room.remove_player("nope")
    assert len(room.players) == 1


def test_player_lookup_and_manager_drop():
    from app.rooms import RoomManager
    room = Room(code="ROSE")
    a = room.add_player("a")
    assert room.player(a.id) is a
    assert room.player("nope") is None
    mgr = RoomManager()
    r = mgr.create()
    mgr.drop(r.code)
    assert mgr.get(r.code) is None
