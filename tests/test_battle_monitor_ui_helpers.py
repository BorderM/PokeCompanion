from __future__ import annotations

import queue
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
    assert "text=\"Singles\"" in source
    assert "text=\"Doubles\"" in source
    assert "single_name_region" in source
    assert "double_name_regions" in source
    assert "battle_slot_mode_dropdown" not in source
    assert "Slot {self.slot_display_number(slot_idx)}: {status}" in source
    assert "self.add_ocr_fix_dialog(s)" in source
    assert "program-wide and apply before fuzzy matching in every profile/game" in source
    assert "after_render_signature != self.last_rendered_keys" in source
    assert "if self.last_rendered_keys:" in source
    assert "title_text = f\"Slot {self.slot_display_number(slot_idx)}: Unclear\"" in source
    assert "LIVE_OCR_ATTEMPT_LIMIT_PER_SLOT" in source
    assert "self.slot_layout(idx) != active_layout" in source
    assert "ocr_fix_row = tk.Frame(header, bg=CARD_BG)" in source
    assert "title_row.pack(anchor=\"w\", fill=\"x\", pady=(0, 2))" in source
    assert "battle_slot_mode" in source


def test_live_scan_orders_current_layout_slots_first():
    app = BattleMonitorApp.__new__(BattleMonitorApp)
    app.name_region_slots = [0, 1, 2]
    regions = [Rect(0, 0, 10, 10), Rect(1, 0, 10, 10), Rect(2, 0, 10, 10)]
    app.name_regions = regions
    mode = {"value": "double"}
    app.battle_slot_mode = SimpleNamespace(get=lambda: mode["value"])

    assert [slot for slot, _region in app.ordered_name_regions_for_scan(regions)] == [1, 2, 0]

    mode["value"] = "single"
    assert [slot for slot, _region in app.ordered_name_regions_for_scan(regions)] == [0, 1, 2]

def test_all_saved_name_regions_stay_scan_active():
    app = BattleMonitorApp.__new__(BattleMonitorApp)
    single = Rect(10, 20, 120, 24)
    double_1 = Rect(15, 30, 120, 24)
    double_2 = Rect(15, 180, 120, 24)
    app.single_name_region = single
    app.double_name_regions = [double_1, double_2]
    app.name_regions = []
    app.name_region_slots = []
    app.sync_active_name_regions()
    assert app.name_regions == [single, double_1, double_2]
    assert app.name_region_slots == [0, 1, 2]


def test_auto_battle_layout_prefers_detected_double_slots():
    app = BattleMonitorApp.__new__(BattleMonitorApp)
    app.single_name_region = Rect(10, 20, 120, 24)
    app.double_name_regions = [Rect(15, 30, 120, 24), Rect(15, 180, 120, 24)]
    mode = {"value": "single"}
    app.battle_slot_mode = SimpleNamespace(get=lambda: mode["value"], set=lambda value: mode.__setitem__("value", value))
    app.slot_form_overrides = {}
    app.current_keys = {1: "pikachu"}
    app.update_auto_battle_layout({1: ["Pikachu"]})
    assert mode["value"] == "single"
    app.update_auto_battle_layout({1: ["Pikachu"]}, scan_detected_slots={1})
    assert mode["value"] == "double"

    app.current_keys = {1: "arcanine", 2: "volbeat"}
    app.slot_form_overrides = {1: "arcanine-form", 2: "volbeat-form"}
    app.update_auto_battle_layout({0: ["Geodude"], 1: ["old double noise"]}, scan_detected_slots={0})
    assert mode["value"] == "single"
    assert app.current_keys == {}
    assert app.slot_form_overrides == {}

    app.current_keys = {0: "roselia"}
    app.slot_form_overrides = {0: "roselia-form"}
    app.update_auto_battle_layout({0: ["Roselia"], 1: ["Volbeat"]}, scan_detected_slots={1})
    assert mode["value"] == "double"
    assert app.current_keys == {}
    assert app.slot_form_overrides == {}

    app.current_keys = {0: "roselia"}
    app.slot_form_overrides = {0: "roselia-form"}
    app.update_auto_battle_layout({0: ["Roselia"], 1: ["Volbeat"]})
    assert mode["value"] == "double"
    assert app.current_keys == {0: "roselia"}
    assert app.slot_form_overrides == {0: "roselia-form"}

    app.current_keys = {}
    mode["value"] = "single"
    app.update_auto_battle_layout({})
    assert mode["value"] == "single"

    mode["value"] = "double"
    app.current_keys = {}
    app.update_auto_battle_layout({0: ["Heatnor-"]})
    assert mode["value"] == "double"


