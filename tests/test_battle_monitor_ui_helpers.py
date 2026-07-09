from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BATTLE_MONITOR_DIR = PROJECT_ROOT / "battle_monitor"
for path in (PROJECT_ROOT, BATTLE_MONITOR_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from battle_monitor_app import BattleMonitorApp, LOW_CONFIDENCE_CLEAR_SCANS, sorted_name_regions
from ocr_quality import TemporalMatchStabilizer
from region_selector import Rect


def test_sorted_name_regions_orders_double_battle_slots_top_to_bottom():
    lower = Rect(20, 180, 120, 24)
    upper = Rect(22, 80, 120, 24)
    same_row_left = Rect(10, 80, 120, 24)

    assert sorted_name_regions([lower, upper, same_row_left]) == [same_row_left, upper, lower]


def test_mark_slot_miss_clears_stale_detected_card_after_threshold():
    app = BattleMonitorApp.__new__(BattleMonitorApp)
    app.slot_miss_counts = {}
    app.current_keys = {0: "pikachu"}
    app.slot_form_overrides = {0: "pikachu-cosplay"}
    app.last_slot_attempt_texts = {0: ["Pikachu"]}
    app.last_slot_raw_texts = {0: "Pikachu"}
    app.ocr_stabilizer = TemporalMatchStabilizer()

    for _ in range(LOW_CONFIDENCE_CLEAR_SCANS - 1):
        assert app.mark_slot_miss(0) is False
        assert app.current_keys == {0: "pikachu"}

    assert app.mark_slot_miss(0) is True
    assert app.current_keys == {}
    assert app.slot_form_overrides == {}
    assert app.last_slot_attempt_texts == {}
    assert app.last_slot_raw_texts == {}
