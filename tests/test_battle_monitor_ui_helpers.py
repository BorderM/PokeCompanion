from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BATTLE_MONITOR_DIR = PROJECT_ROOT / "battle_monitor"
for path in (PROJECT_ROOT, BATTLE_MONITOR_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from battle_monitor_app import BattleMonitorApp, CONTROL_PANEL_WIDTH, LOW_CONFIDENCE_CLEAR_SCANS, sorted_name_regions
from ocr_quality import TemporalMatchStabilizer
from region_selector import Rect


def test_sorted_name_regions_orders_double_battle_slots_top_to_bottom():
    lower = Rect(20, 180, 120, 24)
    upper = Rect(22, 80, 120, 24)
    same_row_left = Rect(10, 80, 120, 24)

    assert sorted_name_regions([lower, upper, same_row_left]) == [same_row_left, upper, lower]


def test_control_panel_width_fits_two_column_setup_button_labels():
    # At the current ttk padding/panel gutters, 320 px gives the half-width
    # buttons enough room for labels such as "Window Region" and "Guided Setup".
    assert CONTROL_PANEL_WIDTH >= 320


def test_topbar_has_compact_toggle_and_expanded_setup_may_overlap_game():
    source = (BATTLE_MONITOR_DIR / "battle_monitor_app.py").read_text(encoding="utf-8")
    assert "self.topbar_compact_check" in source
    assert "text=\"Compact\"" in source
    assert "setup view may overlap the game" in source
    assert "self.dock_to_game_region(self.last_docked_position or self.dock_position.get())" in source
    assert "instead of resizing in place and overlapping the emulator" in source


def test_battle_slot_mode_source_has_double_slots_and_slot_ocr_fix():
    source = (BATTLE_MONITOR_DIR / "battle_monitor_app.py").read_text(encoding="utf-8")
    assert "self.battle_slot_mode" in source
    assert "values=(\"single\", \"double\")" in source
    assert "Slot {slot_idx + 1}: {status}" in source
    assert "self.add_ocr_fix_dialog(s)" in source
    assert "battle_slot_mode" in source


def test_expected_battle_slots_uses_single_or_double_mode():
    app = BattleMonitorApp.__new__(BattleMonitorApp)
    app.current_keys = {}
    app.last_slot_attempt_texts = {}
    app.battle_slot_mode = SimpleNamespace(get=lambda: "single")
    assert app.expected_battle_slots() == [0]

    app.battle_slot_mode = SimpleNamespace(get=lambda: "double")
    assert app.expected_battle_slots() == [0, 1]

    app.current_keys = {2: "pikachu"}
    assert app.expected_battle_slots() == [0, 1, 2]


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
    assert app.last_slot_attempt_texts == {0: ["Pikachu"]}
    assert app.last_slot_raw_texts == {0: "Pikachu"}