def test_double_slot_selection_shows_provisional_double_placeholders_while_ocr_runs():
    app = BattleMonitorApp.__new__(BattleMonitorApp)
    first = Rect(40, 90, 100, 20)
    second = Rect(40, 180, 100, 20)
    selections = iter([first, second])
    mode = {"value": "single"}
    app.select_relative_name_region = lambda _title: next(selections)
    app.battle_slot_mode = SimpleNamespace(get=lambda: mode["value"], set=lambda value: mode.__setitem__("value", value))
    app.single_name_region = Rect(10, 20, 120, 24)
    app.double_name_regions = []
    app.name_regions = []
    app.name_region_slots = []
    app.current_keys = {0: "roselia"}
    app.slot_form_overrides = {}
    app.scan_histories = {}
    app.ocr_stabilizer = TemporalMatchStabilizer()
    app.slot_miss_counts = {}
    app.auto_slot_pending = {}
    app.last_rendered_keys = ("stale",)
    app.status_var = SimpleNamespace(set=lambda _value: None)
    app.update_preview = lambda: None
    app.render_detected = lambda *_args, **_kwargs: None
    app.last_debug_lines = []
    app.last_slot_attempt_texts = {1: ["Druddigon"], 2: ["Hreanine"]}
    app.last_slot_raw_texts = {1: "Druddigon", 2: "Hreanine"}

    app.select_double_name_slots()

    assert mode["value"] == "double"
    assert app.double_name_regions == [first, second]
    assert app.name_region_slots == [0, 1, 2]
    assert app.current_keys == {}
    assert app.expected_battle_slots() == [1, 2]
    assert app.last_slot_attempt_texts == {}
    assert app.last_slot_raw_texts == {}

    app.current_keys = {}
    app.update_auto_battle_layout({1: ["Volbeat"], 2: ["Illumise"]})
    assert mode["value"] == "double"
    assert app.expected_battle_slots() == [1, 2]


def test_slot_setup_invalidates_in_flight_scan_and_renders_actual_new_state():
    app = BattleMonitorApp.__new__(BattleMonitorApp)
    first = Rect(40, 90, 100, 20)
    second = Rect(40, 180, 100, 20)
    selections = iter([first, second])
    mode = {"value": "single"}
    rendered_slots = []
    scheduled_delays = []

    app.select_relative_name_region = lambda _title: next(selections)
    app.battle_slot_mode = SimpleNamespace(get=lambda: mode["value"], set=lambda value: mode.__setitem__("value", value))
    app.single_name_region = Rect(10, 20, 120, 24)
    app.double_name_regions = []
    app.name_regions = []
    app.name_region_slots = []
    app.current_keys = {0: "heatmor"}
    app.slot_form_overrides = {0: "heatmor"}
    app.scan_histories = {}
    app.ocr_stabilizer = TemporalMatchStabilizer()
    app.slot_miss_counts = {}
    app.auto_slot_pending = {}
    app.last_rendered_keys = ((0, "heatmor"), (0,), "single")
    app.last_debug_lines = []
    app.last_slot_attempt_texts = {0: ["Heatnor-"]}
    app.last_slot_raw_texts = {0: "Heatnor-"}
    app.scan_worker_active = True
    app.active_scan_tick = 42
    app.scan_result_queue = queue.Queue()
    app.scan_result_queue.put((42, [], None))
    app.running = True
    app.root = SimpleNamespace(after=lambda delay, callback: scheduled_delays.append(delay))
    app.status_var = SimpleNamespace(set=lambda _value: None)
    app.update_preview = lambda: None
    app.render_detected = lambda *_args, **_kwargs: rendered_slots.append(tuple(app.expected_battle_slots()))

    app.select_double_name_slots()

    assert mode["value"] == "double"
    assert app.expected_battle_slots() == [1, 2]
    assert rendered_slots[-1] == (1, 2)
    assert app.current_keys == {}
    assert app.last_slot_attempt_texts == {}
    assert app.scan_worker_active is False
    assert app.active_scan_tick == 0
    assert app.scan_result_queue.empty()
    assert scheduled_delays


def test_legacy_name_regions_migrate_to_per_game_slot_storage():
    app = BattleMonitorApp.__new__(BattleMonitorApp)
    app.threshold_var = SimpleNamespace(set=lambda _value: None)
    app.dock_on_start = SimpleNamespace(set=lambda _value: None)
    app.dock_position = SimpleNamespace(set=lambda _value: None)
    app.ultra_compact = SimpleNamespace(set=lambda _value: None)
    app.battle_slot_mode = SimpleNamespace(get=lambda: "double", set=lambda _value: None)
    app.auto_window_region = SimpleNamespace(set=lambda _value: None)
    app.section_collapsed = {}
    app.controls_visible = SimpleNamespace(get=lambda: True)
    app.current_keys = {}
    app.slot_form_overrides = {}
    app.scan_histories = {}
    app.ocr_stabilizer = TemporalMatchStabilizer()
    app.slot_miss_counts = {}
    app.auto_slot_pending = {}
    app.last_rendered_keys = tuple()
    app.preview_visible = SimpleNamespace(get=lambda: False)
    app.update_preview = lambda: None
    app.render_detected = lambda *_args, **_kwargs: None
    app.toggle_controls_panel = lambda: None
    app.toggle_preview = lambda: None
    app.last_debug_lines = []

    first = Rect(40, 90, 100, 20)
    second = Rect(40, 180, 100, 20)
    BattleMonitorApp.apply_profile_payload(app, {"name_regions": [second.to_dict(), first.to_dict()], "battle_slot_mode": "double"})

    assert app.single_name_region is None
    assert app.double_name_regions == [first, second]
    assert app.name_regions == [first, second]


def test_expected_battle_slots_uses_detected_single_or_double_layout():
    app = BattleMonitorApp.__new__(BattleMonitorApp)
    app.battle_slot_mode = SimpleNamespace(get=lambda: "single")
    assert app.expected_battle_slots() == [0]

    app.battle_slot_mode = SimpleNamespace(get=lambda: "double")
    assert app.expected_battle_slots() == [1, 2]


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
