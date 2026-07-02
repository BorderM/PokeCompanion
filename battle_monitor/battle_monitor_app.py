from __future__ import annotations

import ctypes
import ctypes.wintypes
import json
import queue
import re
import sys
import time
import threading
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional


def _enable_dpi_awareness() -> None:
    """Keep Tk geometry, pointer positions, and Win32 window rects aligned."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-monitor DPI aware.
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


_enable_dpi_awareness()

import mss
from PIL import Image, ImageDraw, ImageTk
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

# Allow running this file directly from the repository root, from battle_monitor/,
# from a PyInstaller one-folder build, and from a Nuitka standalone build.
#
# v14 note: packaged builds can place data beside the executable, inside
# PyInstaller's _internal/_MEIPASS folder, or beside the compiled module. Search
# those roots instead of assuming one exact layout; otherwise the GUI may fail
# before it appears and look like it did nothing.
def _is_packaged() -> bool:
    return bool(getattr(sys, "frozen", False) or globals().get("__compiled__"))


def _dedupe_paths(paths):
    seen = set()
    result = []
    for path in paths:
        try:
            resolved = Path(path).resolve()
        except Exception:
            continue
        key = str(resolved).lower()
        if key not in seen:
            seen.add(key)
            result.append(resolved)
    return result


def _candidate_roots():
    module_dir = Path(__file__).resolve().parent
    app_root = Path(sys.executable).resolve().parent if _is_packaged() else module_dir
    bundle_root = Path(getattr(sys, "_MEIPASS", app_root))
    return _dedupe_paths([
        app_root,
        bundle_root,
        bundle_root.parent,
        module_dir,
        module_dir.parent,
        Path.cwd(),
        Path.cwd().parent,
    ])


def _find_project_root() -> Path:
    for root in _candidate_roots():
        if (root / "processed_pokemon_cache.json").exists() and (root / "data").exists():
            return root
    # Last-resort fallback for source runs. The launcher will log the real error
    # if the cache is missing.
    return Path(__file__).resolve().parent.parent


def _find_this_dir(project_root: Path) -> Path:
    for candidate in _dedupe_paths([
        Path(__file__).resolve().parent,
        project_root / "battle_monitor",
        Path(sys.executable).resolve().parent / "battle_monitor" if _is_packaged() else Path(__file__).resolve().parent,
    ]):
        if candidate.exists():
            return candidate
    return project_root / "battle_monitor"


APP_ROOT = Path(sys.executable).resolve().parent if _is_packaged() else Path(__file__).resolve().parent
PROJECT_ROOT = _find_project_root()
THIS_DIR = _find_this_dir(PROJECT_ROOT)
USER_DATA_DIR = (APP_ROOT / "battle_monitor") if _is_packaged() else THIS_DIR

for import_path in (THIS_DIR, Path(__file__).resolve().parent):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from ocr_engine import OcrEngine
from pokemon_repository import PokemonRepository, MatchResult, normalize_name
from region_selector import Rect, select_screen_region

CONFIG_PATH = USER_DATA_DIR / "battle_monitor_config.json"
OCR_CORRECTIONS_PATH = USER_DATA_DIR / "ocr_corrections.json"
PROFILE_DIR = USER_DATA_DIR / "profiles"
DEFAULT_PROFILE_PATH = PROFILE_DIR / "default.json"
SCAN_INTERVAL_MS = 450
WAITING_SCAN_INTERVAL_MS = 250
FOLLOW_WINDOW_INTERVAL_MS = 300
DEBUG_RENDER_INTERVAL_SEC = 2.5
PREVIEW_REFRESH_EVERY_SCANS = 4
MIN_MATCH_SCORE = 84
# Name Area scans are intentionally stricter than precise Add Name crops.
# A broad Name Area can include route text, menu text, trees, HP bars, or an
# empty second slot. Requiring either a level/nameplate cue or a stronger fuzzy
# score prevents the monitor from inventing Pokémon when no battle nameplate is
# present.
AUTO_AREA_MATCH_SCORE = 95
AUTO_AREA_STRONG_MATCH_SCORE = 98
AUTO_AREA_TEXT_PANEL_SCORE = 90
# Name Area panel crops are strong visual evidence, so allow a lower OCR score
# only after the crop has passed the nameplate detector. This rescues common
# pixel-font reads like Heatmor -> Heatnors or Chansey -> Chanseus without
# lowering the general/no-panel threshold used outside battles.
AUTO_AREA_PANEL_RELAXED_SCORE = 78
AUTO_AREA_SECOND_SLOT_CONFIRM_SCANS = 2
LOW_CONFIDENCE_CLEAR_SCANS = 2
CONTROL_PANEL_WIDTH = 260
CONTROL_STATUS_WRAP = CONTROL_PANEL_WIDTH - 34
DOCK_WIDTH = 500
ULTRA_DOCK_WIDTH = 460
DOCK_MIN_WIDTH = 360
DOCK_MIN_HEIGHT = 320
EXPANDED_CONTROLS_MIN_WIDTH = CONTROL_PANEL_WIDTH + 260
EXPANDED_CONTROLS_TARGET_WIDTH = 820
DOCK_HORIZONTAL_HEIGHT = 240
# Tk window geometry describes the content area on Windows. The native
# title bar/borders are added around that area, so subtract these estimates
# when trying to match the selected emulator window exactly.
WINDOW_DECORATION_WIDTH_ESTIMATE = 0
WINDOW_DECORATION_HEIGHT_ESTIMATE = 36
DOCK_GAP = 0

PAGE_BG = "#111827"
CARD_BG = "#1f2937"
CARD_BG_ALT = "#243244"
BORDER = "#374151"
TEXT = "#e5e7eb"
MUTED = "#9ca3af"
WHITE = "#ffffff"
BLUE = "#3b82f6"
GREEN = "#22c55e"
RED = "#ef4444"
YELLOW = "#f59e0b"
PURPLE = "#8b5cf6"

TYPE_COLORS = {
    "normal": "#A8A77A",
    "fire": "#EE8130",
    "water": "#6390F0",
    "electric": "#F7D02C",
    "grass": "#7AC74C",
    "ice": "#96D9D6",
    "fighting": "#C22E28",
    "poison": "#A33EA1",
    "ground": "#E2BF65",
    "flying": "#A98FF3",
    "psychic": "#F95587",
    "bug": "#A6B91A",
    "rock": "#B6A136",
    "ghost": "#735797",
    "dragon": "#6F35FC",
    "dark": "#705746",
    "steel": "#C0C0C0",
    "fairy": "#D685AD",
    "none": "#4B5563",
}

EFFECTIVENESS_ROWS = [
    ("four_times_effective", "4× Weak"),
    ("super_effective", "2× Weak"),
    ("two_times_resistant", "½ Resist"),
    ("four_times_resistant", "¼ Resist"),
    ("immune", "Immune"),
]

STAT_ROWS = [
    ("hp", "HP"),
    ("attack", "Attack"),
    ("defense", "Defense"),
    ("special_attack", "Sp. Atk"),
    ("special_defense", "Sp. Def"),
    ("speed", "Speed"),
    ("total", "Total"),
]


def profile_filename(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9 _.-]", "", name or "").strip()
    safe = re.sub(r"\s+", "_", safe)
    if not safe:
        safe = "profile"
    if not safe.lower().endswith(".json"):
        safe += ".json"
    return safe


class ToolTip:
    def __init__(self, widget: tk.Widget, text: str, delay_ms: int = 500, wraplength: int = 280):
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self.wraplength = wraplength
        self.after_id = None
        self.tipwindow = None
        widget.bind("<Enter>", self.schedule, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")

    def schedule(self, _event=None) -> None:
        self.cancel()
        self.after_id = self.widget.after(self.delay_ms, self.show)

    def cancel(self) -> None:
        if self.after_id:
            try:
                self.widget.after_cancel(self.after_id)
            except Exception:
                pass
            self.after_id = None

    def show(self) -> None:
        self.after_id = None
        if self.tipwindow or not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + 12
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        except Exception:
            return
        self.tipwindow = tk.Toplevel(self.widget)
        self.tipwindow.wm_overrideredirect(True)
        self.tipwindow.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            self.tipwindow,
            text=self.text,
            bg="#0f172a",
            fg=TEXT,
            relief="solid",
            borderwidth=1,
            padx=8,
            pady=5,
            justify="left",
            wraplength=self.wraplength,
            font=("Segoe UI", 8),
        )
        label.pack()

    def hide(self, _event=None) -> None:
        self.cancel()
        if self.tipwindow:
            try:
                self.tipwindow.destroy()
            except Exception:
                pass
            self.tipwindow = None


class BattleMonitorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Pokémon Battle Monitor")
        self.root.geometry("960x580")
        self.root.minsize(380, 400)
        self.root.configure(bg=PAGE_BG)

        self.config = self.load_config()
        self.repo = PokemonRepository(PROJECT_ROOT)
        self.ocr = OcrEngine(self.config.get("tesseract_cmd"))
        self.ocr_corrections = self.load_ocr_corrections()
        self.sct = mss.mss()

        self.game_region: Optional[Rect] = None
        self.name_regions: List[Rect] = []  # relative to game region
        self.running = False
        self.scan_histories: Dict[int, deque] = {}
        self.slot_miss_counts: Dict[int, int] = {}
        self.auto_slot_pending: Dict[int, tuple[str, int]] = {}
        self.current_keys: Dict[int, str] = {}
        self.slot_form_overrides: Dict[int, str] = {}
        self.name_scan_area: Optional[Rect] = None  # optional broad area for future auto name-panel detection
        self.last_debug_lines: List[str] = []
        self.last_slot_raw_texts: Dict[int, str] = {}
        self.last_slot_attempt_texts: Dict[int, List[str]] = {}
        self.setup_tour_window = None
        self.setup_tour_index = 0
        self.setup_tour_fixed_geometry = None
        self.setup_auto_advance_job = None
        self.last_profile_save_time = 0.0
        self.last_docked_time = 0.0
        self.scan_worker_active = False
        self.active_scan_tick = 0
        self.active_scan_started_at = 0.0
        self.last_scan_completed_at = 0.0
        self.scan_watchdog_job = None
        self.follow_window_job = None
        self.last_follow_window_tick = 0.0
        self.active_scan_auto_area = False
        self.active_scan_threshold = MIN_MATCH_SCORE
        self.last_docked_position = None
        self.docking_in_progress = False
        self.scan_result_queue = queue.Queue()
        self.setup_steps = []
        self.tooltips: List[ToolTip] = []
        self.last_rendered_keys: tuple = tuple()
        self.last_debug_signature: tuple = tuple()
        self.last_debug_render_time = 0.0
        self.last_card_width_bucket = None
        self.resize_render_job = None
        self.scan_tick = 0
        self.preview_photo = None
        self.preview_visible = tk.BooleanVar(value=False)
        self.preview_button_text = tk.StringVar(value="Show Preview")
        self.controls_visible = tk.BooleanVar(value=True)
        self.controls_button_text = tk.StringVar(value="Hide Controls")
        self.dock_on_start = tk.BooleanVar(value=True)
        self.dock_position = tk.StringVar(value="left")
        self.ultra_compact = tk.BooleanVar(value=False)
        self.auto_window_region = tk.BooleanVar(value=False)
        self.attached_window_title = ""
        self.window_match_text = ""
        self.section_collapsed = {
            "stats": tk.BooleanVar(value=True),
            "effectiveness": tk.BooleanVar(value=False),
            "abilities": tk.BooleanVar(value=True),
        }
        self.show_debug = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Select a game region to begin.")
        self.scan_status_var = tk.StringVar(value="Idle")
        self.threshold_var = tk.IntVar(value=MIN_MATCH_SCORE)

        self.setup_styles()
        self.build_ui()
        self.status_var.set(self.ocr.diagnostic_message())
        if DEFAULT_PROFILE_PATH.exists():
            try:
                self.load_profile(DEFAULT_PROFILE_PATH, silent=True)
            except Exception:
                pass
        # Guided Setup is available from the Setup panel, but it no longer
        # opens automatically on launch. The monitor should start quietly for
        # users who already have a saved profile or who are testing OCR/docking.

    def setup_styles(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("App.TFrame", background=PAGE_BG)
        style.configure("Panel.TFrame", background=CARD_BG)
        style.configure("App.TLabel", background=PAGE_BG, foreground=TEXT, font=("Segoe UI", 9))
        style.configure("Title.TLabel", background=PAGE_BG, foreground=WHITE, font=("Segoe UI", 15, "bold"))
        style.configure("Section.TLabelframe", background=PAGE_BG, foreground=TEXT, bordercolor=BORDER)
        style.configure("Section.TLabelframe.Label", background=PAGE_BG, foreground=TEXT, font=("Segoe UI", 9, "bold"))
        style.configure("TButton", font=("Segoe UI", 9), padding=(7, 4))
        style.configure("TCheckbutton", background=PAGE_BG, foreground=TEXT, font=("Segoe UI", 9))
        style.map("TCheckbutton", background=[("active", PAGE_BG)], foreground=[("active", WHITE)])
        style.configure("TRadiobutton", background=PAGE_BG, foreground=TEXT, font=("Segoe UI", 9))
        style.map("TRadiobutton", background=[("active", PAGE_BG)], foreground=[("active", WHITE)])
        style.configure("TScale", background=PAGE_BG)

    def add_tooltip(self, widget: tk.Widget, text: str) -> None:
        self.tooltips.append(ToolTip(widget, text))

    def load_config(self) -> dict:
        if CONFIG_PATH.exists():
            try:
                return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            except Exception:
                return {}
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps({"tesseract_cmd": ""}, indent=2), encoding="utf-8")
        return {"tesseract_cmd": ""}


    def load_ocr_corrections(self) -> Dict[str, str]:
        """Load normalized OCR-text -> Pokémon key overrides."""
        if OCR_CORRECTIONS_PATH.exists():
            try:
                data = json.loads(OCR_CORRECTIONS_PATH.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    # Keep only mappings to known local Pokémon keys.
                    return {str(k): str(v) for k, v in data.items() if str(v) in getattr(self, "repo", {}).pokemon}
            except Exception:
                return {}
        OCR_CORRECTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
        return {}

    def save_ocr_corrections(self) -> None:
        OCR_CORRECTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
        OCR_CORRECTIONS_PATH.write_text(json.dumps(self.ocr_corrections, indent=2, sort_keys=True), encoding="utf-8")

    def corrected_match(self, raw_text: str) -> Optional[MatchResult]:
        normalized = normalize_name(raw_text)
        key = self.ocr_corrections.get(normalized)
        if not key or key not in self.repo.pokemon:
            return None
        record = self.repo.pokemon.get(key, {})
        return MatchResult(
            key=key,
            display_name=record.get("display_name") or key.replace("-", " ").title(),
            score=100.0,
            raw_text=raw_text,
            normalized_text=normalized,
        )

    def build_ui(self) -> None:
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)

        controls = ttk.Frame(self.root, padding=(8, 8, 8, 8), style="App.TFrame", width=CONTROL_PANEL_WIDTH)
        self.controls_frame = controls
        controls.grid(row=0, column=0, sticky="nsw")
        controls.grid_propagate(False)
        controls.columnconfigure(0, weight=1)
        controls.columnconfigure(1, weight=1)

        header = ttk.Frame(controls, style="App.TFrame")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Battle Monitor", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        self.hide_controls_button = ttk.Button(header, text="Hide", width=8, command=self.toggle_controls_panel)
        self.hide_controls_button.grid(row=0, column=1, sticky="e", padx=(8, 0))
        self.add_tooltip(self.hide_controls_button, "Hide the setup controls and return to the docked companion view.")

        row = 1
        capture = ttk.LabelFrame(controls, text="Setup", style="Section.TLabelframe", padding=6)
        capture.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        capture.columnconfigure(0, weight=1)
        capture.columnconfigure(1, weight=1)
        self.game_region_button = ttk.Button(capture, text="Game Region", command=self.select_game_region)
        self.game_region_button.grid(row=0, column=0, sticky="ew", padx=(0, 2), pady=2)
        self.add_tooltip(self.game_region_button, "Manually drag around the full emulator or game window.")
        self.window_region_button = ttk.Button(capture, text="Window Region", command=self.select_game_window_region)
        self.window_region_button.grid(row=0, column=1, sticky="ew", padx=(2, 0), pady=2)
        self.add_tooltip(self.window_region_button, "Choose a running emulator/game window and use its current bounds.")
        self.add_name_button = ttk.Button(capture, text="Add Name", command=self.add_name_region)
        self.add_name_button.grid(row=1, column=0, sticky="ew", padx=(0, 2), pady=2)
        self.add_tooltip(self.add_name_button, "Add a precise OCR crop around one enemy Pokemon name box.")
        self.clear_names_button = ttk.Button(capture, text="Clear Names", command=self.clear_name_regions)
        self.clear_names_button.grid(row=1, column=1, sticky="ew", padx=(2, 0), pady=2)
        self.add_tooltip(self.clear_names_button, "Remove all precise name crops and reset current detections.")
        self.name_area_button = ttk.Button(capture, text="Name Area", command=self.select_name_scan_area)
        self.name_area_button.grid(row=2, column=0, sticky="ew", padx=(0, 2), pady=2)
        self.add_tooltip(self.name_area_button, "Select one broad area containing possible enemy nameplates; the app detects panels inside it.")
        self.preview_toggle_button = ttk.Button(capture, textvariable=self.preview_button_text, command=self.toggle_preview)
        self.preview_toggle_button.grid(row=2, column=1, sticky="ew", padx=(2, 0), pady=2)
        self.add_tooltip(self.preview_toggle_button, "Show or hide a preview of the selected game region and OCR boxes.")
        self.guided_setup_button = ttk.Button(capture, text="Guided Setup", command=self.start_setup_tour)
        self.guided_setup_button.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(5, 2))
        self.add_tooltip(self.guided_setup_button, "Walk through window selection, name areas, docking, profiles, and tracking.")

        row += 1
        tracking = ttk.LabelFrame(controls, text="Live", style="Section.TLabelframe", padding=6)
        tracking.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        tracking.columnconfigure(0, weight=1)
        tracking.columnconfigure(1, weight=1)
        self.start_button = ttk.Button(tracking, text="Start", command=self.start_tracking)
        self.start_button.grid(row=0, column=0, sticky="ew", padx=(0, 2), pady=2)
        self.add_tooltip(self.start_button, "Begin OCR scanning using the selected name regions or Name Area.")
        self.stop_button = ttk.Button(tracking, text="Stop", command=self.stop_tracking)
        self.stop_button.grid(row=0, column=1, sticky="ew", padx=(2, 0), pady=2)
        self.add_tooltip(self.stop_button, "Stop scanning and ignore any late OCR results from in-flight scans.")
        self.dock_on_start_check = ttk.Checkbutton(tracking, text="Dock on Start", variable=self.dock_on_start)
        self.dock_on_start_check.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.add_tooltip(self.dock_on_start_check, "Automatically hide controls and dock beside the game when tracking starts.")
        self.ultra_compact_check = ttk.Checkbutton(tracking, text="Ultra compact", variable=self.ultra_compact, command=self.on_compact_option_changed)
        self.ultra_compact_check.grid(row=2, column=0, columnspan=2, sticky="w", pady=(2, 0))
        self.add_tooltip(self.ultra_compact_check, "Use a smaller battle-focused card with name, types, speed, and effectiveness.")
        self.auto_window_region_check = ttk.Checkbutton(tracking, text="Follow window", variable=self.auto_window_region)
        self.auto_window_region_check.grid(row=3, column=0, columnspan=2, sticky="w", pady=(2, 0))
        self.add_tooltip(self.auto_window_region_check, "Keep the captured game bounds and docked monitor attached to the selected window as it moves.")
        ttk.Label(tracking, text="Dock position", style="App.TLabel").grid(row=4, column=0, columnspan=2, sticky="w", pady=(7, 1))
        self.dock_select_frame = ttk.Frame(tracking, style="App.TFrame")
        dock_select = self.dock_select_frame
        dock_select.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(0, 2))
        for c in range(2):
            dock_select.columnconfigure(c, weight=1)
        self.dock_left_radio = ttk.Radiobutton(dock_select, text="Left", value="left", variable=self.dock_position)
        self.dock_left_radio.grid(row=0, column=0, sticky="w", padx=(0, 6), pady=1)
        self.dock_right_radio = ttk.Radiobutton(dock_select, text="Right", value="right", variable=self.dock_position)
        self.dock_right_radio.grid(row=0, column=1, sticky="w", pady=1)
        self.dock_above_radio = ttk.Radiobutton(dock_select, text="Above", value="above", variable=self.dock_position)
        self.dock_above_radio.grid(row=1, column=0, sticky="w", padx=(0, 6), pady=1)
        self.dock_below_radio = ttk.Radiobutton(dock_select, text="Below", value="below", variable=self.dock_position)
        self.dock_below_radio.grid(row=1, column=1, sticky="w", pady=1)
        self.add_tooltip(self.dock_left_radio, "Dock the companion on the left side of the selected game region.")
        self.add_tooltip(self.dock_right_radio, "Dock the companion on the right side of the selected game region.")
        self.add_tooltip(self.dock_above_radio, "Dock the companion above the selected game region.")
        self.add_tooltip(self.dock_below_radio, "Dock the companion below the selected game region.")
        self.dock_now_button = ttk.Button(tracking, text="Dock Now", command=lambda: self.dock_to_game_region(self.dock_position.get()))
        self.dock_now_button.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(5, 2))
        self.add_tooltip(self.dock_now_button, "Immediately move and resize the monitor to the selected dock position.")

        row += 1
        profiles = ttk.LabelFrame(controls, text="Profiles / OCR", style="Section.TLabelframe", padding=6)
        profiles.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        profiles.columnconfigure(0, weight=1)
        profiles.columnconfigure(1, weight=1)
        self.save_profile_button = ttk.Button(profiles, text="Save", command=self.save_profile_dialog)
        self.save_profile_button.grid(row=0, column=0, sticky="ew", padx=(0, 2), pady=2)
        self.add_tooltip(self.save_profile_button, "Save the current regions, dock settings, compact mode, and collapsed sections.")
        self.load_profile_button = ttk.Button(profiles, text="Load", command=self.load_profile_dialog)
        self.load_profile_button.grid(row=0, column=1, sticky="ew", padx=(2, 0), pady=2)
        self.add_tooltip(self.load_profile_button, "Load a saved monitor setup from the profiles folder.")
        self.add_ocr_fix_button = ttk.Button(profiles, text="Add OCR Fix", command=self.add_ocr_fix_dialog)
        self.add_ocr_fix_button.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(5, 2))
        self.add_tooltip(self.add_ocr_fix_button, "Teach the matcher that a recurring bad OCR read means a specific Pokemon.")

        row += 1
        status = ttk.LabelFrame(controls, text="Status", style="Section.TLabelframe", padding=6)
        status.grid(row=row, column=0, columnspan=2, sticky="nsew", pady=(0, 0))
        ttk.Label(status, textvariable=self.status_var, wraplength=CONTROL_STATUS_WRAP, style="App.TLabel").pack(anchor="w")
        controls.rowconfigure(row, weight=1)

        main = ttk.Frame(self.root, padding=(6, 8, 8, 8), style="App.TFrame")
        main.grid(row=0, column=1, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(0, weight=0)
        main.rowconfigure(1, weight=0)
        main.rowconfigure(2, weight=1)

        self.compact_topbar = ttk.Frame(main, style="App.TFrame")
        self.compact_topbar.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        self.show_controls_button = ttk.Button(self.compact_topbar, textvariable=self.controls_button_text, command=self.toggle_controls_panel)
        self.show_controls_button.pack(side="left")
        self.add_tooltip(self.show_controls_button, "Show the setup controls; hiding them again returns to the docked position.")
        tk.Label(
            self.compact_topbar,
            textvariable=self.scan_status_var,
            bg=PAGE_BG,
            fg=MUTED,
            font=("Segoe UI", 8),
            anchor="w",
        ).pack(side="left", padx=(8, 0), fill="x", expand=True)
        self.compact_topbar.grid_remove()

        self.preview_box = ttk.LabelFrame(main, text="Region preview", style="Section.TLabelframe", padding=6)
        self.preview_box.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        self.preview_label = tk.Label(self.preview_box, text="No preview yet", bg=CARD_BG, fg=MUTED, anchor="center")
        self.preview_label.pack(fill="both", expand=True, padx=2, pady=2)
        self.preview_box.grid_remove()

        info_box = ttk.LabelFrame(main, text="Live battle information", style="Section.TLabelframe", padding=4)
        info_box.grid(row=2, column=0, sticky="nsew")
        info_box.rowconfigure(0, weight=1)
        info_box.columnconfigure(0, weight=1)

        self.info_canvas = tk.Canvas(info_box, bg=PAGE_BG, highlightthickness=0, borderwidth=0)
        self.info_canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(info_box, orient="vertical", command=self.info_canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.info_canvas.configure(yscrollcommand=scrollbar.set)

        self.card_container = tk.Frame(self.info_canvas, bg=PAGE_BG)
        self.card_window = self.info_canvas.create_window((0, 0), window=self.card_container, anchor="nw")
        self.card_container.bind("<Configure>", self._on_card_container_configure)
        self.info_canvas.bind("<Configure>", self._on_info_canvas_configure)
        self.info_canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.render_idle_message()

    def _on_card_container_configure(self, _event=None) -> None:
        self.info_canvas.configure(scrollregion=self.info_canvas.bbox("all"))

    def info_layout_bucket(self, width: int) -> tuple:
        width = max(1, int(width))
        two_column_min = 640 if self.ultra_compact.get() else 760
        columns = 2 if len(self.current_keys) >= 2 and width >= two_column_min else 1
        card_width = max(220, width // columns)
        if self.ultra_compact.get():
            tier = 3 if card_width >= 700 else (2 if card_width >= 560 else (1 if card_width >= 430 else 0))
        else:
            tier = 3 if card_width >= 760 else (2 if card_width >= 620 else (1 if card_width >= 460 else 0))
        return (columns, tier, card_width // 80)

    def _on_info_canvas_configure(self, event) -> None:
        self.info_canvas.itemconfigure(self.card_window, width=event.width)
        bucket = self.info_layout_bucket(event.width)
        if bucket != self.last_card_width_bucket:
            self.last_card_width_bucket = bucket
            if self.current_keys:
                if self.resize_render_job:
                    try:
                        self.root.after_cancel(self.resize_render_job)
                    except Exception:
                        pass
                self.resize_render_job = self.root.after_idle(self.rerender_cards_for_resize)

    def rerender_cards_for_resize(self) -> None:
        self.resize_render_job = None
        if not self.current_keys:
            return
        self.last_rendered_keys = tuple()
        self.render_detected(self.last_debug_lines, preserve_scroll=True, force=True)

    def reset_info_canvas_width(self) -> None:
        """Re-anchor the card container to the current canvas width.

        Repeated docking/undocking can leave Tk with stale requested widths until
        the next Configure event. Forcing the window width here prevents the
        cards from gradually narrowing after several dock changes.
        """
        try:
            self.root.update_idletasks()
            width = max(1, self.info_canvas.winfo_width())
            self.info_canvas.itemconfigure(self.card_window, width=width)
            self.info_canvas.configure(scrollregion=self.info_canvas.bbox("all"))
        except Exception:
            pass

    def _on_mousewheel(self, event) -> None:
        # Windows mousewheel delta is usually +/-120.
        self.info_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def clear_cards(self) -> None:
        for widget in self.card_container.winfo_children():
            widget.destroy()
        for col in range(4):
            self.card_container.columnconfigure(col, weight=0, uniform="")

    def normalize_window_title(self, title: str) -> str:
        title = re.sub(r"\([^)]*fps[^)]*\)", "", title or "", flags=re.IGNORECASE)
        title = re.sub(r"\s+", " ", title).strip()
        return title

    def list_visible_windows(self) -> List[dict]:
        if sys.platform != "win32":
            return []
        user32 = ctypes.windll.user32
        windows: List[dict] = []

        def visible_window_rect(hwnd) -> Optional[Rect]:
            rect = ctypes.wintypes.RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return None
            best = rect
            try:
                # GetWindowRect can include invisible resize borders and can be
                # DPI-virtualized in some process states. DWM's extended frame
                # bounds are the visible window bounds, which is what docking
                # should sit flush against.
                dwm_rect = ctypes.wintypes.RECT()
                result = ctypes.windll.dwmapi.DwmGetWindowAttribute(
                    hwnd,
                    9,  # DWMWA_EXTENDED_FRAME_BOUNDS
                    ctypes.byref(dwm_rect),
                    ctypes.sizeof(dwm_rect),
                )
                if result == 0 and dwm_rect.right > dwm_rect.left and dwm_rect.bottom > dwm_rect.top:
                    best = dwm_rect
            except Exception:
                pass
            return Rect(
                int(best.left),
                int(best.top),
                int(best.right - best.left),
                int(best.bottom - best.top),
            )

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def enum_proc(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            title = buffer.value.strip()
            if not title or title == self.root.title():
                return True
            rect = visible_window_rect(hwnd)
            if rect is None:
                return True
            width = int(rect.w)
            height = int(rect.h)
            if width < 80 or height < 80:
                return True
            windows.append({
                "hwnd": int(hwnd),
                "title": title,
                "match_text": self.normalize_window_title(title),
                "rect": rect,
            })
            return True

        user32.EnumWindows(enum_proc, 0)
        return sorted(windows, key=lambda w: w["title"].lower())

    def select_game_window_region(self) -> None:
        windows = self.list_visible_windows()
        if not windows:
            messagebox.showinfo("Window region", "No visible windows were found. This automatic option is Windows-only; use Game Region instead.")
            return
        selected = self.select_window_dialog(windows)
        if not selected:
            return
        self.apply_window_region(selected, reset_name_regions=True)
        self.status_var.set(f"Attached to window: {selected['title']} ({self.game_region.w}×{self.game_region.h}).")
        self.update_preview()

    def select_window_dialog(self, windows: List[dict]) -> Optional[dict]:
        dialog = tk.Toplevel(self.root)
        dialog.title("Select game window")
        dialog.configure(bg=PAGE_BG)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(True, True)
        dialog.geometry("560x360")

        tk.Label(dialog, text="Select a running emulator/game window", bg=PAGE_BG, fg=WHITE, font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=12, pady=(12, 6))
        tk.Label(dialog, text="This uses the full outer window bounds, including title/menu bars.", bg=PAGE_BG, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", padx=12, pady=(0, 6))

        listbox = tk.Listbox(dialog, bg=CARD_BG, fg=TEXT, selectbackground=BLUE, activestyle="none")
        listbox.pack(fill="both", expand=True, padx=12, pady=6)
        for w in windows:
            r = w["rect"]
            listbox.insert("end", f"{w['title']}   [{r.w}×{r.h} at {r.x},{r.y}]")
        if windows:
            listbox.selection_set(0)
        result = {"window": None}

        def choose(_event=None):
            selection = listbox.curselection()
            if selection:
                result["window"] = windows[selection[0]]
            dialog.destroy()

        def cancel():
            result["window"] = None
            dialog.destroy()

        buttons = tk.Frame(dialog, bg=PAGE_BG)
        buttons.pack(fill="x", padx=12, pady=(4, 12))
        ttk.Button(buttons, text="Use Window", command=choose).pack(side="right", padx=(6, 0))
        ttk.Button(buttons, text="Cancel", command=cancel).pack(side="right")
        listbox.bind("<Double-Button-1>", choose)
        dialog.bind("<Return>", choose)
        dialog.bind("<Escape>", lambda _event: cancel())
        dialog.wait_window()
        return result["window"]

    def apply_window_region(self, window: dict, reset_name_regions: bool = False, clear_detection: bool = True) -> None:
        old_region = self.game_region
        new_region = window["rect"]
        region_size_changed = bool(old_region and (old_region.w != new_region.w or old_region.h != new_region.h))
        region_changed = bool(
            not old_region
            or old_region.x != new_region.x
            or old_region.y != new_region.y
            or old_region.w != new_region.w
            or old_region.h != new_region.h
        )
        self.game_region = new_region
        self.attached_window_title = window.get("title", "")
        self.window_match_text = window.get("match_text") or self.normalize_window_title(self.attached_window_title)
        if reset_name_regions:
            # Window Region should only define the game/window bounds. Users then
            # add precise name boxes or a broad Name Area.
            self.name_regions = []
            self.name_scan_area = None
        elif region_size_changed and old_region:
            # Name regions and Name Area are relative to the attached window.
            # When the emulator is resized, scale both; when it is only moved,
            # keep the relative regions unchanged so they follow automatically.
            sx = new_region.w / max(1, old_region.w)
            sy = new_region.h / max(1, old_region.h)
            self.name_regions = [Rect(int(r.x * sx), int(r.y * sy), max(1, int(r.w * sx)), max(1, int(r.h * sy))) for r in self.name_regions]
            if self.name_scan_area:
                r = self.name_scan_area
                self.name_scan_area = Rect(int(r.x * sx), int(r.y * sy), max(1, int(r.w * sx)), max(1, int(r.h * sy)))

        # Important: automatic window refresh happens while tracking.  Earlier
        # versions cleared current_keys on every refresh, which could leave the
        # pane stuck on the scanning card even when OCR had read a valid name.
        # Keep the live card visible unless this was an intentional new setup or
        # the window dimensions changed enough that the name regions were scaled.
        if clear_detection or reset_name_regions or region_size_changed:
            self.current_keys.clear()
            self.slot_form_overrides.clear()
            self.scan_histories.clear()
            self.slot_miss_counts.clear()
            self.auto_slot_pending.clear()
            self.last_rendered_keys = tuple()
            try:
                self.render_detected(self.last_debug_lines, force=True)
            except Exception:
                pass
        elif region_changed and self.preview_visible.get():
            # Moving the emulator should update the preview, but should not wipe
            # the detected Pokémon card.
            self.update_preview()

    def refresh_attached_window_region(self, silent: bool = False, redock_on_move: bool = True) -> bool:
        if not self.window_match_text:
            if not silent:
                messagebox.showinfo("Auto window region", "Use Window Region first so the monitor knows which window to track.")
            return False
        target = self.normalize_window_title(self.window_match_text).lower()
        windows = self.list_visible_windows()
        candidates = [w for w in windows if w.get("match_text", "").lower() == target]
        if not candidates:
            candidates = [w for w in windows if target and target in w.get("match_text", "").lower()]
        if not candidates:
            if not silent:
                messagebox.showwarning("Auto window region", "Could not find the attached window. Use Window Region again.")
            return False
        old_region = self.game_region
        self.apply_window_region(candidates[0], reset_name_regions=False, clear_detection=False)
        moved = bool(old_region and self.game_region and (old_region.x != self.game_region.x or old_region.y != self.game_region.y or old_region.w != self.game_region.w or old_region.h != self.game_region.h))
        if moved and redock_on_move and self.running and self.auto_window_region.get() and not self.controls_visible.get():
            # Keep the companion flush with the attached emulator window when it
            # is dragged or resized. Name regions are relative, so they follow
            # the window automatically; the monitor window should follow too.
            try:
                self.dock_to_game_region(self.last_docked_position or self.dock_position.get())
            except Exception:
                pass
        if not silent:
            self.status_var.set(f"Refreshed window region from {candidates[0]['title']}.")
            self.update_preview()
        return True

    def save_config(self) -> None:
        CONFIG_PATH.write_text(json.dumps(self.config, indent=2), encoding="utf-8")

    def set_tesseract_path(self) -> None:
        path = filedialog.askopenfilename(
            title="Select tesseract.exe",
            initialdir="C:/Program Files/Tesseract-OCR",
            filetypes=[("Tesseract executable", "tesseract.exe"), ("Executable", "*.exe"), ("All files", "*.*")],
        )
        if not path:
            return
        self.config["tesseract_cmd"] = path
        self.save_config()
        self.ocr.set_tesseract_cmd(path)
        self.status_var.set(self.ocr.diagnostic_message())
        messagebox.showinfo("OCR setup", self.ocr.diagnostic_message())

    def check_ocr_setup(self) -> None:
        messagebox.showinfo("OCR setup", self.ocr.diagnostic_message())
        self.status_var.set(self.ocr.diagnostic_message())

    def toggle_controls_panel(self) -> None:
        if self.controls_visible.get():
            self.controls_frame.grid_remove()
            self.controls_visible.set(False)
            self.controls_button_text.set("Show Controls")
            self.compact_topbar.grid()
            self.root.minsize(DOCK_MIN_WIDTH, DOCK_MIN_HEIGHT)
            if self.game_region and not self.docking_in_progress:
                self.dock_to_game_region(self.last_docked_position or self.dock_position.get())
                return
            elif not self.docking_in_progress and self.root.winfo_width() > 640:
                width = ULTRA_DOCK_WIDTH if self.ultra_compact.get() else DOCK_WIDTH
                self.root.geometry(f"{width}x560")
            self.reset_info_canvas_width()
            self.status_var.set("Controls hidden. Use Show Controls to adjust regions, profiles, or tracking.")
        else:
            self.controls_frame.grid()
            self.controls_visible.set(True)
            self.controls_button_text.set("Hide Controls")
            self.compact_topbar.grid_remove()
            self.root.minsize(EXPANDED_CONTROLS_MIN_WIDTH, 400)
            self.position_expanded_controls_window()
            self.reset_info_canvas_width()
            self.status_var.set("Controls shown.")

    def position_expanded_controls_window(self) -> None:
        """Show controls by expanding away from the selected game region.

        In docked mode, the game region is treated as a hard no-overlap boundary.
        If the monitor is docked to the left, the window expands further left and
        keeps its right edge flush to the game. If there is not enough room for
        the full target width, it uses whatever space exists instead of jumping
        over the game window.
        """
        target_w = EXPANDED_CONTROLS_TARGET_WIDTH
        target_h = max(580, self.root.winfo_height())
        screen_w = max(1, self.root.winfo_screenwidth())
        screen_h = max(1, self.root.winfo_screenheight())

        if not self.game_region:
            width = min(target_w, screen_w)
            height = min(target_h, screen_h)
            self.root.geometry(f"{int(width)}x{int(height)}+{int(max(0, min(self.root.winfo_x(), screen_w - width)))}+{int(max(0, min(self.root.winfo_y(), screen_h - height)))}")
            return

        region = self.game_region
        position = (self.last_docked_position or self.dock_position.get() or "left").lower()
        min_w = EXPANDED_CONTROLS_MIN_WIDTH
        hard_min_w = CONTROL_PANEL_WIDTH + 24
        min_h = 400

        def clamp_y(preferred_y: int, height: int) -> int:
            return int(max(0, min(preferred_y, max(0, screen_h - height))))

        def left_rect():
            available = max(0, region.x)
            if available < hard_min_w:
                return None
            width = max(min_w, min(target_w, available)) if available >= min_w else available
            if width <= 0:
                return None
            x = max(0, region.x - width)
            height = min(target_h, screen_h)
            y = clamp_y(region.y, height)
            return int(width), int(height), int(x), int(y)

        def right_rect():
            available = max(0, screen_w - (region.x + region.w))
            if available < hard_min_w:
                return None
            width = max(min_w, min(target_w, available)) if available >= min_w else available
            if width <= 0:
                return None
            x = region.x + region.w
            height = min(target_h, screen_h)
            y = clamp_y(region.y, height)
            return int(width), int(height), int(x), int(y)

        def above_rect():
            available = max(0, region.y)
            if available < min_h:
                return None
            height = max(min_h, min(target_h, available))
            width = min(target_w, screen_w)
            x = int(max(0, min(region.x, max(0, screen_w - width))))
            y = int(region.y - height)
            return int(width), int(height), x, y

        def below_rect():
            available = max(0, screen_h - (region.y + region.h))
            if available < min_h:
                return None
            height = max(min_h, min(target_h, available))
            width = min(target_w, screen_w)
            x = int(max(0, min(region.x, max(0, screen_w - width))))
            y = int(region.y + region.h)
            return int(width), int(height), x, y

        strategies = {
            "left": left_rect,
            "right": right_rect,
            "above": above_rect,
            "below": below_rect,
        }
        # Prefer the current dock side first, then other positions that can be
        # shown without touching the selected game region.
        fallback_order = {
            "left": ["above", "below", "right"],
            "right": ["above", "below", "left"],
            "above": ["left", "right", "below"],
            "below": ["left", "right", "above"],
        }
        rect = strategies.get(position, left_rect)()
        used_position = position
        if rect is None:
            for candidate in fallback_order.get(position, ["left", "right", "above", "below"]):
                rect = strategies[candidate]()
                if rect is not None:
                    used_position = candidate
                    break

        if rect is None:
            # Last resort: keep the monitor on the same side and use the smallest
            # possible on-screen size. This can be cramped, but still avoids the
            # selected game region when any side space exists.
            width = min(target_w, max(min_w, screen_w))
            height = min(target_h, screen_h)
            x = max(0, min(self.root.winfo_x(), max(0, screen_w - width)))
            y = max(0, min(self.root.winfo_y(), max(0, screen_h - height)))
            rect = (int(width), int(height), int(x), int(y))
            used_position = "current screen space"

        width, height, x, y = rect
        self.root.minsize(min(EXPANDED_CONTROLS_MIN_WIDTH, max(1, width)), 400)
        self.root.geometry(f"{int(width)}x{int(height)}+{int(x)}+{int(y)}")
        self.reset_info_canvas_width()
        self.status_var.set(f"Controls shown {used_position}; game region was not overlapped.")

    def toggle_preview(self) -> None:
        self.preview_visible.set(not self.preview_visible.get())
        if self.preview_visible.get():
            self.preview_button_text.set("Hide Preview")
            self.preview_box.grid()
            self.update_preview(force=True)
        else:
            self.preview_button_text.set("Show Preview")
            self.preview_box.grid_remove()

    def select_game_region(self) -> None:
        self.root.withdraw()
        rect = select_screen_region(self.root, "Select the full emulator/game window region")
        self.root.deiconify()
        if not rect:
            self.status_var.set("Game region selection cancelled.")
            return
        self.game_region = rect
        self.attached_window_title = ""
        self.window_match_text = ""
        # Game Region now defines only the capture bounds. Users add precise name
        # boxes separately, which avoids random UI text being forced into a
        # Pokémon name when no battle name is visible.
        self.name_regions = []
        self.name_scan_area = None
        self.current_keys.clear()
        self.slot_form_overrides.clear()
        self.scan_histories.clear()
        self.slot_miss_counts.clear()
        self.auto_slot_pending.clear()
        self.last_rendered_keys = tuple()
        self.status_var.set(f"Game region set: {rect.w}×{rect.h} at {rect.x},{rect.y}. Add one or more name regions.")
        self.update_preview()
        self.render_detected(self.last_debug_lines, force=True)

    def select_name_scan_area(self) -> None:
        """Select a broad area that contains all possible enemy nameplates.

        v23 stores this separately from the precise name boxes. It is used as a
        setup aid now and prepares the app for automatic single/double battle
        panel detection without forcing a wrong layout.
        """
        if not self.game_region:
            messagebox.showinfo("Select game region first", "Select or attach the full game/window region first.")
            return
        self.root.withdraw()
        rect = select_screen_region(self.root, "Select the total area containing enemy nameplates")
        self.root.deiconify()
        if not rect:
            self.status_var.set("Name area selection cancelled.")
            return
        rel = Rect(rect.x - self.game_region.x, rect.y - self.game_region.y, rect.w, rect.h).normalized()
        rel = Rect(
            max(0, min(rel.x, self.game_region.w - 1)),
            max(0, min(rel.y, self.game_region.h - 1)),
            max(1, min(rel.w, self.game_region.w - rel.x)),
            max(1, min(rel.h, self.game_region.h - rel.y)),
        )
        self.name_scan_area = rel
        self.current_keys.clear()
        self.slot_form_overrides.clear()
        self.scan_histories.clear()
        self.slot_miss_counts.clear()
        self.auto_slot_pending.clear()
        self.last_rendered_keys = tuple()
        derived = self.derive_regions_from_name_area()
        self.status_var.set(
            f"Name Area set: {rel.w}×{rel.h} at +{rel.x},+{rel.y}. "
            f"It will scan as {len(derived)} slot(s). Add Name regions later if you want tighter crops."
        )
        self.update_preview()
        self.render_detected(self.last_debug_lines, force=True)

    def add_name_region(self) -> None:
        if not self.game_region:
            messagebox.showinfo("Select game region first", "Select the full game region before adding name regions.")
            return
        self.root.withdraw()
        rect = select_screen_region(self.root, "Select a Pokémon name box region")
        self.root.deiconify()
        if not rect:
            self.status_var.set("Name region selection cancelled.")
            return
        rel = Rect(rect.x - self.game_region.x, rect.y - self.game_region.y, rect.w, rect.h).normalized()
        # Clip to the game region.
        rel = Rect(
            max(0, min(rel.x, self.game_region.w - 1)),
            max(0, min(rel.y, self.game_region.h - 1)),
            max(1, min(rel.w, self.game_region.w - rel.x)),
            max(1, min(rel.h, self.game_region.h - rel.y)),
        )
        # If only the auto top-left region exists, replace it with the user's precise region.
        auto = Rect(0, 0, self.game_region.w // 2, self.game_region.h // 2)
        if len(self.name_regions) == 1 and self.name_regions[0] == auto:
            self.name_regions = []
        self.name_regions.append(rel)
        self.status_var.set(f"Added name region {len(self.name_regions)}: {rel.w}×{rel.h} at +{rel.x},+{rel.y}.")
        self.current_keys.clear()
        self.slot_form_overrides.clear()
        self.scan_histories.clear()
        self.slot_miss_counts.clear()
        self.auto_slot_pending.clear()
        self.last_rendered_keys = tuple()
        self.update_preview()
        self.render_detected(self.last_debug_lines, force=True)

    def clear_name_regions(self) -> None:
        self.name_regions.clear()
        self.current_keys.clear()
        self.slot_form_overrides.clear()
        self.scan_histories.clear()
        self.slot_miss_counts.clear()
        self.auto_slot_pending.clear()
        self.last_rendered_keys = tuple()
        self.status_var.set("Name regions cleared. Add one or more name regions before tracking.")
        self.update_preview()
        self.render_detected(self.last_debug_lines, force=True)

    def capture_rect(self, rect: Rect) -> Image.Image:
        monitor = {"left": rect.x, "top": rect.y, "width": rect.w, "height": rect.h}
        shot = self.sct.grab(monitor)
        return Image.frombytes("RGB", shot.size, shot.rgb)

    def absolute_name_rect(self, rel: Rect) -> Rect:
        assert self.game_region is not None
        return Rect(self.game_region.x + rel.x, self.game_region.y + rel.y, rel.w, rel.h)

    def derive_regions_from_name_area(self) -> List[Rect]:
        """Return the broad Name Area as the auto-detection source.

        Earlier versions split a tall Name Area into two fixed halves. That did
        work for some double battles, but it also made single battles flicker a
        false Slot 2 because the lower half often contained grass, menus, or HP
        bars. v25 keeps the broad area intact and lets the OCR worker look for
        actual purple battle nameplates inside it. If it finds two panels, it
        scans two slots; if it finds one panel, it scans one slot.
        """
        if not self.name_scan_area:
            return []
        area = self.name_scan_area
        return [Rect(area.x, area.y, area.w, area.h)]

    def effective_name_regions(self) -> List[Rect]:
        """Name regions currently used for OCR.

        v24: Name Area now counts as a tracking source when no precise Add Name
        regions are present.
        """
        if self.name_regions:
            return [Rect(r.x, r.y, r.w, r.h) for r in self.name_regions]
        return self.derive_regions_from_name_area()

    def has_tracking_regions(self) -> bool:
        return bool(self.game_region and self.effective_name_regions())

    def update_preview(self, force: bool = False) -> None:
        if not self.preview_visible.get() and not force:
            return
        if not self.game_region:
            self.preview_label.configure(text="No game region selected", image="")
            return
        try:
            img = self.capture_rect(self.game_region)
        except Exception as exc:
            self.status_var.set(f"Could not capture preview: {exc}")
            return
        draw = ImageDraw.Draw(img)
        if self.name_scan_area:
            rel = self.name_scan_area
            draw.rectangle([rel.x, rel.y, rel.x + rel.w, rel.y + rel.h], outline="cyan", width=2)
            draw.text((rel.x + 4, rel.y + 4), "Name Area", fill="cyan")
        for i, rel in enumerate(self.name_regions, start=1):
            draw.rectangle([rel.x, rel.y, rel.x + rel.w, rel.y + rel.h], outline="red", width=3)
            draw.text((rel.x + 4, rel.y + 4), f"Name {i}", fill="red")
        if not self.name_regions and self.name_scan_area:
            rel = self.name_scan_area
            draw.text((rel.x + 4, rel.y + max(16, rel.h - 18)), "Auto detects panels here", fill="orange")
        max_w, max_h = 720, 120
        scale = min(max_w / img.width, max_h / img.height, 1)
        if scale < 1:
            img = img.resize((int(img.width * scale), int(img.height * scale)), Image.Resampling.LANCZOS)
        self.preview_photo = ImageTk.PhotoImage(img)
        self.preview_label.configure(image=self.preview_photo, text="")

    def start_tracking(self) -> None:
        if self.running:
            self.status_var.set("Tracking is already running. Use Stop before starting a new scan loop.")
            return
        if not self.game_region:
            messagebox.showinfo("Missing region", "Select a game region first.")
            return
        if not self.effective_name_regions():
            messagebox.showinfo("Missing name regions", "Add at least one name region or select a Name Area.")
            return
        if not self.ocr.available:
            messagebox.showerror("OCR setup needed", self.ocr.diagnostic_message())
            self.status_var.set(self.ocr.diagnostic_message())
            return
        if self.auto_window_region.get():
            self.refresh_attached_window_region(silent=True)
        docked = False
        if self.dock_on_start.get():
            self.dock_to_game_region(self.dock_position.get())
            docked = True
        self.running = True
        self.scan_worker_active = False
        self.active_scan_tick = 0
        self.active_scan_started_at = 0.0
        self.last_scan_completed_at = time.monotonic()
        self.scan_status_var.set("Scanning…")
        self.schedule_scan_watchdog()
        self.schedule_follow_window()
        while not self.scan_result_queue.empty():
            try:
                self.scan_result_queue.get_nowait()
            except queue.Empty:
                break
        self.status_var.set("Tracking started. Cards update only when the detected Pokémon changes." + (" Docked beside the selected game region." if docked else ""))
        # Replace the first-run idle helper immediately so users can see that
        # the configured region is actively being scanned.
        if not self.current_keys:
            self.render_detected(self.last_debug_lines, force=True)
        self.root.after(50, self.scan_once)

    def set_and_dock(self, position: str) -> None:
        self.dock_position.set(position)
        if self.auto_window_region.get():
            self.refresh_attached_window_region(silent=True)
        self.dock_to_game_region(position)

    def on_compact_option_changed(self) -> None:
        self.last_rendered_keys = tuple()
        self.render_detected(self.last_debug_lines, preserve_scroll=True, force=True)
        if not self.controls_visible.get() and self.root.winfo_width() > 360:
            width = ULTRA_DOCK_WIDTH if self.ultra_compact.get() else DOCK_WIDTH
            self.root.geometry(f"{width}x{max(DOCK_MIN_HEIGHT, self.root.winfo_height())}")
            self.reset_info_canvas_width()

    def own_visible_window_rect(self) -> Optional[Rect]:
        """Return the monitor's actual outer visible bounds on Windows."""
        if sys.platform != "win32":
            return None
        try:
            hwnd = int(self.root.winfo_id())
            try:
                root_hwnd = ctypes.windll.user32.GetAncestor(hwnd, 2)  # GA_ROOT
                if root_hwnd:
                    hwnd = int(root_hwnd)
            except Exception:
                pass

            rect = ctypes.wintypes.RECT()
            if not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return None
            best = rect
            try:
                dwm_rect = ctypes.wintypes.RECT()
                result = ctypes.windll.dwmapi.DwmGetWindowAttribute(
                    hwnd,
                    9,  # DWMWA_EXTENDED_FRAME_BOUNDS
                    ctypes.byref(dwm_rect),
                    ctypes.sizeof(dwm_rect),
                )
                if result == 0 and dwm_rect.right > dwm_rect.left and dwm_rect.bottom > dwm_rect.top:
                    best = dwm_rect
            except Exception:
                pass
            return Rect(
                int(best.left),
                int(best.top),
                int(best.right - best.left),
                int(best.bottom - best.top),
            )
        except Exception:
            return None

    def correct_docked_window_frame_overlap(self, requested: str, region: Rect) -> None:
        """Nudge the native Tk window frame clear of the game boundary."""
        rect = self.own_visible_window_rect()
        if not rect:
            return
        dx = 0
        dy = 0
        if requested == "left":
            overlap = (rect.x + rect.w) - (region.x - DOCK_GAP)
            if overlap > 0:
                dx = -overlap
        elif requested == "right":
            overlap = (region.x + region.w + DOCK_GAP) - rect.x
            if overlap > 0:
                dx = overlap
        elif requested == "above":
            overlap = (rect.y + rect.h) - (region.y - DOCK_GAP)
            if overlap > 0:
                dy = -overlap
        elif requested == "below":
            overlap = (region.y + region.h + DOCK_GAP) - rect.y
            if overlap > 0:
                dy = overlap

        if dx or dy:
            self.root.geometry(
                f"{self.root.winfo_width()}x{self.root.winfo_height()}"
                f"+{int(self.root.winfo_x() + dx)}+{int(self.root.winfo_y() + dy)}"
            )

    def dock_to_game_region(self, position: Optional[str] = None) -> None:
        """Dock the compact monitor around the selected game region without overlap.

        v23 intentionally honors the selected direction instead of silently
        falling back to the opposite side. If there is not enough visible screen
        space on that side, the window may be partly off-screen, but it will not
        be placed over the selected game region.
        """
        if self.window_match_text:
            # Manual docking, Hide Controls -> dock, and Dock Now should all use
            # the latest attached-window rectangle. Follow mode already refreshes
            # on a timer, but relying on the next timer tick can leave a visible
            # gap until the emulator is moved again.
            self.refresh_attached_window_region(silent=True, redock_on_move=False)

        if not self.game_region:
            messagebox.showinfo("Missing region", "Select or attach a game region first.")
            return

        if self.preview_visible.get():
            self.toggle_preview()
        if self.controls_visible.get():
            self.docking_in_progress = True
            try:
                self.toggle_controls_panel()
            finally:
                self.docking_in_progress = False
            if self.window_match_text:
                self.refresh_attached_window_region(silent=True, redock_on_move=False)
        self.root.update_idletasks()

        region = self.game_region
        requested = (position or self.dock_position.get() or "left").lower()
        if requested not in {"left", "right", "above", "below"}:
            requested = "left"
        self.dock_position.set(requested)

        screen_w = max(1, self.root.winfo_screenwidth())
        screen_h = max(1, self.root.winfo_screenheight())
        side_width = ULTRA_DOCK_WIDTH if self.ultra_compact.get() else DOCK_WIDTH
        min_w = DOCK_MIN_WIDTH
        min_h = DOCK_MIN_HEIGHT

        def choose_side_width(available: int) -> int:
            # Keep docked width stable across Show Controls -> Dock cycles.
            # Shrink only when the requested side is genuinely tight.
            target = int(side_width)
            if available >= target:
                return target
            if available >= min_w:
                return int(available)
            return int(min_w)

        def choose_vertical_dock_height(preferred_y: int) -> tuple[int, int]:
            # Keep the top edge aligned with the game window when possible.
            # Earlier builds clamped y upward when the emulator was moved lower,
            # which made the dock look detached. Shrink height first, then clamp
            # only if the requested top is actually off-screen.
            y = int(max(0, preferred_y))
            height = int(max(min_h, region.h - WINDOW_DECORATION_HEIGHT_ESTIMATE))
            available_below = max(0, screen_h - y)
            if available_below >= min_h:
                height = min(height, available_below)
            else:
                height = min_h
                y = max(0, screen_h - height)
            return int(y), int(height)

        # Horizontal docks match the selected game region height.  Vertical
        # docks match the selected game region width and use a shallow info bar.
        if requested == "left":
            available = max(0, region.x)
            width = choose_side_width(available)
            y, height = choose_vertical_dock_height(region.y)
            x = region.x - width
        elif requested == "right":
            available = max(0, screen_w - (region.x + region.w))
            width = choose_side_width(available)
            y, height = choose_vertical_dock_height(region.y)
            x = region.x + region.w
        elif requested == "above":
            available_h = max(0, region.y)
            width = max(min_w, min(region.w, screen_w))
            height = min(DOCK_HORIZONTAL_HEIGHT, available_h) if available_h >= 180 else DOCK_HORIZONTAL_HEIGHT
            x = region.x
            y = region.y - height
        else:  # below
            available_h = max(0, screen_h - (region.y + region.h))
            width = max(min_w, min(region.w, screen_w))
            height = min(DOCK_HORIZONTAL_HEIGHT, available_h) if available_h >= 180 else DOCK_HORIZONTAL_HEIGHT
            x = region.x
            y = region.y + region.h

        # Clamp only along the axis perpendicular to the requested dock side.
        # Do not clamp across the game boundary, because that is what made Right
        # become Left and Below become Above in earlier builds.
        if requested in {"left", "right"}:
            # y/height already handled by choose_vertical_dock_height so moving
            # the emulator downward does not pull the companion upward unless
            # there is genuinely no screen space left.
            y = int(y)
        else:
            x = max(0, min(int(x), max(0, screen_w - int(width))))

        width = int(max(1, width))
        height = int(max(1, height))
        x = int(x)
        y = int(y)

        self.last_docked_position = requested
        self.last_docked_time = time.monotonic()
        self.root.minsize(min_w, min_h)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.lift()
        self.root.update_idletasks()
        self.correct_docked_window_frame_overlap(requested, region)
        self.root.update_idletasks()
        self.reset_info_canvas_width()
        self.last_rendered_keys = tuple()
        self.render_detected(self.last_debug_lines, preserve_scroll=True, force=True)
        self.status_var.set(f"Docked {requested} of the selected game region.")

    def stop_tracking(self) -> None:
        self.running = False
        # Mark any in-flight OCR result as stale. The worker thread may still
        # finish later, but it will be ignored instead of updating the UI.
        self.active_scan_tick = 0
        self.scan_worker_active = False
        self.scan_status_var.set("Stopped")
        if self.scan_watchdog_job:
            try:
                self.root.after_cancel(self.scan_watchdog_job)
            except Exception:
                pass
            self.scan_watchdog_job = None
        if self.follow_window_job:
            try:
                self.root.after_cancel(self.follow_window_job)
            except Exception:
                pass
            self.follow_window_job = None
        self.status_var.set("Tracking stopped.")

    def schedule_scan_watchdog(self) -> None:
        if self.scan_watchdog_job:
            try:
                self.root.after_cancel(self.scan_watchdog_job)
            except Exception:
                pass
        self.scan_watchdog_job = self.root.after(1000, self.scan_watchdog)

    def schedule_follow_window(self) -> None:
        """Keep dock/window-follow movement independent from OCR scanning.

        OCR can occasionally take a while on Name Area scans.  The companion
        should still stay attached to the emulator while the OCR worker is
        busy, so this runs on its own Tk timer instead of waiting for scan_once.
        """
        if self.follow_window_job:
            try:
                self.root.after_cancel(self.follow_window_job)
            except Exception:
                pass
        self.follow_window_job = self.root.after(FOLLOW_WINDOW_INTERVAL_MS, self.follow_window_tick)

    def follow_window_tick(self) -> None:
        self.follow_window_job = None
        if not self.running:
            return
        if self.auto_window_region.get() and self.window_match_text:
            try:
                self.refresh_attached_window_region(silent=True)
            except Exception:
                pass
        self.schedule_follow_window()

    def scan_watchdog(self) -> None:
        self.scan_watchdog_job = None
        if not self.running:
            return
        now = time.monotonic()
        if self.scan_worker_active and self.active_scan_started_at and (now - self.active_scan_started_at) > 5.0:
            # Abandon a stuck Tesseract worker. Its late result will be ignored
            # because active_scan_tick is reset before the next scan starts.
            self.scan_worker_active = False
            self.active_scan_tick = 0
            self.scan_status_var.set("OCR retrying…")
            self.root.after(100, self.scan_once)
        elif (not self.scan_worker_active) and self.last_scan_completed_at and (now - self.last_scan_completed_at) > 4.0:
            # Safety net for rare Tk scheduling stalls after long idle periods.
            self.scan_status_var.set("OCR resuming…")
            self.root.after(100, self.scan_once)
        self.schedule_scan_watchdog()

    def scan_once(self) -> None:
        if not self.running:
            return
        if self.scan_worker_active:
            # Do not start overlapping OCR jobs; Tesseract can be slow on some
            # machines. The polling loop will finish the active scan when ready.
            self.scan_status_var.set("OCR busy…")
            self.root.after(200, self.poll_scan_result)
            return

        self.scan_tick += 1
        # Window following is handled by follow_window_tick(), independently
        # from OCR.  Do not wait for scan ticks here.

        if not self.game_region:
            self.running = False
            self.scan_status_var.set("Stopped")
            self.status_var.set("Tracking stopped: no game region is selected.")
            return

        game_region = Rect(self.game_region.x, self.game_region.y, self.game_region.w, self.game_region.h)
        name_regions = self.effective_name_regions()
        if not name_regions:
            self.running = False
            self.scan_status_var.set("Stopped")
            self.status_var.set("Tracking stopped: add at least one Name region or Name Area.")
            self.render_detected(self.last_debug_lines, force=True)
            return
        self.active_scan_auto_area = bool((not self.name_regions) and self.name_scan_area)
        threshold = AUTO_AREA_MATCH_SCORE if self.active_scan_auto_area else int(float(self.threshold_var.get()))
        self.active_scan_threshold = threshold
        corrections = dict(self.ocr_corrections)
        # Drop stale results from any previous/abandoned worker before starting
        # a fresh scan. This prevents Stop/Start from showing old OCR output or
        # leaving the UI stuck on a stale in-flight scan.
        while not self.scan_result_queue.empty():
            try:
                self.scan_result_queue.get_nowait()
            except queue.Empty:
                break

        self.scan_worker_active = True
        self.active_scan_tick = self.scan_tick
        self.active_scan_started_at = time.monotonic()
        self.scan_status_var.set("OCR scan running…")

        worker = threading.Thread(
            target=self._scan_worker,
            args=(game_region, name_regions, threshold, corrections, self.scan_tick, self.active_scan_auto_area),
            daemon=True,
        )
        worker.start()
        self.root.after(50, self.poll_scan_result)

    def poll_scan_result(self) -> None:
        if not self.scan_worker_active:
            return
        try:
            scan_tick, results, worker_error = self.scan_result_queue.get_nowait()
        except queue.Empty:
            if self.running:
                # If Tesseract hangs despite its timeout, do not leave the UI
                # permanently stuck on "OCR scan running". Abandon this scan and
                # start a fresh one; stale worker results are ignored by scan_tick.
                if self.active_scan_started_at and (time.monotonic() - self.active_scan_started_at) > 7.0:
                    self.scan_worker_active = False
                    self.scan_status_var.set("OCR retrying…")
                    self.root.after(250, self.scan_once)
                    return
                self.root.after(75, self.poll_scan_result)
            return
        self.finish_scan(scan_tick, results, worker_error)

    def _ocr_text_is_plausible_name(self, text: str) -> bool:
        """Avoid forcing a Pokémon match from empty/noisy OCR.

        Exact local-repository names and user corrections are still allowed, but
        fuzzy matching is blocked for tiny fragments like "1 WW".
        """
        normalized = normalize_name(text)
        if not normalized:
            return False
        # Exact short names such as Mew/Muk should still be valid.
        if normalized in self.repo.candidate_to_key:
            return True
        cleaned = self.repo._clean_ocr_nameplate_text(text)
        letters = re.sub(r"[^A-Z]", "", cleaned or normalized)
        return len(letters) >= 4

    def _match_ocr_text(self, text: str, threshold: int, corrections: Dict[str, str]) -> Optional[MatchResult]:
        """Resolve one OCR string to a Pokémon using corrections + repository matching."""
        normalized = normalize_name(text)
        corrected_key = corrections.get(normalized)
        if corrected_key and corrected_key in self.repo.pokemon:
            record = self.repo.pokemon.get(corrected_key, {})
            return MatchResult(
                key=corrected_key,
                display_name=record.get("display_name") or corrected_key.replace("-", " ").title(),
                score=100.0,
                raw_text=text,
                normalized_text=normalized,
            )
        if not self._ocr_text_is_plausible_name(text):
            return None
        return self.repo.match_name(text, min_score=threshold)

    def _ocr_name_candidates(self, text: str) -> List[str]:
        """Return cleaned name-looking fragments from a noisy nameplate OCR read."""
        raw = (text or "").strip()
        if not raw:
            return []
        normalized = normalize_name(raw)
        cleaned = self.repo._clean_ocr_nameplate_text(raw)
        variants: List[str] = []
        for value in (raw, normalized, cleaned):
            value = re.sub(r"\s+", " ", value or "").strip()
            if value and value not in variants:
                variants.append(value)

        # Split text before a separated level marker. Avoid splitting inside
        # Pokémon names such as Jigglypuff by requiring whitespace before L/Lv.
        split_patterns = [
            r"\s+L\s*[VW]?\s*[0-9SBI]{0,3}.*$",
            r"\s+LV\s*[0-9SBI]{0,3}.*$",
            r"\s+LVL\s*[0-9SBI]{0,3}.*$",
            r"\s+LEVEL\s*[0-9SBI]{0,3}.*$",
            r"\s+LU[GTIS]*\s*[0-9SBI]{0,3}.*$",  # OCR variants of Lv/Lvl.
        ]
        for value in list(variants):
            for pattern in split_patterns:
                left = re.sub(pattern, "", value, flags=re.IGNORECASE).strip()
                if left and left != value and left not in variants:
                    variants.append(left)
        # Also try the first one to three words after removing level/HP noise;
        # this helps reads like "Chanseus LuGS eS" without breaking multi-word
        # Pokémon names such as Mr Mime or Tapu Koko.
        words = [w for w in re.split(r"\s+", cleaned) if w]
        for n in (1, 2, 3):
            if len(words) >= n:
                joined = " ".join(words[:n]).strip()
                if joined and joined not in variants:
                    variants.append(joined)
        return variants

    def _match_auto_area_text(self, text: str, threshold: int, corrections: Dict[str, str], source: str = "") -> Optional[MatchResult]:
        """Match OCR from broad Name Area mode with stricter context rules.

        General Name Area reads still use the high threshold. Crops that were
        already detected as nameplates may use a lower score on cleaned name
        fragments, which improves pixel-font cases without causing route/menu
        text to become Pokémon cards.
        """
        direct = self._match_ocr_text(text, threshold, corrections)
        if direct:
            return direct
        if not str(source or "").startswith("detected_panel"):
            return None
        best: Optional[MatchResult] = None
        for candidate_text in self._ocr_name_candidates(text):
            if not self._ocr_text_is_plausible_name(candidate_text):
                continue
            match = self.repo.match_name(candidate_text, min_score=AUTO_AREA_PANEL_RELAXED_SCORE)
            if match and (best is None or match.score > best.score):
                best = MatchResult(
                    key=match.key,
                    display_name=match.display_name,
                    score=match.score,
                    raw_text=text,
                    normalized_text=match.normalized_text,
                )
        return best

    def _raw_has_level_marker(self, text: str) -> bool:
        """Return True when OCR text looks like it came from a Pokémon nameplate.

        Most battle nameplates include a level marker. OCR can read "Lv58" as
        LV58, LW58, L 58, or occasionally LSB/LS8 depending on the font, so this
        check is deliberately permissive while still requiring a real level-like
        cue.
        """
        raw = (text or "").upper()
        normalized = normalize_name(text)
        return bool(
            re.search(r"\bL\s*[VW]?\s*\d{1,3}\b", raw)
            or re.search(r"\bLV\s*\d{1,3}\b", raw)
            or re.search(r"\bL[VW]?\s*[0-9SBI]{1,3}\b", normalized)
        )

    def _is_corrected_ocr(self, text: str, corrections: Dict[str, str]) -> bool:
        return normalize_name(text) in corrections

    def _auto_area_match_allowed(self, match: Optional[MatchResult], raw_text: str, corrections: Dict[str, str], slot_idx: int, source: str = "") -> bool:
        """Gate matches from broad Name Area scans.

        Name Area is user-friendly but broad, so it should not invent Pokémon
        from route/menu noise. Detected-panel crops are trusted more than the
        whole broad area, but second-slot auto detections are still debounced so
        empty double-battle space does not flicker into phantom cards.
        """
        if not match:
            return False
        source_text = str(source or "")
        if self._is_corrected_ocr(raw_text, corrections):
            return True
        if match.score >= 99.5:
            return True
        has_level = self._raw_has_level_marker(raw_text)
        detected_panel = source_text.startswith("detected_panel")

        if detected_panel:
            if slot_idx == 0:
                return match.score >= AUTO_AREA_PANEL_RELAXED_SCORE
            return match.score >= AUTO_AREA_TEXT_PANEL_SCORE

        if has_level and match.score >= AUTO_AREA_MATCH_SCORE:
            return True
        if slot_idx == 0 and match.score >= AUTO_AREA_STRONG_MATCH_SCORE:
            return True
        history = self.scan_histories.get(slot_idx)
        if history and list(history).count(match.key) >= 2 and match.score >= AUTO_AREA_MATCH_SCORE:
            return True
        return False

    def _auto_slot_confirmed(self, slot_idx: int, match: MatchResult, raw_text: str, corrections: Dict[str, str], source: str = "") -> bool:
        """Debounce automatic Name Area slots, especially Slot 2+.

        Slot 1 may appear immediately because a single battle only needs one
        opponent. Slot 2+ is accepted only after the same key appears twice, or
        when the match is exact/corrected/very high confidence. This reduces the
        alternating phantom second slot seen while scanning broad areas.
        """
        if slot_idx == 0:
            return True
        if self._is_corrected_ocr(raw_text, corrections) or match.score >= 99.5:
            self.auto_slot_pending.pop(slot_idx, None)
            return True
        if str(source or "").startswith("detected_panel") and match.score >= 94:
            self.auto_slot_pending.pop(slot_idx, None)
            return True
        prev_key, count = self.auto_slot_pending.get(slot_idx, ("", 0))
        count = count + 1 if prev_key == match.key else 1
        self.auto_slot_pending[slot_idx] = (match.key, count)
        return count >= AUTO_AREA_SECOND_SLOT_CONFIRM_SCANS

    def _merge_nameplate_regions(self, regions: List[Rect], image_size: tuple[int, int]) -> List[Rect]:
        """Merge overlapping visual/text nameplate candidates in reading order."""
        if not regions:
            return []
        img_w, img_h = image_size

        def iou_rect(a: Rect, b: Rect) -> float:
            ax1, ay1, ax2, ay2 = a.x, a.y, a.x + a.w, a.y + a.h
            bx1, by1, bx2, by2 = b.x, b.y, b.x + b.w, b.y + b.h
            ix1, iy1 = max(ax1, bx1), max(ay1, by1)
            ix2, iy2 = min(ax2, bx2), min(ay2, by2)
            if ix2 <= ix1 or iy2 <= iy1:
                return 0.0
            inter = (ix2 - ix1) * (iy2 - iy1)
            return inter / float(a.w * a.h + b.w * b.h - inter)

        cleaned: List[Rect] = []
        for r in regions:
            x = max(0, min(int(r.x), max(0, img_w - 1)))
            y = max(0, min(int(r.y), max(0, img_h - 1)))
            w = max(1, min(int(r.w), img_w - x))
            h = max(1, min(int(r.h), img_h - y))
            if w < 60 or h < 18:
                continue
            # Avoid dialogue/menu blocks that fill most of the selected area.
            if h > max(135, int(img_h * 0.70)):
                continue
            cleaned.append(Rect(x, y, w, h))

        kept: List[Rect] = []
        # Prefer wider/larger panel boxes first, then remove duplicates.
        for r in sorted(cleaned, key=lambda q: q.w * q.h, reverse=True):
            if any(iou_rect(r, old) > 0.35 for old in kept):
                continue
            kept.append(r)
        return sorted(kept, key=lambda q: (q.y, q.x))[:4]

    def _name_area_full_fallback_allowed(self, image: Image.Image) -> bool:
        """Allow whole-crop OCR only when Name Area looks like one tight panel.

        Broad Name Area mode should prefer detected nameplate panels. If panel
        detection finds nothing, OCRing the entire broad area can turn stale UI
        noise into a false Pokemon card. Keep the full-area fallback only for
        users who selected a single compact nameplate-sized rectangle.
        """
        w, h = image.size
        if w < 90 or h < 20:
            return False
        aspect = w / max(1, h)
        return h <= 85 and 2.0 <= aspect <= 8.5

    def detect_text_nameplate_regions_from_image(self, image: Image.Image) -> List[Rect]:
        """Find nameplates using OCR text evidence instead of a fixed UI color.

        A usable battle nameplate usually contains several pieces of evidence
        close together: a Pokémon-name candidate, a gender glyph or OCR stand-in,
        a level marker such as Lv/Lvl/Level, and a number. This detector groups
        sparse OCR word boxes into text rows and expands rows with enough
        evidence into panel candidates. It is used before the older color-based
        fallback so custom/fan-game nameplate colors can still work.
        """
        try:
            boxes = self.ocr.word_boxes(image)
        except Exception:
            boxes = []
        if not boxes:
            return []

        # Remove tiny punctuation-only noise while keeping level numbers.
        filtered = []
        for b in boxes:
            text = (b.text or "").strip()
            if not text:
                continue
            if b.width < 2 or b.height < 3:
                continue
            if not re.search(r"[A-Za-z0-9♀♂]", text):
                continue
            filtered.append(b)
        if not filtered:
            return []

        # Group words by approximate baseline/center row.
        filtered.sort(key=lambda b: (b.top + b.height / 2, b.left))
        median_h = sorted([max(1, b.height) for b in filtered])[len(filtered) // 2]
        row_tol = max(8, int(median_h * 0.9))
        rows: List[list] = []
        for box in filtered:
            cy = box.top + box.height / 2
            placed = False
            for row in rows:
                row_cy = sum(b.top + b.height / 2 for b in row) / max(1, len(row))
                if abs(cy - row_cy) <= row_tol:
                    row.append(box)
                    placed = True
                    break
            if not placed:
                rows.append([box])

        candidates: List[Rect] = []
        img_w, img_h = image.size
        for row in rows:
            row.sort(key=lambda b: b.left)
            line_text = " ".join(b.text for b in row)
            compact = re.sub(r"\s+", " ", line_text).strip()
            if not compact:
                continue
            x1 = min(b.left for b in row)
            y1 = min(b.top for b in row)
            x2 = max(b.left + b.width for b in row)
            y2 = max(b.top + b.height for b in row)
            line_w = x2 - x1
            line_h = y2 - y1
            if line_w < 30 or line_h < 8:
                continue

            raw_upper = compact.upper()
            normalized = normalize_name(compact)
            has_level = self._raw_has_level_marker(compact) or bool(re.search(r"\b(LV|LVL|LEVEL|L)\s*[0-9SBI]{1,3}\b", raw_upper))
            has_number = bool(re.search(r"\d", compact))
            has_gender = bool(re.search(r"[♀♂]", compact) or re.search(r"\b(MALE|FEMALE)\b", raw_upper))
            corrected = self._is_corrected_ocr(compact, self.ocr_corrections)
            match = self.repo.match_name(compact, min_score=76)
            exactish = bool(match and (match.score >= 98 or normalize_name(match.display_name) in normalized or normalized in self.repo.candidate_to_key))
            has_name = bool(match and match.score >= 82)

            # Require real name evidence. A level number alone is not enough,
            # and a fuzzy name alone must be extremely strong because overworld
            # textures can OCR into plausible-looking junk.
            if not corrected:
                if not has_name:
                    continue
                if not (has_level or has_gender or (has_number and match and match.score >= 94) or exactish or (match and match.score >= AUTO_AREA_STRONG_MATCH_SCORE)):
                    continue

            # Expand from the text row to a likely full panel. Expand more to
            # the right because Lv/HP bars often sit there; expand vertically to
            # include the border/background without grabbing dialogue boxes.
            pad_left = max(8, int(line_h * 0.9))
            pad_right = max(40, int(line_w * 0.45))
            pad_y = max(8, int(line_h * 0.8))
            rx = max(0, x1 - pad_left)
            ry = max(0, y1 - pad_y)
            rw = min(img_w - rx, line_w + pad_left + pad_right)
            rh = min(img_h - ry, line_h + pad_y * 2)
            candidates.append(Rect(rx, ry, rw, rh))

        return self._merge_nameplate_regions(candidates, image.size)

    def detect_nameplate_regions_from_image(self, image: Image.Image) -> List[Rect]:
        """Find likely Pokémon nameplates in a broad crop.

        v26 uses text/structure evidence first: Pokémon-like names, gender
        markers, level markers, and nearby numbers. The older purple-panel scan
        remains as a fallback for GBA-style UI, but Name Area is no longer tied
        to purple-only nameplates.
        """
        text_regions = self.detect_text_nameplate_regions_from_image(image)
        try:
            import numpy as np
        except Exception:
            return text_regions

        rgb = image.convert("RGB")
        arr = np.array(rgb)
        if arr.size == 0:
            return text_regions
        r = arr[:, :, 0].astype("int16")
        g = arr[:, :, 1].astype("int16")
        b = arr[:, :, 2].astype("int16")
        mask = (
            (r >= 70) & (r <= 190) &
            (g >= 35) & (g <= 145) &
            (b >= 95) & (b <= 235) &
            (b > g + 18) &
            (b >= r - 10)
        )
        h, w = mask.shape
        if w < 30 or h < 20:
            return text_regions

        seen = np.zeros_like(mask, dtype=bool)
        components = []
        min_pixels = max(180, int(w * h * 0.01))
        for y in range(h):
            xs = np.where(mask[y] & (~seen[y]))[0]
            for x in xs:
                if seen[y, x] or not mask[y, x]:
                    continue
                stack = [(int(x), int(y))]
                seen[y, x] = True
                min_x = max_x = int(x)
                min_y = max_y = int(y)
                count = 0
                while stack:
                    cx, cy = stack.pop()
                    count += 1
                    if cx < min_x: min_x = cx
                    if cx > max_x: max_x = cx
                    if cy < min_y: min_y = cy
                    if cy > max_y: max_y = cy
                    for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                        if 0 <= nx < w and 0 <= ny < h and (not seen[ny, nx]) and mask[ny, nx]:
                            seen[ny, nx] = True
                            stack.append((nx, ny))
                bw = max_x - min_x + 1
                bh = max_y - min_y + 1
                if count < min_pixels:
                    continue
                if bw < max(80, int(w * 0.16)) or bh < 24:
                    continue
                if bh > max(130, int(h * 0.65)):
                    # Usually a dialogue/menu box rather than a small nameplate.
                    continue
                aspect = bw / max(1, bh)
                if aspect < 2.0 or aspect > 8.5:
                    continue
                pad_x = max(4, int(bw * 0.03))
                pad_y = max(3, int(bh * 0.05))
                rx = max(0, min_x - pad_x)
                ry = max(0, min_y - pad_y)
                rw = min(w - rx, bw + pad_x * 2)
                rh = min(h - ry, bh + pad_y * 2)
                components.append((rx, ry, rw, rh, count))

        def iou(a, b):
            ax, ay, aw, ah, _ = a
            bx, by, bw, bh, _ = b
            ix1, iy1 = max(ax, bx), max(ay, by)
            ix2, iy2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
            if ix2 <= ix1 or iy2 <= iy1:
                return 0.0
            inter = (ix2 - ix1) * (iy2 - iy1)
            return inter / float(aw * ah + bw * bh - inter)

        kept = []
        for comp in sorted(components, key=lambda c: c[4], reverse=True):
            if any(iou(comp, old) > 0.45 for old in kept):
                continue
            kept.append(comp)
        kept = sorted(kept, key=lambda c: (c[1], c[0]))[:4]
        color_regions = [Rect(int(x), int(y), int(w_), int(h_)) for x, y, w_, h_, _ in kept]
        return self._merge_nameplate_regions(text_regions + color_regions, image.size)

    def _scan_worker(self, game_region: Rect, name_regions: List[Rect], threshold: int, corrections: Dict[str, str], scan_tick: int, auto_area_mode: bool = False) -> None:
        """Capture configured name regions and OCR them off the Tk UI thread.

        v21 deliberately restores the old successful behaviour: as soon as OCR
        text resolves to a Pokémon, that slot is considered detected. The worker
        no longer waits for every OCR preset after a confident name is found,
        which was the main reason the UI could sit forever on "OCR scan running".
        """
        results = []
        worker_error = None
        try:
            with mss.mss() as sct:
                scan_items = []
                if auto_area_mode and name_regions:
                    # In Name Area mode, capture the broad area once, find real
                    # nameplates inside it, and OCR those panels as slots. This
                    # replaces the old fixed top/bottom split that caused false
                    # Slot 2 cards in single battles and overworld screens.
                    rel = name_regions[0]
                    abs_rect = Rect(game_region.x + rel.x, game_region.y + rel.y, rel.w, rel.h)
                    monitor = {"left": abs_rect.x, "top": abs_rect.y, "width": abs_rect.w, "height": abs_rect.h}
                    shot = sct.grab(monitor)
                    area_img = Image.frombytes("RGB", shot.size, shot.rgb)
                    panels = self.detect_nameplate_regions_from_image(area_img)
                    if panels:
                        for slot_idx, panel in enumerate(panels):
                            scan_items.append((slot_idx, area_img.crop((panel.x, panel.y, panel.x + panel.w, panel.y + panel.h)), f"detected_panel@{panel.x},{panel.y}"))
                    elif self._name_area_full_fallback_allowed(area_img):
                        scan_items.append((0, area_img, "name_area_full"))
                    else:
                        results.append({"idx": 0, "source": "name_area_no_panel", "attempts": [], "best": None, "best_preset": "", "capture_error": None})
                else:
                    for idx, rel in enumerate(name_regions):
                        abs_rect = Rect(game_region.x + rel.x, game_region.y + rel.y, rel.w, rel.h)
                        monitor = {"left": abs_rect.x, "top": abs_rect.y, "width": abs_rect.w, "height": abs_rect.h}
                        shot = sct.grab(monitor)
                        img = Image.frombytes("RGB", shot.size, shot.rgb)
                        scan_items.append((idx, img, "precise"))

                for idx, img, source in scan_items:
                    attempts = []
                    best = None
                    best_preset = ""
                    try:
                        # Stream OCR attempts one-by-one and stop as soon as a
                        # Pokémon name is recognized. This keeps the live loop
                        # responsive and avoids doing many slow Tesseract calls.
                        for attempt in self.ocr.iter_text_attempts(img):
                            attempts.append(attempt)
                            if attempt.text:
                                match = self._match_auto_area_text(attempt.text, threshold, corrections, source) if auto_area_mode else self._match_ocr_text(attempt.text, threshold, corrections)
                                if match and auto_area_mode and not self._auto_area_match_allowed(match, attempt.text, corrections, idx, source):
                                    match = None
                                if match and (best is None or match.score > best.score):
                                    best = match
                                    best_preset = f"{source}/{attempt.preset}"
                                    if best.score >= threshold:
                                        break
                    except Exception as exc:
                        results.append({"idx": idx, "source": source, "capture_error": str(exc), "attempts": [], "best": None, "best_preset": ""})
                        continue

                    results.append({"idx": idx, "source": source, "attempts": attempts, "best": best, "best_preset": best_preset, "capture_error": None})
        except Exception as exc:
            worker_error = str(exc)

        self.scan_result_queue.put((scan_tick, results, worker_error))

    def finish_scan(self, scan_tick: int, results: list, worker_error: Optional[str]) -> None:
        # Ignore late results from abandoned workers. This is important after
        # Stop/Start or after the watchdog retries a hung OCR call.
        if scan_tick != self.active_scan_tick:
            return

        # Keep the scan/result processing self-contained. v21 accidentally
        # referenced this value without defining it in finish_scan(), which made
        # successful OCR results crash before they reached the card renderer.
        threshold = int(self.active_scan_threshold or int(float(self.threshold_var.get())))
        auto_area_mode = bool(self.active_scan_auto_area)
        corrections = dict(self.ocr_corrections)

        self.scan_worker_active = False
        self.active_scan_tick = 0
        self.last_scan_completed_at = time.monotonic()
        if not self.running:
            return

        if worker_error:
            self.scan_status_var.set("OCR error")
            self.status_var.set(f"Tracking paused after OCR error: {worker_error}")
            self.root.after(WAITING_SCAN_INTERVAL_MS, self.scan_once)
            return

        debug_lines: List[str] = []
        before_keys = tuple(sorted(self.current_keys.items()))
        seen_result_slots = set()
        current_scan_texts: Dict[int, List[str]] = {}

        for result in results:
            idx = result.get("idx", 0)
            seen_result_slots.add(idx)
            if result.get("capture_error"):
                debug_lines.append(f"Slot {idx + 1}: capture error: {result['capture_error']}")
                continue

            attempts = result.get("attempts") or []
            attempt_texts = [a.text for a in attempts if a.text]
            current_scan_texts[idx] = attempt_texts
            self.last_slot_attempt_texts[idx] = attempt_texts
            if attempt_texts:
                self.last_slot_raw_texts[idx] = attempt_texts[0]
            else:
                self.last_slot_raw_texts.pop(idx, None)

            best = result.get("best")
            best_preset = result.get("best_preset", "")
            if not best and attempts:
                # Final UI-side fallback. If the OCR worker captured usable text
                # but failed to pick a best match for any reason, run the same
                # repository matcher on each attempt and on the combined text in
                # the main thread. This restores the older simple path: OCR text
                # directly resolves to a Pokémon card.
                fallback_texts = [a.text for a in attempts if getattr(a, "text", "")]
                if fallback_texts:
                    fallback_texts.append(" ".join(fallback_texts[:3]))
                for raw_text in fallback_texts:
                    source_name = result.get("source", "")
                    candidate = self._match_auto_area_text(raw_text, threshold, corrections, source_name) if auto_area_mode else self._match_ocr_text(raw_text, threshold, corrections)
                    if candidate and auto_area_mode and not self._auto_area_match_allowed(candidate, raw_text, corrections, idx, source_name):
                        candidate = None
                    if candidate and (best is None or candidate.score > best.score):
                        best = candidate
                        best_preset = "ui_fallback"
            source_name = result.get("source", "")
            allowed = bool(best and ((best.score >= threshold) or auto_area_mode) and ((not auto_area_mode) or self._auto_area_match_allowed(best, best.raw_text, corrections, idx, source_name)))
            confirmed = bool(allowed and ((not auto_area_mode) or self._auto_slot_confirmed(idx, best, best.raw_text, corrections, source_name)))
            if confirmed:
                history = self.scan_histories.setdefault(idx, deque(maxlen=3))
                history.append(best.key)
                self.auto_slot_pending.pop(idx, None)
                self.slot_miss_counts[idx] = 0
                self.current_keys[idx] = self.apply_slot_form_override(idx, best.key)
                # Prefer showing the OCR text that actually matched, not the
                # first noisy OCR attempt. This makes the status/placeholder
                # reflect the same text that drove the card render.
                self.last_slot_raw_texts[idx] = best.raw_text
                self.last_slot_attempt_texts[idx] = [best.raw_text] + [v for v in self.last_slot_attempt_texts.get(idx, []) if v and v != best.raw_text]
                debug_lines.append(
                    f"Slot {idx + 1}: raw='{best.raw_text}' normalized='{best.normalized_text}' → {best.display_name} ({best.score:.1f}) via {best_preset}"
                )
            else:
                self.slot_miss_counts[idx] = self.slot_miss_counts.get(idx, 0) + 1
                if self.slot_miss_counts[idx] >= LOW_CONFIDENCE_CLEAR_SCANS and idx in self.current_keys:
                    self.current_keys.pop(idx, None)
                    self.slot_form_overrides.pop(idx, None)
                debug_text = "; ".join(f"{a.preset}:{a.text!r}" for a in attempts[:4]) or "no OCR text"
                source = result.get("source") or ("Name Area" if auto_area_mode else "Name")
                debug_lines.append(f"Slot {idx + 1}: waiting / no confident match from {source}. {debug_text}")

        # If dynamic Name Area detection no longer sees a previous auto slot,
        # clear it after a short debounce. This prevents a stale/flickering Slot
        # 2 card from hanging around when a single-battle screen only has one
        # detected nameplate.
        for stale_idx in list(self.current_keys.keys()):
            if stale_idx not in seen_result_slots:
                self.slot_miss_counts[stale_idx] = self.slot_miss_counts.get(stale_idx, 0) + 1
                if self.slot_miss_counts[stale_idx] >= LOW_CONFIDENCE_CLEAR_SCANS:
                    self.current_keys.pop(stale_idx, None)
                    self.slot_form_overrides.pop(stale_idx, None)
                    self.last_slot_attempt_texts.pop(stale_idx, None)
                    self.last_slot_raw_texts.pop(stale_idx, None)

        # Last-chance UI-side direct resolver: if any OCR string visibly
        # contains a Pokémon name, render the card even if the worker did not
        # choose a best match. This specifically protects cases like the UI
        # showing "Latest OCR: Slot 1: Heatmor" but no card.
        if not self.current_keys:
            for slot_idx, values in list(current_scan_texts.items()):
                for raw_text in values:
                    source_name = "ui_direct"
                    match = self._match_auto_area_text(raw_text, threshold, corrections, source_name) if auto_area_mode else self._match_ocr_text(raw_text, threshold, corrections)
                    if match and auto_area_mode and not self._auto_area_match_allowed(match, raw_text, corrections, slot_idx, source_name):
                        match = None
                    if match and match.score >= threshold:
                        self.slot_miss_counts[slot_idx] = 0
                        self.current_keys[slot_idx] = self.apply_slot_form_override(slot_idx, match.key)
                        debug_lines.append(
                            f"Slot {slot_idx + 1}: ui-direct raw='{match.raw_text}' → {match.display_name} ({match.score:.1f})"
                        )
                        break

        if self.current_keys:
            names = []
            for slot_idx, key in sorted(self.current_keys.items()):
                record = self.repo.pokemon.get(key, {})
                names.append(record.get("display_name") or key.replace("-", " ").title())
            self.scan_status_var.set("Detected: " + ", ".join(names[:2]))
        else:
            raw_bits = []
            for slot_idx in sorted(self.last_slot_attempt_texts):
                values = [v for v in self.last_slot_attempt_texts.get(slot_idx, []) if v]
                if values:
                    raw_bits.append(f"S{slot_idx + 1}: {values[0][:18]}")
            self.scan_status_var.set("Waiting for Pokémon" + ((" — " + " | ".join(raw_bits[:2])) if raw_bits else ""))

        after_keys = tuple(sorted(self.current_keys.items()))
        debug_signature = tuple(debug_lines)
        now = time.monotonic()

        should_render = after_keys != before_keys or after_keys != self.last_rendered_keys
        # When there is no confident match, refresh the placeholder occasionally
        # with the latest OCR text/error so it does not keep saying setup is
        # incomplete while the scanner is actually running.
        if not after_keys and debug_signature != self.last_debug_signature:
            if now - self.last_debug_render_time >= DEBUG_RENDER_INTERVAL_SEC:
                should_render = True
                self.last_debug_render_time = now
                self.last_debug_signature = debug_signature
        if self.show_debug.get() and debug_signature != self.last_debug_signature:
            if now - self.last_debug_render_time >= DEBUG_RENDER_INTERVAL_SEC:
                should_render = True
                self.last_debug_render_time = now
                self.last_debug_signature = debug_signature

        self.last_debug_lines = debug_lines
        if should_render:
            self.render_detected(debug_lines, preserve_scroll=True, force=True)

        if self.preview_visible.get() and scan_tick % PREVIEW_REFRESH_EVERY_SCANS == 0:
            self.update_preview()
        next_delay = SCAN_INTERVAL_MS if self.current_keys else WAITING_SCAN_INTERVAL_MS
        self.root.after(next_delay, self.scan_once)


    def apply_slot_form_override(self, slot_idx: int, matched_key: str) -> str:
        """Keep a manual form selected until the slot detects a different species."""
        override_key = self.slot_form_overrides.get(slot_idx)
        if not override_key:
            return matched_key
        if self.repo.same_species(override_key, matched_key):
            return override_key
        self.slot_form_overrides.pop(slot_idx, None)
        return matched_key

    def set_slot_form_override(self, slot_idx: int, selected_key: str) -> None:
        if selected_key not in self.repo.pokemon:
            return
        current_key = self.current_keys.get(slot_idx)
        if current_key and not self.repo.same_species(current_key, selected_key):
            messagebox.showinfo("Form override", "That form does not match the currently detected Pokémon species.")
            return

        species_key = self.repo.get_species_key(selected_key)
        if selected_key == species_key:
            self.slot_form_overrides.pop(slot_idx, None)
        else:
            self.slot_form_overrides[slot_idx] = selected_key
        self.current_keys[slot_idx] = selected_key
        record = self.repo.pokemon.get(selected_key, {}) or {}
        self.status_var.set(f"Slot {slot_idx + 1} form set to {record.get('display_name') or selected_key}.")
        self.last_rendered_keys = tuple()
        self.render_detected(self.last_debug_lines, preserve_scroll=True, force=True)

    def render_idle_message(self) -> None:
        self.clear_cards()
        placeholder = tk.Frame(self.card_container, bg=CARD_BG, padx=18, pady=18, highlightthickness=1, highlightbackground=BORDER)
        placeholder.grid(row=0, column=0, sticky="ew", padx=4, pady=4)
        self.card_container.columnconfigure(0, weight=1)

        has_setup = self.has_tracking_regions()
        if self.running and has_setup:
            title = "Waiting for Pokémon…"
            subtitle = "No confident name is visible in the selected name region yet. The card will appear as soon as a Pokémon name is read."
        elif has_setup:
            title = "Ready. Click Start to begin tracking."
            subtitle = "Game region and name region are set. Use Show Preview only if you need to tune the crop."
        elif self.game_region:
            title = "Game region set. Add a name region or Name Area next."
            subtitle = "Click Add Name for precise slots, or Name Area to scan a broader area containing opponent nameplates."
        else:
            title = "Idle. Select the game/window region to begin."
            subtitle = "Use Window Region for emulators where possible, then Add Name for the Pokémon name box."

        tk.Label(
            placeholder,
            text=title,
            bg=CARD_BG,
            fg=TEXT,
            font=("Segoe UI", 12, "bold"),
            anchor="w",
            wraplength=max(260, self.info_canvas.winfo_width() - 80),
            justify="left",
        ).pack(anchor="w", fill="x")
        tk.Label(
            placeholder,
            text=subtitle,
            bg=CARD_BG,
            fg=MUTED,
            font=("Segoe UI", 9),
            anchor="w",
            wraplength=max(260, self.info_canvas.winfo_width() - 80),
            justify="left",
        ).pack(anchor="w", fill="x", pady=(6, 0))

        if self.game_region:
            info = f"Game: {self.game_region.w}×{self.game_region.h} at {self.game_region.x},{self.game_region.y}"
            effective = self.effective_name_regions()
            if effective:
                label = "Name regions" if self.name_regions else "Name Area auto slots"
                info += f"  •  {label}: {len(effective)}"
            tk.Label(placeholder, text=info, bg=CARD_BG, fg=MUTED, font=("Segoe UI", 8), anchor="w").pack(anchor="w", fill="x", pady=(8, 0))

        raw_bits = []
        for slot_idx in sorted(self.last_slot_attempt_texts):
            values = [v for v in self.last_slot_attempt_texts.get(slot_idx, []) if v]
            if values:
                raw_bits.append(f"Slot {slot_idx + 1}: {values[0][:40]}")
        if raw_bits:
            tk.Label(
                placeholder,
                text="Latest OCR: " + " | ".join(raw_bits[:2]),
                bg=CARD_BG,
                fg=TEXT,
                font=("Consolas", 8),
                anchor="w",
                wraplength=max(260, self.info_canvas.winfo_width() - 80),
                justify="left",
            ).pack(anchor="w", fill="x", pady=(8, 0))
        elif self.running and has_setup:
            tk.Label(
                placeholder,
                text="Latest OCR: no readable text yet. Try a tighter crop around just the name, not the whole HP bar.",
                bg=CARD_BG,
                fg=MUTED,
                font=("Segoe UI", 8),
                anchor="w",
                wraplength=max(260, self.info_canvas.winfo_width() - 80),
                justify="left",
            ).pack(anchor="w", fill="x", pady=(8, 0))

    def render_detected(self, debug_lines: List[str], preserve_scroll: bool = True, force: bool = False) -> None:
        rendered_keys = tuple(sorted(self.current_keys.items()))
        if not force and rendered_keys == self.last_rendered_keys and not self.show_debug.get():
            return
        scroll_pos = self.info_canvas.yview()[0] if preserve_scroll else 0
        self.clear_cards()
        keys = [(idx, self.current_keys[idx]) for idx in sorted(self.current_keys)]
        if not keys:
            self.render_idle_message()
        else:
            self.reset_info_canvas_width()
            available_width = max(1, self.info_canvas.winfo_width())
            two_column_min = 640 if self.ultra_compact.get() else 760
            columns = 2 if len(keys) >= 2 and available_width >= two_column_min else 1
            for c in range(columns):
                self.card_container.columnconfigure(c, weight=1, uniform="battle_cards")
            for pos, (idx, key) in enumerate(keys):
                row = pos // columns
                col = pos % columns
                card = self.create_pokemon_card(self.card_container, idx, key, compact=(columns == 2))
                card.grid(row=row, column=col, sticky="new", padx=3, pady=3)

        if self.show_debug.get():
            debug = tk.Frame(self.card_container, bg=CARD_BG, padx=10, pady=8, highlightthickness=1, highlightbackground=BORDER)
            debug_width = max(1, self.info_canvas.winfo_width())
            debug_two_column_min = 640 if self.ultra_compact.get() else 760
            active_columns = 2 if len(keys) >= 2 and debug_width >= debug_two_column_min else 1
            next_row = (len(keys) + active_columns - 1) // active_columns + 1
            debug.grid(row=next_row, column=0, columnspan=active_columns, sticky="ew", padx=3, pady=(6, 3))
            tk.Label(debug, text="OCR Debug", bg=CARD_BG, fg=WHITE, font=("Segoe UI", 10, "bold")).pack(anchor="w")
            tk.Label(
                debug,
                text="\n".join(debug_lines) if debug_lines else "No debug output yet.",
                bg=CARD_BG,
                fg=MUTED,
                font=("Consolas", 8),
                justify="left",
                anchor="w",
                wraplength=max(320, self.info_canvas.winfo_width() - 80),
            ).pack(anchor="w", fill="x", pady=(4, 0))
        self.last_rendered_keys = rendered_keys
        if self.show_debug.get():
            self.last_debug_signature = tuple(debug_lines)
            self.last_debug_render_time = time.monotonic()
        self.card_container.update_idletasks()
        self.info_canvas.configure(scrollregion=self.info_canvas.bbox("all"))
        if preserve_scroll:
            self.info_canvas.yview_moveto(scroll_pos)
        else:
            self.info_canvas.yview_moveto(0)

    def card_layout_metrics(self, compact: bool = False, dense: bool = False) -> dict:
        """Return discrete card sizing values for the current information pane."""
        columns = 2 if compact else 1
        pane_width = max(1, self.info_canvas.winfo_width())
        card_width = max(220, pane_width // columns)
        if dense:
            tier = 3 if card_width >= 700 else (2 if card_width >= 560 else (1 if card_width >= 430 else 0))
            title_font = [14, 15, 17, 19][tier]
            section_font = [9, 10, 12, 13][tier]
            body_font = [8, 9, 10, 11][tier]
            chip_font = [9, 10, 11, 12][tier]
            chip_padx = [6, 7, 9, 10][tier]
            card_pad = [8, 10, 13, 16][tier]
            label_width = [8, 8, 9, 10][tier]
            label_space = [64, 70, 82, 94][tier]
            chip_estimate = [52, 58, 68, 78][tier]
        else:
            tier = 3 if card_width >= 760 else (2 if card_width >= 620 else (1 if card_width >= 460 else 0))
            title_font = [12 if compact else 13, 15, 17, 19][tier]
            section_font = [10, 11, 13, 14][tier]
            body_font = [8, 9, 10, 11][tier]
            chip_font = [8, 9, 11, 12][tier]
            chip_padx = [6, 7, 9, 10][tier]
            card_pad = [8, 10, 14, 18][tier]
            label_width = [9, 10, 11, 12][tier]
            label_space = [90, 102, 124, 142][tier]
            chip_estimate = [64, 70, 84, 96][tier]
        return {
            "card_width": card_width,
            "wrap": max(190 if dense else 260, card_width - (40 if dense else 64)),
            "card_pad": card_pad,
            "title_font": title_font,
            "section_font": section_font,
            "body_font": body_font,
            "stat_font": body_font + 1,
            "chip_font": chip_font,
            "chip_padx": chip_padx,
            "chip_pady": 2 if tier < 2 else (3 if tier == 2 else 4),
            "effect_label_width": label_width,
            "effect_label_space": label_space,
            "chip_estimate": chip_estimate,
            "tier": tier,
        }

    def create_pokemon_card(self, parent: tk.Widget, slot_idx: int, key: str, compact: bool = False) -> tk.Frame:
        summary = self.repo.get_battle_summary(key)
        ultra = self.ultra_compact.get()
        # Docking hides controls, but only the explicit Ultra compact option
        # should switch the card into the stripped-down battle glance view.
        dense = bool(ultra)
        metrics = self.card_layout_metrics(compact=compact, dense=dense)
        wrap = metrics["wrap"]

        card = tk.Frame(parent, bg=CARD_BG, padx=metrics["card_pad"], pady=metrics["card_pad"], highlightthickness=1, highlightbackground=BORDER)
        header = tk.Frame(card, bg=CARD_BG)
        header.pack(fill="x")

        # The slot label used useful vertical space but did not add much once the
        # card is already grouped by detected Pokémon. Keep only the Pokémon name
        # and optional form selector.
        title_row = tk.Frame(header, bg=CARD_BG)
        title_row.pack(anchor="w", fill="x")
        tk.Label(
            title_row,
            text=summary.get("display_name", key),
            bg=CARD_BG,
            fg=WHITE,
            font=("Segoe UI", metrics["title_font"], "bold"),
            anchor="w",
        ).pack(side="left", anchor="w", fill="x", expand=True)
        self.add_form_selector(title_row, slot_idx, key, compact=True if dense or compact else False, metrics=metrics)

        types_frame = tk.Frame(card, bg=CARD_BG)
        types_frame.pack(anchor="w", fill="x", pady=(2, 3 if dense else 6 + metrics["tier"]))
        for type_name in summary.get("types", []) or ["none"]:
            self.add_type_chip(types_frame, str(type_name), padx=(0, 4), pady=(1, 1), compact=dense, metrics=metrics)

        if dense:
            stats = summary.get("stats", {}) or {}
            speed = stats.get("speed")
            if speed not in (None, "", "—"):
                tk.Label(card, text=f"Speed: {speed}", bg=CARD_BG, fg=MUTED, font=("Segoe UI", metrics["section_font"], "bold"), anchor="w").pack(anchor="w", pady=(0, 3))
            # Ultra compact skips collapsed Base Stats / Abilities headers so
            # the highest-value battle information stays immediately visible.
            self.add_effectiveness_content(card, summary.get("effectiveness", {}), wrap, dense=True, metrics=metrics)
        else:
            self.add_separator(card)
            self.add_collapsible_section(card, "Base Stats", "stats", lambda body: self.add_stats_content(body, summary.get("stats", {}), wrap, metrics=metrics), metrics=metrics)
            self.add_separator(card)
            self.add_collapsible_section(card, "Type Effectiveness", "effectiveness", lambda body: self.add_effectiveness_content(body, summary.get("effectiveness", {}), wrap, metrics=metrics), metrics=metrics)
            self.add_separator(card)
            self.add_collapsible_section(card, "Abilities", "abilities", lambda body: self.add_abilities_content(body, summary.get("abilities", []), wrap, metrics=metrics), metrics=metrics)
        return card


    def add_form_selector(self, parent: tk.Widget, slot_idx: int, key: str, compact: bool = False, metrics: Optional[dict] = None) -> None:
        options = self.repo.get_form_options(key)
        if not options:
            return
        metrics = metrics or self.card_layout_metrics(compact=compact, dense=compact)

        current_display = None
        for opt in options:
            if opt["key"] == key:
                current_display = opt["display_name"]
                break
        if not current_display:
            record = self.repo.pokemon.get(key, {}) or {}
            current_display = record.get("display_name") or key.replace("-", " ").title()

        button_text = "Form ▾" if compact else f"Form: {current_display} ▾"
        form_font = max(8, metrics["body_font"] + (1 if compact else 0))
        btn = tk.Menubutton(
            parent,
            text=button_text,
            bg=CARD_BG_ALT,
            fg=TEXT,
            activebackground=BORDER,
            activeforeground=WHITE,
            relief="flat",
            bd=0,
            font=("Segoe UI", form_font, "bold"),
            padx=max(6, metrics["chip_padx"]),
            pady=2 if metrics["tier"] < 3 else 3,
            cursor="hand2",
        )
        menu = tk.Menu(btn, tearoff=0, bg=CARD_BG, fg=TEXT, activebackground=BLUE, activeforeground=WHITE)
        for opt in options:
            type_text = "/".join(str(t).title() for t in opt.get("types", []))
            label = opt["display_name"] + (f"  ({type_text})" if type_text else "")
            if opt["key"] == key:
                label = "✓ " + label
            menu.add_command(label=label, command=lambda form_key=opt["key"]: self.set_slot_form_override(slot_idx, form_key))
        btn.configure(menu=menu)
        btn.pack(side="left", anchor="w", padx=(6, 0))

        if self.slot_form_overrides.get(slot_idx):
            tk.Label(parent, text="manual", bg=CARD_BG, fg=YELLOW, font=("Segoe UI", max(8, metrics["body_font"]), "bold")).pack(side="left", padx=(5, 0))

    def add_separator(self, parent: tk.Widget) -> None:
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", pady=8)

    def add_collapsible_section(self, parent: tk.Widget, title: str, state_key: str, build_content, compact_header: bool = False, metrics: Optional[dict] = None) -> None:
        collapsed = self.section_collapsed[state_key].get()
        section_font = metrics.get("section_font", 9 if compact_header else 10) if metrics else (9 if compact_header else 10)
        section = tk.Frame(parent, bg=CARD_BG)
        section.pack(fill="x")
        arrow = "▸" if collapsed else "▾"
        header = tk.Button(
            section,
            text=f"{arrow} {title}",
            command=lambda: self.toggle_info_section(state_key),
            bg=CARD_BG,
            fg=WHITE,
            activebackground=CARD_BG_ALT,
            activeforeground=WHITE,
            font=("Segoe UI", section_font, "bold"),
            anchor="w",
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=0,
            pady=0,
            cursor="hand2",
        )
        header.pack(anchor="w", fill="x")
        if collapsed:
            return
        body = tk.Frame(section, bg=CARD_BG)
        body.pack(fill="x", pady=(3 if compact_header else 5, 0))
        build_content(body)

    def toggle_info_section(self, state_key: str) -> None:
        if state_key not in self.section_collapsed:
            return
        self.section_collapsed[state_key].set(not self.section_collapsed[state_key].get())
        self.last_rendered_keys = tuple()
        self.render_detected(self.last_debug_lines, preserve_scroll=True, force=True)

    def add_stats_content(self, parent: tk.Widget, stats: dict, wrap: int, metrics: Optional[dict] = None) -> None:
        font_size = metrics.get("stat_font", 9) if metrics else 9
        table = tk.Frame(parent, bg=CARD_BG)
        table.pack(fill="x")
        # Two columns of stats in the official order: HP, Atk, Def, SpA, SpD, Speed, Total.
        for i, (key, label) in enumerate(STAT_ROWS):
            row = i // 2
            col = (i % 2) * 2
            tk.Label(table, text=label, bg=CARD_BG, fg=MUTED, font=("Segoe UI", font_size, "bold"), anchor="w").grid(row=row, column=col, sticky="w", padx=(0, 6), pady=2)
            tk.Label(table, text=str(stats.get(key, "—")), bg=CARD_BG, fg=TEXT, font=("Segoe UI", font_size), anchor="w").grid(row=row, column=col + 1, sticky="w", padx=(0, 16), pady=2)
        table.columnconfigure(1, weight=1)
        table.columnconfigure(3, weight=1)

    def add_effectiveness_content(self, parent: tk.Widget, effectiveness: dict, wrap: int, dense: bool = False, metrics: Optional[dict] = None) -> None:
        metrics = metrics or self.card_layout_metrics(compact=False, dense=dense)
        has_rows = False
        for field, label in EFFECTIVENESS_ROWS:
            values = effectiveness.get(field) or []
            if not values:
                continue
            has_rows = True
            row = tk.Frame(parent, bg=CARD_BG)
            row.pack(fill="x", anchor="w", pady=1 if dense else 2)
            tk.Label(
                row,
                text=label,
                bg=CARD_BG,
                fg=TEXT,
                font=("Segoe UI", metrics["section_font"] if dense else metrics["body_font"], "bold"),
                width=metrics["effect_label_width"],
                anchor="nw",
            ).pack(side="left", anchor="n")
            chips = tk.Frame(row, bg=CARD_BG)
            chips.pack(side="left", fill="x", expand=True, anchor="w")
            self.add_wrapped_type_chips(chips, [str(t) for t in values], dense=dense, metrics=metrics)
        if not has_rows:
            tk.Label(parent, text="No effectiveness data found.", bg=CARD_BG, fg=MUTED, font=("Segoe UI", metrics["body_font"])).pack(anchor="w")

    def add_wrapped_type_chips(self, parent: tk.Widget, values: List[str], dense: bool = False, metrics: Optional[dict] = None) -> None:
        metrics = metrics or self.card_layout_metrics(compact=False, dense=dense)
        # Narrow docked windows used to clip long rows such as Flying/Poison/Bug/Fire/Ice.
        # Wrap chips by count so the card can stay thin without hiding battle info.
        canvas_width = max(220, metrics["card_width"])
        label_space = metrics["effect_label_space"]
        usable = max(110, canvas_width - label_space)
        chip_estimate = metrics["chip_estimate"]
        max_per_row = max(2, min(7, usable // chip_estimate))
        row = None
        for i, type_name in enumerate(values):
            if i % max_per_row == 0:
                row = tk.Frame(parent, bg=CARD_BG)
                row.pack(anchor="w", fill="x")
            self.add_type_chip(row or parent, type_name, padx=(0, 4), pady=(0, 3 if dense else 4), compact=dense, metrics=metrics)


    def add_abilities_content(self, parent: tk.Widget, abilities: list, wrap: int, metrics: Optional[dict] = None) -> None:
        metrics = metrics or self.card_layout_metrics(compact=False, dense=False)
        if not abilities:
            tk.Label(parent, text="Not found in local profile-detail cache.", bg=CARD_BG, fg=MUTED, font=("Segoe UI", metrics["body_font"])).pack(anchor="w")
            return
        for ability in abilities:
            hidden = " (Hidden)" if ability.get("is_hidden") else ""
            name = ability.get("name", "Unknown")
            effect = ability.get("effect") or ability.get("flavor_text") or ""
            tk.Label(parent, text=f"{name}{hidden}", bg=CARD_BG, fg=WHITE, font=("Segoe UI", metrics["stat_font"], "bold"), anchor="w").pack(anchor="w", fill="x", pady=(2, 0))
            if effect:
                tk.Label(parent, text=effect, bg=CARD_BG, fg=TEXT, font=("Segoe UI", metrics["body_font"]), justify="left", wraplength=wrap, anchor="w").pack(anchor="w", fill="x", pady=(0, 4))

    def add_type_chip(self, parent: tk.Widget, type_name: str, padx=(0, 4), pady=(0, 0), compact: bool = False, metrics: Optional[dict] = None) -> None:
        metrics = metrics or self.card_layout_metrics(compact=False, dense=compact)
        t = (type_name or "none").lower()
        fg = "#111827" if t in {"electric", "ice", "ground", "steel", "fairy", "normal"} else WHITE
        chip = tk.Label(
            parent,
            text=t.title(),
            bg=TYPE_COLORS.get(t, TYPE_COLORS["none"]),
            fg=fg,
            font=("Segoe UI", metrics["chip_font"], "bold"),
            padx=metrics["chip_padx"],
            pady=metrics["chip_pady"],
        )
        chip.pack(side="left", padx=padx, pady=pady)


    def open_setup_wizard(self) -> None:
        """Backward-compatible name for older buttons/profiles; now opens the inline setup tour."""
        self.start_setup_tour()

    def start_setup_tour(self) -> None:
        """Inline first-run guided setup using one stationary callout."""
        if self.setup_tour_window and self.setup_tour_window.winfo_exists():
            self.setup_tour_window.lift()
            self.position_setup_callout()
            self.schedule_setup_auto_advance()
            return
        if not self.controls_visible.get():
            self.toggle_controls_panel()
        self.setup_tour_index = 0
        self.setup_tour_fixed_geometry = None
        self.setup_steps = self.build_setup_steps()
        self.render_setup_callout()
        self.schedule_setup_auto_advance()

    def build_setup_steps(self) -> List[dict]:
        return [
            {
                "target": self.window_region_button,
                "title": "1. Attach to the game window",
                "body": "Open your emulator or fan game, then use Window Region. This sets the full game window bounds. Game Region is a manual fallback.",
                "action_label": "Choose Window",
                "action": self.select_game_window_region,
                "complete": lambda: self.game_region is not None,
            },
            {
                "target": self.add_name_button,
                "title": "2. Mark the Pokémon name box",
                "body": "Click Add Name for a tight enemy-name crop, or use Name Area for one broad area containing possible opponent nameplates. Either one is enough to start.",
                "action_label": "Add Name Region",
                "action": self.add_name_region,
                "complete": self.has_any_name_tracking_region,
            },
            {
                "target": self.preview_toggle_button,
                "title": "3. Check the preview",
                "body": "Show Preview to confirm the red box covers the name text/nameplate. The tour advances after the preview has been shown once.",
                "action_label": "Show Preview",
                "action": self.ensure_preview_visible,
                "complete": lambda: bool(self.preview_visible.get()),
            },
            {
                "target": self.ultra_compact_check,
                "title": "4. Pick compact options",
                "body": "Use Recommended enables Dock on Start, Ultra compact, and Auto window region when a window is attached.",
                "action_label": "Use Recommended",
                "action": self.apply_recommended_setup_options,
                "complete": lambda: bool(self.dock_on_start.get() and self.ultra_compact.get()),
            },
            {
                "target": self.dock_select_frame,
                "title": "5. Choose and test docking",
                "body": "Select Left, Right, Above, or Below, then use Dock Now to test the position. The monitor should not overlap the game region.",
                "action_label": "Dock Now",
                "action": lambda: self.dock_to_game_region(self.dock_position.get()),
                "complete": lambda: self.last_docked_time > 0,
            },
            {
                "target": self.save_profile_button,
                "title": "6. Save the setup",
                "body": "Save stores the game/window region, name regions, dock direction, compact mode, and collapsed sections.",
                "action_label": "Save Profile",
                "action": self.save_profile_dialog,
                "complete": lambda: self.last_profile_save_time > 0,
            },
            {
                "target": self.start_button,
                "title": "7. Start tracking",
                "body": "Start begins OCR tracking. Once OCR reads a Pokémon name, the battle card appears and only refreshes when the detection changes.",
                "action_label": "Start",
                "action": self.start_tracking,
                "finish_label": "Finish Tour",
                "complete": lambda: bool(self.running),
            },
        ]

    def is_auto_name_region(self, region: Rect) -> bool:
        if not self.game_region:
            return False
        auto = Rect(0, 0, self.game_region.w // 2, self.game_region.h // 2)
        return region == auto

    def has_precise_name_regions(self) -> bool:
        if not self.game_region or not self.name_regions:
            return False
        return any(not self.is_auto_name_region(r) for r in self.name_regions)

    def has_any_name_tracking_region(self) -> bool:
        return self.has_tracking_regions()

    def setup_status_summary(self) -> str:
        region = "game region ready" if self.game_region else "no game region yet"
        effective = self.effective_name_regions()
        if self.name_regions:
            names = f"{len(self.name_regions)} precise name region(s)"
        elif self.name_scan_area:
            names = f"name area → {len(effective)} auto slot(s)"
        else:
            names = "no name regions yet"
        ocr = "OCR ready" if self.ocr.available else "OCR not ready"
        return f"Status: {region} • {names} • {ocr}"

    def ensure_preview_visible(self) -> None:
        if not self.preview_visible.get():
            self.toggle_preview()
        else:
            self.update_preview(force=True)

    def apply_recommended_setup_options(self) -> None:
        self.dock_on_start.set(True)
        self.ultra_compact.set(True)
        self.auto_window_region.set(bool(self.window_match_text))
        self.section_collapsed["stats"].set(True)
        self.section_collapsed["abilities"].set(True)
        self.on_compact_option_changed()
        self.status_var.set("Recommended compact options enabled.")

    def render_setup_callout(self) -> None:
        if not self.setup_steps:
            self.setup_steps = self.build_setup_steps()
        step = self.setup_steps[self.setup_tour_index]

        if self.setup_tour_window and self.setup_tour_window.winfo_exists():
            win = self.setup_tour_window
            # If the user dragged the callout, keep that new position when the
            # step changes instead of snapping back to the original anchor.
            try:
                self.setup_tour_fixed_geometry = (win.winfo_x(), win.winfo_y())
            except Exception:
                pass
            for child in win.winfo_children():
                child.destroy()
        else:
            win = tk.Toplevel(self.root)
            self.setup_tour_window = win
            win.title("Guided Setup")
            win.configure(bg=BLUE)
            win.resizable(False, False)
            win.protocol("WM_DELETE_WINDOW", self.close_setup_tour)
            win.bind("<Configure>", lambda _event: self.remember_setup_callout_position())

        outer = tk.Frame(win, bg=BLUE, padx=2, pady=2)
        outer.pack(fill="both", expand=True)
        card = tk.Frame(outer, bg=CARD_BG, padx=12, pady=10)
        card.pack(fill="both", expand=True)

        top = tk.Frame(card, bg=CARD_BG)
        top.pack(fill="x")
        tk.Label(top, text=step["title"], bg=CARD_BG, fg=WHITE, font=("Segoe UI", 11, "bold"), anchor="w").pack(side="left", fill="x", expand=True)
        tk.Label(top, text=f"{self.setup_tour_index + 1}/{len(self.setup_steps)}", bg=CARD_BG, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(side="right")

        tk.Label(
            card,
            text=step["body"],
            bg=CARD_BG,
            fg=TEXT,
            font=("Segoe UI", 9),
            wraplength=315,
            justify="left",
            anchor="w",
        ).pack(fill="x", pady=(8, 8))

        status_text = self.setup_status_summary()
        if self.current_setup_step_complete():
            status_text += "\n✓ This step is complete. Moving on…"
        tk.Label(
            card,
            text=status_text,
            bg=CARD_BG,
            fg=MUTED,
            font=("Segoe UI", 8),
            wraplength=315,
            justify="left",
            anchor="w",
        ).pack(fill="x", pady=(0, 8))

        buttons = tk.Frame(card, bg=CARD_BG)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Back", command=self.previous_setup_step).pack(side="left")
        ttk.Button(buttons, text="Skip", command=self.skip_setup_tour).pack(side="left", padx=(6, 0))
        ttk.Button(buttons, text=step.get("action_label", "Do This"), command=lambda: self.run_setup_action(step)).pack(side="right", padx=(6, 0))
        ttk.Button(buttons, text=step.get("finish_label", "Next"), command=self.next_setup_step).pack(side="right")

        self.root.after(50, self.position_setup_callout)

    def remember_setup_callout_position(self) -> None:
        win = self.setup_tour_window
        if not win or not win.winfo_exists():
            return
        try:
            self.setup_tour_fixed_geometry = (win.winfo_x(), win.winfo_y())
        except Exception:
            pass

    def position_setup_callout(self) -> None:
        """Place the setup callout once and keep it there across steps."""
        win = self.setup_tour_window
        if not win or not win.winfo_exists():
            return
        try:
            win.update_idletasks()
            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()
            tw = max(350, win.winfo_reqwidth())
            th = max(180, win.winfo_reqheight())
            if self.setup_tour_fixed_geometry:
                x, y = self.setup_tour_fixed_geometry
            else:
                self.root.update_idletasks()
                root_x = self.root.winfo_rootx()
                root_y = self.root.winfo_rooty()
                controls_w = self.controls_frame.winfo_width() if self.controls_visible.get() else 0
                # Start beside the left controls panel when possible. If that would
                # leave the screen, fall back to a stable top-left position inside
                # the monitor window. Do not move again when the step changes.
                x = root_x + controls_w + 12
                y = root_y + 62
                if x + tw > screen_w - 10:
                    x = root_x + 18
                    y = root_y + 74
                x = max(10, min(int(x), max(10, screen_w - tw - 10)))
                y = max(10, min(int(y), max(10, screen_h - th - 45)))
                self.setup_tour_fixed_geometry = (x, y)
            win.geometry(f"{tw}x{th}+{int(x)}+{int(y)}")
        except tk.TclError:
            pass

    def current_setup_step_complete(self) -> bool:
        if not self.setup_steps or self.setup_tour_index >= len(self.setup_steps):
            return False
        check = self.setup_steps[self.setup_tour_index].get("complete")
        if not check:
            return False
        try:
            return bool(check())
        except Exception:
            return False

    def schedule_setup_auto_advance(self) -> None:
        if self.setup_auto_advance_job:
            try:
                self.root.after_cancel(self.setup_auto_advance_job)
            except Exception:
                pass
        self.setup_auto_advance_job = self.root.after(650, self.check_setup_tour_auto_advance)

    def check_setup_tour_auto_advance(self) -> None:
        self.setup_auto_advance_job = None
        if not self.setup_tour_window or not self.setup_tour_window.winfo_exists():
            return
        if self.current_setup_step_complete():
            # Give the user a brief moment to see the completion state, then move.
            self.root.after(350, self.next_setup_step)
            return
        # Refresh the status line without changing the callout position.
        try:
            self.render_setup_callout()
        except tk.TclError:
            return
        self.schedule_setup_auto_advance()

    def run_setup_action(self, step: dict) -> None:
        action = step.get("action")
        if not action:
            return
        win = self.setup_tour_window
        try:
            if win and win.winfo_exists():
                win.withdraw()
            action()
        finally:
            try:
                if win and win.winfo_exists():
                    win.deiconify()
                    self.render_setup_callout()
                    self.schedule_setup_auto_advance()
            except tk.TclError:
                pass

    def next_setup_step(self) -> None:
        if not self.setup_tour_window or not self.setup_tour_window.winfo_exists():
            return
        if self.setup_tour_index >= len(self.setup_steps) - 1:
            self.finish_setup_tour()
            return
        self.setup_tour_index += 1
        self.render_setup_callout()
        self.schedule_setup_auto_advance()

    def previous_setup_step(self) -> None:
        if self.setup_tour_index > 0:
            self.setup_tour_index -= 1
            self.render_setup_callout()
            self.schedule_setup_auto_advance()

    def finish_setup_tour(self) -> None:
        self.config["first_run_complete"] = True
        self.save_config()
        self.close_setup_tour(mark_complete=False)
        self.status_var.set("Guided setup complete. Save your profile if you changed regions or docking.")

    def skip_setup_tour(self) -> None:
        self.config["first_run_complete"] = True
        self.save_config()
        self.close_setup_tour(mark_complete=False)
        self.status_var.set("Guided setup skipped. Use Guided Setup any time to reopen it.")

    def close_setup_tour(self, mark_complete: bool = False) -> None:
        if self.setup_auto_advance_job:
            try:
                self.root.after_cancel(self.setup_auto_advance_job)
            except Exception:
                pass
            self.setup_auto_advance_job = None
        if mark_complete:
            self.config["first_run_complete"] = True
            self.save_config()
        if self.setup_tour_window and self.setup_tour_window.winfo_exists():
            self.setup_tour_window.destroy()
        self.setup_tour_window = None
        self.setup_tour_fixed_geometry = None

    def add_ocr_fix_dialog(self) -> None:
        recent_items = []
        for slot, texts in sorted(self.last_slot_attempt_texts.items()):
            for text in texts[:3]:
                if text and text not in [item[1] for item in recent_items]:
                    recent_items.append((slot + 1, text))
        default_raw = recent_items[0][1] if recent_items else ""

        dialog = tk.Toplevel(self.root)
        dialog.title("Add OCR correction")
        dialog.configure(bg=PAGE_BG)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)

        tk.Label(dialog, text="Teach the monitor a bad OCR read", bg=PAGE_BG, fg=WHITE, font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 4))
        tk.Label(dialog, text="Example: map LURANT1S or Lurantls to Lurantis. Corrections apply before fuzzy matching.", bg=PAGE_BG, fg=MUTED, font=("Segoe UI", 8), wraplength=440, justify="left").grid(row=1, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 10))

        tk.Label(dialog, text="OCR text", bg=PAGE_BG, fg=TEXT, font=("Segoe UI", 9)).grid(row=2, column=0, sticky="w", padx=12, pady=4)
        raw_var = tk.StringVar(value=default_raw)
        raw_entry = ttk.Entry(dialog, textvariable=raw_var, width=44)
        raw_entry.grid(row=2, column=1, sticky="ew", padx=12, pady=4)

        tk.Label(dialog, text="Correct Pokémon", bg=PAGE_BG, fg=TEXT, font=("Segoe UI", 9)).grid(row=3, column=0, sticky="w", padx=12, pady=4)
        correct_var = tk.StringVar()
        correct_entry = ttk.Entry(dialog, textvariable=correct_var, width=44)
        correct_entry.grid(row=3, column=1, sticky="ew", padx=12, pady=4)

        if recent_items:
            tk.Label(dialog, text="Recent OCR reads", bg=PAGE_BG, fg=MUTED, font=("Segoe UI", 8)).grid(row=4, column=0, sticky="nw", padx=12, pady=(8, 2))
            recent_box = tk.Listbox(dialog, width=44, height=min(5, len(recent_items)), bg=CARD_BG, fg=TEXT, selectbackground=BLUE, activestyle="none")
            recent_box.grid(row=4, column=1, sticky="ew", padx=12, pady=(8, 2))
            for slot, text in recent_items:
                recent_box.insert("end", f"Slot {slot}: {text}")
            def use_recent(_event=None):
                sel = recent_box.curselection()
                if sel:
                    raw_var.set(recent_items[sel[0]][1])
            recent_box.bind("<<ListboxSelect>>", use_recent)

        result_label = tk.Label(dialog, text="", bg=PAGE_BG, fg=MUTED, font=("Segoe UI", 8), wraplength=440, justify="left")
        result_label.grid(row=5, column=0, columnspan=2, sticky="w", padx=12, pady=(6, 0))

        def save_fix() -> None:
            raw = raw_var.get().strip()
            correct = correct_var.get().strip()
            if not raw or not correct:
                result_label.configure(text="Enter both the OCR text and the correct Pokémon name.", fg=YELLOW)
                return
            match = self.repo.match_name(correct, min_score=0)
            if not match:
                result_label.configure(text="Could not find that Pokémon in the local repository.", fg=RED)
                return
            normalized = normalize_name(raw)
            self.ocr_corrections[normalized] = match.key
            self.save_ocr_corrections()
            result_label.configure(text=f"Saved: {normalized} → {match.display_name}", fg=GREEN)
            self.status_var.set(f"OCR correction saved: {normalized} → {match.display_name}")

        buttons = tk.Frame(dialog, bg=PAGE_BG)
        buttons.grid(row=6, column=0, columnspan=2, sticky="ew", padx=12, pady=12)
        ttk.Button(buttons, text="Save", command=save_fix).pack(side="right", padx=(6, 0))
        ttk.Button(buttons, text="Close", command=dialog.destroy).pack(side="right")
        raw_entry.focus_set()
        dialog.bind("<Return>", lambda _event: save_fix())
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        dialog.wait_window()

    def profile_payload(self) -> dict:
        return {
            "game_region": self.game_region.to_dict() if self.game_region else None,
            "name_regions": [r.to_dict() for r in self.name_regions],
            "name_scan_area": self.name_scan_area.to_dict() if self.name_scan_area else None,
            "threshold": int(float(self.threshold_var.get())),
            "preview_visible": bool(self.preview_visible.get()),
            "controls_visible": bool(self.controls_visible.get()),
            "dock_on_start": bool(self.dock_on_start.get()),
            "dock_position": self.dock_position.get(),
            "ultra_compact": bool(self.ultra_compact.get()),
            "auto_window_region": bool(self.auto_window_region.get()),
            "attached_window_title": self.attached_window_title,
            "window_match_text": self.window_match_text,
            "section_collapsed": {key: bool(var.get()) for key, var in self.section_collapsed.items()},
        }

    def apply_profile_payload(self, payload: dict) -> None:
        game = payload.get("game_region")
        self.game_region = Rect.from_dict(game) if game else None
        self.name_regions = [Rect.from_dict(r) for r in payload.get("name_regions", [])]
        area = payload.get("name_scan_area")
        self.name_scan_area = Rect.from_dict(area) if area else None
        if payload.get("threshold"):
            self.threshold_var.set(int(payload["threshold"]))
        if "dock_on_start" in payload:
            self.dock_on_start.set(bool(payload.get("dock_on_start")))
        if payload.get("dock_position") in {"left", "right", "above", "below"}:
            self.dock_position.set(payload.get("dock_position"))
        if "ultra_compact" in payload:
            self.ultra_compact.set(bool(payload.get("ultra_compact")))
        if "auto_window_region" in payload:
            self.auto_window_region.set(bool(payload.get("auto_window_region")))
        self.attached_window_title = payload.get("attached_window_title", "") or ""
        self.window_match_text = payload.get("window_match_text", "") or ""
        for key, value in (payload.get("section_collapsed") or {}).items():
            if key in self.section_collapsed:
                self.section_collapsed[key].set(bool(value))
        target_controls_visible = payload.get("controls_visible")
        if target_controls_visible is not None and bool(target_controls_visible) != self.controls_visible.get():
            self.toggle_controls_panel()
        self.current_keys.clear()
        self.slot_form_overrides.clear()
        self.scan_histories.clear()
        self.slot_miss_counts.clear()
        self.auto_slot_pending.clear()
        self.last_rendered_keys = tuple()
        if payload.get("preview_visible"):
            if not self.preview_visible.get():
                self.toggle_preview()
        else:
            if self.preview_visible.get():
                self.toggle_preview()
        self.update_preview()
        self.render_detected(self.last_debug_lines, force=True)

    def save_profile(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.profile_payload(), indent=2), encoding="utf-8")
        self.last_profile_save_time = time.monotonic()
        self.status_var.set(f"Profile saved: {path.name}")

    def load_profile(self, path: Path, silent: bool = False) -> None:
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.apply_profile_payload(payload)
        self.status_var.set(f"Profile loaded: {path.name}")
        if not silent:
            messagebox.showinfo("Profile loaded", f"Loaded {path.name}")

    def save_profile_dialog(self) -> None:
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        name = simpledialog.askstring("Save profile", "Profile name:", parent=self.root, initialvalue="default")
        if not name:
            return
        path = PROFILE_DIR / profile_filename(name)
        if path.exists() and not messagebox.askyesno("Overwrite profile?", f"{path.name} already exists. Overwrite it?"):
            return
        self.save_profile(path)

    def load_profile_dialog(self) -> None:
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        profiles = sorted(PROFILE_DIR.glob("*.json"), key=lambda p: p.name.lower())
        if not profiles:
            messagebox.showinfo("No profiles", f"No saved profiles found in {PROFILE_DIR}")
            return
        selected = self.select_profile_from_app_folder(profiles)
        if selected:
            self.load_profile(selected)

    def select_profile_from_app_folder(self, profiles: List[Path]) -> Optional[Path]:
        dialog = tk.Toplevel(self.root)
        dialog.title("Load profile")
        dialog.configure(bg=PAGE_BG)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)

        tk.Label(dialog, text="Select a saved profile", bg=PAGE_BG, fg=WHITE, font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=12, pady=(12, 6))
        tk.Label(dialog, text=str(PROFILE_DIR), bg=PAGE_BG, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", padx=12, pady=(0, 6))

        listbox = tk.Listbox(dialog, width=42, height=min(12, max(4, len(profiles))), bg=CARD_BG, fg=TEXT, selectbackground=BLUE, activestyle="none")
        listbox.pack(fill="both", padx=12, pady=6)
        for p in profiles:
            listbox.insert("end", p.stem)
        listbox.selection_set(0)

        result = {"path": None}

        def choose(_event=None):
            selection = listbox.curselection()
            if selection:
                result["path"] = profiles[selection[0]]
            dialog.destroy()

        def cancel():
            result["path"] = None
            dialog.destroy()

        buttons = tk.Frame(dialog, bg=PAGE_BG)
        buttons.pack(fill="x", padx=12, pady=(4, 12))
        ttk.Button(buttons, text="Load", command=choose).pack(side="right", padx=(6, 0))
        ttk.Button(buttons, text="Cancel", command=cancel).pack(side="right")
        listbox.bind("<Double-Button-1>", choose)
        dialog.bind("<Return>", choose)
        dialog.bind("<Escape>", lambda _event: cancel())
        dialog.wait_window()
        return result["path"]


def _startup_error_log_path() -> Path:
    try:
        USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
        return USER_DATA_DIR / "startup_error.log"
    except Exception:
        return Path.cwd() / "startup_error.log"


def main() -> None:
    try:
        root = tk.Tk()
        app = BattleMonitorApp(root)
        root.protocol("WM_DELETE_WINDOW", root.destroy)
        root.mainloop()
    except BaseException as exc:
        import traceback
        log_path = _startup_error_log_path()
        details = traceback.format_exc()
        try:
            log_path.write_text(details, encoding="utf-8")
        except Exception:
            pass
        try:
            # Try to show a helpful error even for direct source runs. The v14
            # launcher also catches this, so packaged users get both a native
            # dialog and a log file.
            messagebox.showerror(
                "Pokemon Battle Monitor failed to start",
                f"Startup failed before the app could open.\n\nLog file:\n{log_path}\n\nError:\n{exc}",
            )
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
