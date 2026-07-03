from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from PIL import Image, ImageFilter, ImageOps

OCR_TEXT_TIMEOUT_SECONDS = 0.7
OCR_WORD_TIMEOUT_SECONDS = 1.0

try:
    import pytesseract
except Exception:  # pragma: no cover
    pytesseract = None


@dataclass
class OcrAttempt:
    text: str
    preset: str


@dataclass
class OcrWordBox:
    text: str
    conf: float
    left: int
    top: int
    width: int
    height: int
    preset: str


COMMON_WINDOWS_TESSERACT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    # Chocolatey default when installed with `choco install tesseract`.
    r"C:\ProgramData\chocolatey\bin\tesseract.exe",
]


class OcrEngine:
    """Thin wrapper around pytesseract with Windows-friendly executable detection."""

    def __init__(self, tesseract_cmd: Optional[str] = None):
        self.tesseract_cmd = self.resolve_tesseract_cmd(tesseract_cmd)
        if pytesseract and self.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd

    @staticmethod
    def resolve_tesseract_cmd(configured_path: Optional[str] = None) -> Optional[str]:
        """Return a usable tesseract executable path if one can be found."""
        candidates: List[str] = []
        if configured_path:
            candidates.append(configured_path)

        # When distributed as a one-folder executable, prefer a portable
        # Tesseract folder beside the executable: ./tesseract/tesseract.exe.
        # During development, also support battle_monitor/vendor/tesseract.
        app_root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path.cwd()
        bundle_root = Path(getattr(sys, "_MEIPASS", app_root))
        module_root = Path(__file__).resolve().parent
        candidates.extend([
            str(app_root / "tesseract" / "tesseract.exe"),
            str(bundle_root / "tesseract" / "tesseract.exe"),
            str(bundle_root / "battle_monitor" / "vendor" / "tesseract" / "tesseract.exe"),
            str(module_root / "vendor" / "tesseract" / "tesseract.exe"),
        ])

        env_cmd = os.environ.get("TESSERACT_CMD")
        if env_cmd:
            candidates.append(env_cmd)

        path_cmd = shutil.which("tesseract")
        if path_cmd:
            candidates.append(path_cmd)

        candidates.extend(COMMON_WINDOWS_TESSERACT_PATHS)

        seen = set()
        for candidate in candidates:
            if not candidate:
                continue
            candidate = str(Path(candidate).expanduser())
            if candidate in seen:
                continue
            seen.add(candidate)
            if Path(candidate).is_file():
                return candidate
        return None

    @property
    def pytesseract_available(self) -> bool:
        return pytesseract is not None

    @property
    def executable_available(self) -> bool:
        return bool(self.tesseract_cmd and Path(self.tesseract_cmd).is_file())

    @property
    def available(self) -> bool:
        return self.pytesseract_available and self.executable_available

    def diagnostic_message(self) -> str:
        if not self.pytesseract_available:
            return (
                "Python package pytesseract is not installed. Run: "
                "pip install -r battle_monitor/requirements-battle-monitor.txt"
            )
        if not self.executable_available:
            return (
                "Tesseract OCR is not installed or could not be found. Install Tesseract for Windows, "
                "then set battle_monitor/battle_monitor_config.json to the full tesseract.exe path, "
                "for example C:/Program Files/Tesseract-OCR/tesseract.exe."
            )
        try:
            version = str(pytesseract.get_tesseract_version()).splitlines()[0]
            return f"Tesseract ready: {version} at {self.tesseract_cmd}"
        except Exception as exc:
            return f"Tesseract path found, but it failed to run: {exc}"

    def set_tesseract_cmd(self, path: str) -> None:
        self.tesseract_cmd = str(Path(path).expanduser()) if path else None
        if pytesseract and self.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd

    def candidate_crops(self, image: Image.Image) -> List[tuple[str, Image.Image]]:
        """Return OCR crops for both tight text strips and whole nameplates."""
        crops: List[tuple[str, Image.Image]] = []
        w, h = image.size
        aspect = w / max(1, h)
        tight_text_band = w >= 80 and h <= 115 and aspect >= 2.0

        if tight_text_band:
            # Add Name regions are usually already the user's exact text strip.
            # If the strip is very wide, it likely includes gender/level text.
            # Try the left/name portion first so that Lv/HP decoration does not
            # dominate the first Tesseract read.
            if aspect >= 5.5:
                crops.append(("tight_name_left", image.crop((0, 0, max(1, int(w * 0.70)), h))))
                crops.append(("tight_name_left_short", image.crop((0, 0, max(1, int(w * 0.55)), h))))
            # Then read the strip as one line; proportional sub-crops can cut
            # long names or fan-game font descenders and create garbage reads.
            crops.append(("tight_full", image))
            inset_x = max(1, int(w * 0.01))
            inset_y = max(1, int(h * 0.03))
            if w - inset_x > inset_x and h - inset_y > inset_y:
                crops.append(("tight_inner", image.crop((inset_x, inset_y, w - inset_x, h - inset_y))))
            crops.append(("tight_left_wide", image.crop((0, 0, max(1, int(w * 0.78)), h))))
            return crops

        # For full Pokémon nameplates, OCR works best when the level, HP bar,
        # gender symbol, and right-side border are excluded. Try these name-only
        # crops first so the live loop can accept a clean match before slower
        # full-panel attempts run.
        if w >= 120 and h >= 35:
            crops.append(("name_text", image.crop((max(0, int(w * 0.04)), max(0, int(h * 0.05)), max(1, int(w * 0.57)), max(1, int(h * 0.58))))))
            crops.append(("name_text_wide", image.crop((max(0, int(w * 0.03)), max(0, int(h * 0.04)), max(1, int(w * 0.68)), max(1, int(h * 0.62))))))
        crops.append(("full", image))
        if w >= 120 and h >= 35:
            crops.append(("focus_top_left", image.crop((0, 0, max(1, int(w * 0.62)), max(1, int(h * 0.68))))))
        if w >= 150 and h >= 45:
            crops.append(("inner_name", image.crop((max(0, int(w * 0.04)), max(0, int(h * 0.08)), max(1, int(w * 0.52)), max(1, int(h * 0.58))))))
        return crops

    def preprocess_variants(self, image: Image.Image, fast: bool = False) -> List[tuple[str, Image.Image]]:
        base = image.convert("L")
        variants: List[tuple[str, Image.Image]] = []
        try:
            import numpy as np
            rgb = image.convert("RGB")
            arr = np.array(rgb)
            light = ((arr[:, :, 0] > 120) & (arr[:, :, 1] > 120) & (arr[:, :, 2] > 120))
            low_chroma_light = ((arr.mean(axis=2) > 90) & (arr.std(axis=2) < 30))
            bright = ((arr[:, :, 0] > 145) & (arr[:, :, 1] > 145) & (arr[:, :, 2] > 145))
            for name, mask_values, scale in (
                ("light_text_mask", light, 6),
                ("textish_mask", light | low_chroma_light, 6),
                ("bright_text_mask", bright, 4),
            ):
                mask = Image.fromarray((mask_values * 255).astype("uint8"))
                variants.append((f"{name}_{scale}x", mask.resize((max(1, mask.width * scale), max(1, mask.height * scale)), Image.Resampling.NEAREST)))
        except Exception:
            pass

        # Pixel fonts OCR better when scaled with nearest-neighbour first; it
        # preserves hard edges instead of blurring them. The lower threshold is
        # useful for gray/outlined fan-game text while still suppressing most
        # colored HP/menu decoration.
        scale = 6 if fast else 4
        resized = base.resize((max(1, base.width * scale), max(1, base.height * scale)), Image.Resampling.NEAREST)
        variants.append((f"nearest_threshold_120_{scale}x", resized.point(lambda p: 255 if p > 120 else 0)))
        variants.append((f"nearest_threshold_150_{scale}x", resized.point(lambda p: 255 if p > 150 else 0)))
        variants.append((f"nearest_gray_{scale}x", resized))
        if not fast:
            variants.append((f"nearest_threshold_190_{scale}x", resized.point(lambda p: 255 if p > 190 else 0)))
            variants.append((f"nearest_threshold_210_{scale}x", resized.point(lambda p: 255 if p > 210 else 0)))
            variants.append((f"nearest_inverted_threshold_{scale}x", ImageOps.invert(resized).point(lambda p: 255 if p > 130 else 0)))
        return variants

    def iter_text_attempts(self, image: Image.Image):
        """Yield OCR attempts one at a time so callers can stop after a match.

        The earlier read_text() method waits for every crop/preset to finish.
        For live battle monitoring, that can make the UI look stuck even when an
        early attempt already read the Pokémon name correctly. This generator
        preserves the same OCR preprocessing but lets the app accept a recognized
        name immediately.
        """
        if not self.pytesseract_available:
            yield OcrAttempt("", "ERROR:pytesseract_not_installed")
            return
        if not self.executable_available:
            yield OcrAttempt("", "ERROR:tesseract_executable_not_found")
            return

        # Keep config simple and Windows-safe. A broad whitelist is enough
        # because Pokémon matching happens against the local whitelist later.
        base_config = "--oem 3 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.-"
        for crop_name, crop in self.candidate_crops(image):
            fast_crop = crop_name.startswith("tight") or crop_name.startswith("name_text") or crop_name == "inner_name"
            configs = [("psm7", f"--psm 7 {base_config}")]
            if fast_crop:
                configs.append(("psm13", f"--psm 13 {base_config}"))
                configs.append(("psm8", f"--psm 8 {base_config}"))
            for preset, img in self.preprocess_variants(crop, fast=fast_crop):
                for cfg_name, config in configs:
                    full_preset = f"{crop_name}/{preset}/{cfg_name}"
                    try:
                        text = pytesseract.image_to_string(img, config=config, timeout=OCR_TEXT_TIMEOUT_SECONDS)
                    except Exception as exc:
                        yield OcrAttempt("", f"{full_preset}:ERROR:{exc}")
                        continue
                    text = " ".join((text or "").split())
                    if text:
                        yield OcrAttempt(text, full_preset)

    def word_boxes(self, image: Image.Image) -> List[OcrWordBox]:
        """Return OCR word boxes for broad Name Area panel discovery.

        This is intentionally separate from the fast live OCR path. It uses
        Tesseract's sparse-text mode to find text-like clusters such as a
        Pokémon name, gender marker, and Lv/Lvl/Level number anywhere inside the
        broad Name Area. Coordinates are mapped back to the original image.
        """
        if not self.pytesseract_available or not self.executable_available:
            return []

        variants: List[tuple[str, Image.Image, float]] = []
        base = image.convert("L")
        scale = 3.0
        resized = base.resize((max(1, int(base.width * scale)), max(1, int(base.height * scale))), Image.Resampling.NEAREST)
        variants.append(("word_gray_3x", resized, scale))
        variants.append(("word_threshold_3x", resized.point(lambda p: 255 if p > 150 else 0), scale))
        variants.append(("word_inverted_threshold_3x", ImageOps.invert(resized).point(lambda p: 255 if p > 130 else 0), scale))

        boxes: List[OcrWordBox] = []
        seen = set()
        for preset, img, sc in variants:
            try:
                data = pytesseract.image_to_data(
                    img,
                    config="--psm 11 --oem 3",
                    output_type=pytesseract.Output.DICT,
                    timeout=OCR_WORD_TIMEOUT_SECONDS,
                )
            except Exception:
                continue
            n = len(data.get("text", []))
            for i in range(n):
                text = " ".join(str(data["text"][i] or "").split())
                if not text:
                    continue
                try:
                    conf = float(data.get("conf", ["-1"])[i])
                except Exception:
                    conf = -1.0
                # Keep low-confidence level markers, but ignore tiny pure noise.
                if conf < 20 and not any(ch.isdigit() for ch in text):
                    continue
                left = int(round(float(data["left"][i]) / sc))
                top = int(round(float(data["top"][i]) / sc))
                width = max(1, int(round(float(data["width"][i]) / sc)))
                height = max(1, int(round(float(data["height"][i]) / sc)))
                key = (text.upper(), left // 3, top // 3, width // 3, height // 3)
                if key in seen:
                    continue
                seen.add(key)
                boxes.append(OcrWordBox(text=text, conf=conf, left=left, top=top, width=width, height=height, preset=preset))
        return boxes

    def read_text(self, image: Image.Image) -> List[OcrAttempt]:
        return list(self.iter_text_attempts(image))
