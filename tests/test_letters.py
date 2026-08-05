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
