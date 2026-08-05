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


def test_submit_no_crash_when_forbidden_pool_exhausted():
    room = Room(code="ROSE")
    room.add_player("a"); room.add_player("b")
    room.start(seed_word="orage", forbidden_order=["z", "q"])   # pool de 2 lettres
    room.word_count = 14          # forbidden_count=2 ; +1 -> 15 -> after=3 > pool(2)
    a = room.active_player()
    res = room.submit(a.id, "brume", accepted=True)   # sans z/q
    assert res["ok"] is True
    assert res["new_forbidden"] is None               # pool épuisé : aucune nouvelle lettre


def test_next_alive_skips_eliminated_player():
    room = Room(code="ROSE")
    room.add_player("a"); room.add_player("b"); room.add_player("c")
    room.start(seed_word="orage", forbidden_order=list("xyzjkq"))
    room.players[1].alive = False        # b éliminé
    a = room.players[0]
    res = room.submit(a.id, "foudre", accepted=True)
    assert res["active"] == room.players[2].id   # saute b (mort) -> c


def test_submit_in_lobby_is_not_your_turn():
    room = Room(code="ROSE")
    p = room.add_player("a")             # partie non lancée (état lobby)
    res = room.submit(p.id, "foudre", accepted=True)
    assert res["ok"] is False and res["reason"] == "not_your_turn"


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


def test_timeout_eliminates_without_ending_game_with_three_players():
    room = Room(code="ROSE")
    room.add_player("a"); room.add_player("b"); room.add_player("c")
    room.start(seed_word="orage", forbidden_order=list("xyzjkq"))
    a = room.players[0]
    room.timeout(a.id); room.active_index = 0     # on force a à rejouer/timeout
    room.timeout(a.id); room.active_index = 0
    res = room.timeout(a.id)                       # a éliminé, mais b et c restent
    assert res["eliminated"] is True
    assert res["over"] is False
    assert room.state == "playing"
    assert res["active"] in (room.players[1].id, room.players[2].id)


def test_remove_player_during_play_ends_game_on_last_survivor():
    room = _playing_room()                         # 2 joueurs, en jeu
    a, b = room.players
    room.remove_player(b.id)                       # b quitte -> a seul
    assert room.state == "over"
    assert room.winner_id == a.id


def test_timeout_after_attrition_is_ignored_no_contradiction():
    room = _playing_room()
    a, b = room.players
    room.remove_player(b.id)                        # partie déjà terminée (a gagne)
    res = room.timeout(a.id)                         # signal tardif -> ignoré
    assert res == {"ok": False}
    assert a.lives == LIVES                          # aucune vie perdue après la fin


def test_timeout_not_active_returns_bare_false():
    room = _playing_room()
    res = room.timeout(room.players[1].id)          # pas le joueur actif
    assert res == {"ok": False}


def test_submit_clears_turn_deadline_on_advance():
    room = _playing_room()
    room.turn_deadline = 999.0
    a = room.players[0]
    room.submit(a.id, "foudre", accepted=True)
    assert room.turn_deadline == 0.0


def test_timeout_clears_turn_deadline_on_advance():
    room = _playing_room()
    room.turn_deadline = 999.0
    a = room.players[0]
    room.timeout(a.id)                     # -1 vie, passe au suivant (jeu pas fini)
    assert room.turn_deadline == 0.0
