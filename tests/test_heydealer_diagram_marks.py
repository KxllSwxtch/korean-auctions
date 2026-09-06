"""Метки на схеме повреждений HeyDealer.

Регресс-тест на баг, о котором сообщил корейский покупатель: маркер 교환
рисовался буквой "E" (от английского "exchange"), тогда как в
성능·상태점검기록부 это X.

Источник меток переехал в mapper вместе с переходом на dbauto; сам тест остаётся
там, где на него смотрят по имени бага.
"""

from app.services.heydealer_dbauto_mapper import REPAIR_MARKS, repair_mark


def test_exchange_is_the_korean_mark_not_the_english_initial():
    assert repair_mark("exchange") == "X"
    assert "E" not in REPAIR_MARKS.values()


def test_weld_and_painted():
    assert repair_mark("weld") == "W"
    assert repair_mark("painted") == "P"


def test_unknown_and_none_get_no_glyph():
    # Безымянный маркер честнее выдуманной буквы.
    assert repair_mark("none") == ""
    assert repair_mark(None) == ""
    assert repair_mark("") == ""
    assert repair_mark("something_new") == ""


def test_marks_do_not_collide():
    assert len(set(REPAIR_MARKS.values())) == len(REPAIR_MARKS)
