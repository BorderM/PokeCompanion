from __future__ import annotations

import json
import re
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Protocol, Sequence

from PIL import Image

try:
    from .ocr_engine import OcrAttempt
except ImportError:  # Support running modules directly from battle_monitor/.
    from ocr_engine import OcrAttempt


def normalize_name(value: str) -> str:
    value = (value or "").upper()
    value = value.replace("0", "O").replace("1", "I").replace("|", "I")
    value = value.replace("5", "S").replace("8", "B")
    value = value.replace("♀", " F").replace("♂", " M")
    value = re.sub(r"[^A-Z .'-]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


LEVEL_NOISE_PATTERNS = (
    r"\bL\s*[VWUYI]?\s*[0-9SBI]{1,3}\b.*$",
    r"\bL[VWUYI]{1,3}\s*[0-9SBI]{0,3}\b.*$",
    r"\bL[VWUYI]?[0-9SBI]{1,4}\b.*$",
    r"\bLVL?\s*[0-9SBI]{0,3}\b.*$",
    r"\bLEVEL\s*[0-9SBI]{0,3}\b.*$",
    r"\bHP\b.*$",
)


def _dedupe(values: Iterable[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for value in values:
        value = re.sub(r"\s+", " ", value or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def build_ocr_text_variants(raw_text: str) -> List[str]:
    """Return conservative variants for common Pokémon pixel-font OCR errors.

    This does not replace Tesseract. It repairs the text *after* OCR and before
    matching against the known Pokémon-name whitelist.
    """
    normalized = normalize_name(raw_text)
    stripped = []
    without_hp = re.sub(r"\bHP\b.*$", "", normalized, flags=re.IGNORECASE).strip()
    for value in (without_hp, normalized):
        stripped.append(value)
        for pattern in LEVEL_NOISE_PATTERNS:
            stripped.append(re.sub(pattern, "", value, flags=re.IGNORECASE).strip())
    seeds = _dedupe(stripped)
    words = [w for w in re.split(r"\s+", without_hp or normalized) if w]
    for n in (1, 2, 3):
        if len(words) >= n:
            seeds.append(" ".join(words[:n]))

    variants: List[str] = []
    for seed in _dedupe(seeds):
        variants.append(seed)
        compact = re.sub(r"[^A-Z]", "", seed)
        if len(compact) >= 4:
            variants.append(compact)
            # Pixel-font/Tesseract confusions seen in monster names.
            replacements = [
                ("II", "LI"),
                ("II", "LL"),
                ("ATM", "ATR"),
                ("IGATM", "IGATR"),
                ("LR", "CR"),
                ("UNIX", "UNOWN"),
                ("UNIK", "UNOWN"),
                ("0", "O"),
                ("1", "I"),
            ]
            for old, new in replacements:
                if old in compact:
                    variants.append(compact.replace(old, new))
            repaired = compact
            for old, new in (("II", "LI"), ("IGATM", "IGATR"), ("ATM", "ATR")):
                repaired = repaired.replace(old, new)
            if repaired != compact:
                variants.append(repaired)
            # rn/m ambiguity. Try both directions, but only on reasonably long
            # strings to avoid damaging short exact names.
            if "RN" in compact:
                variants.append(compact.replace("RN", "M"))
            if "M" in compact and len(compact) >= 5:
                variants.append(compact.replace("M", "RN"))
            # Terminal R can look like M in some chunky fonts.
            if compact.endswith("M") and len(compact) >= 6:
                variants.append(compact[:-1] + "R")
    return _dedupe(variants)


@dataclass
class OcrSavedFailure:
    image_path: Path
    metadata_path: Path


class OcrFailureRecorder:
    """Save failed OCR crops plus enough metadata to build a regression sample."""

    def __init__(self, output_dir: Path, enabled: bool = False, max_saved: int = 100):
        self.output_dir = Path(output_dir)
        self.enabled = bool(enabled)
        self.max_saved = int(max_saved)

    def record(
        self,
        image: Image.Image,
        slot_idx: int,
        source: str,
        attempts: Sequence[OcrAttempt],
        threshold: int,
        reason: str,
    ) -> Optional[OcrSavedFailure]:
        if not self.enabled:
            return None
        self.output_dir.mkdir(parents=True, exist_ok=True)
        existing = sorted(self.output_dir.glob("*.png"), key=lambda p: p.stat().st_mtime)
        while len(existing) >= self.max_saved:
            victim = existing.pop(0)
            metadata = victim.with_suffix(".json")
            victim.unlink(missing_ok=True)
            metadata.unlink(missing_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        safe_source = re.sub(r"[^A-Za-z0-9_.-]+", "_", source or "unknown")[:40]
        stem = f"{stamp}_slot{slot_idx + 1}_{safe_source}_{reason}"
        image_path = self.output_dir / f"{stem}.png"
        metadata_path = self.output_dir / f"{stem}.json"
        image.save(image_path)
        metadata = {
            "slot": slot_idx + 1,
            "source": source,
            "threshold": threshold,
            "reason": reason,
            "attempts": [{"text": a.text, "preset": a.preset} for a in attempts],
        }
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        return OcrSavedFailure(image_path=image_path, metadata_path=metadata_path)


class TemporalMatchStabilizer:
    """Accept high-confidence OCR immediately and debounce medium-confidence reads."""

    def __init__(self, confirm_score: float = 95.0, repeat_score: float = 84.0, repeat_count: int = 2, window: int = 4):
        self.confirm_score = float(confirm_score)
        self.repeat_score = float(repeat_score)
        self.repeat_count = int(repeat_count)
        self.histories: dict[int, deque[str]] = {}
        self.window = int(window)

    def clear_slot(self, slot_idx: int) -> None:
        self.histories.pop(slot_idx, None)

    def clear(self) -> None:
        self.histories.clear()

    def accept(self, slot_idx: int, match):
        if match is None:
            return None
        if match.score >= self.confirm_score:
            self.histories.setdefault(slot_idx, deque(maxlen=self.window)).append(match.key)
            return match
        if match.score < self.repeat_score:
            return None
        history = self.histories.setdefault(slot_idx, deque(maxlen=self.window))
        history.append(match.key)
        return match if list(history).count(match.key) >= self.repeat_count else None


@dataclass(frozen=True)
class OcrSampleCase:
    image_path: Path
    expected_name: str


@dataclass(frozen=True)
class OcrSampleResult:
    image_path: Path
    expected_name: str
    matched_name: str
    matched_key: str
    score: float
    passed: bool
    attempts: list[str]


@dataclass(frozen=True)
class OcrSampleReport:
    total: int
    passed: int
    results: list[OcrSampleResult]

    @property
    def accuracy(self) -> float:
        return 0.0 if self.total == 0 else round((self.passed / self.total) * 100.0, 2)


class OcrLike(Protocol):
    def iter_text_attempts(self, image: Image.Image): ...


class RepositoryLike(Protocol):
    def match_name(self, text: str, min_score: float = 84): ...


class OcrSampleEvaluator:
    def __init__(self, ocr: OcrLike, repo: RepositoryLike, min_score: float = 84.0):
        self.ocr = ocr
        self.repo = repo
        self.min_score = float(min_score)

    def evaluate(self, cases: Sequence[OcrSampleCase]) -> OcrSampleReport:
        results: list[OcrSampleResult] = []
        for case in cases:
            image = Image.open(case.image_path)
            attempts = list(self.ocr.iter_text_attempts(image))
            best = None
            for attempt in attempts:
                for variant in build_ocr_text_variants(attempt.text):
                    match = self.repo.match_name(variant, min_score=self.min_score)
                    if match and (best is None or match.score > best.score):
                        best = match
            expected_norm = normalize_name(case.expected_name)
            matched_name = best.display_name if best else ""
            passed = bool(best and normalize_name(matched_name) == expected_norm)
            results.append(OcrSampleResult(
                image_path=case.image_path,
                expected_name=case.expected_name,
                matched_name=matched_name,
                matched_key=best.key if best else "",
                score=best.score if best else 0.0,
                passed=passed,
                attempts=[a.text for a in attempts if a.text],
            ))
        return OcrSampleReport(total=len(results), passed=sum(1 for r in results if r.passed), results=results)
