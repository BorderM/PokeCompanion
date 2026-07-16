from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

try:
    from rapidfuzz import fuzz, process
except Exception:  # pragma: no cover - fallback for first run before dependency install
    fuzz = None
    process = None
    import difflib
else:
    difflib = None

try:
    from .ocr_quality import build_ocr_text_variants
except ImportError:  # Support direct script-style imports from battle_monitor/.
    from ocr_quality import build_ocr_text_variants


TYPE_LABELS = {
    "four_times_effective": "4× Weak",
    "super_effective": "2× Weak",
    "two_times_resistant": "½ Resist",
    "four_times_resistant": "¼ Resist",
    "immune": "Immune",
}


def clean_display(value: str) -> str:
    return (value or "").replace("-", " ").replace("_", " ").title()


def normalize_name(value: str) -> str:
    """Normalize OCR text and Pokémon display names for fuzzy matching."""
    value = (value or "").upper()
    # Common OCR substitutions from pixel fonts.
    value = value.replace("0", "O").replace("1", "I").replace("|", "I")
    value = value.replace("5", "S").replace("8", "B")
    value = value.replace("♀", " F").replace("♂", " M")
    value = re.sub(r"[^A-Z .'-]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def slug(value: str) -> str:
    value = (value or "").strip().lower()
    value = value.replace("♀", "-f").replace("♂", "-m")
    value = re.sub(r"[.:'’]", "", value)
    value = re.sub(r"[\s_]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value


def build_known_name_ocr_aliases(name: str) -> List[str]:
    """Precompute likely OCR-shaped aliases for a known Pokémon name.

    The live OCR still reads pixels with Tesseract. This helper gives the
    matcher a small whitelist-derived safety net for scale/pixel-font artifacts
    that consistently distort otherwise known names.
    """
    normalized = normalize_name(name)
    aliases: List[str] = []

    def add(value: str) -> None:
        value = re.sub(r"\s+", " ", value or "").strip()
        if value and len(re.sub(r"[^A-Z]", "", value)) >= 4 and value not in aliases:
            aliases.append(value)

    add(normalized)
    compact = re.sub(r"[^A-Z]", "", normalized)
    add(compact)
    seeds = list(aliases)
    for seed in seeds:
        compact_seed = re.sub(r"[^A-Z]", "", seed)
        if len(compact_seed) < 4:
            continue
        # Terminal A can look like a closed G/Q in small scaled pixel fonts.
        if compact_seed.endswith("A"):
            add(compact_seed[:-1] + "G")
        if compact_seed.endswith("IA"):
            add(compact_seed[:-2] + "IG")
        # Tall strokes swap frequently after nearest-neighbour emulator scaling.
        if "I" in compact_seed:
            add(compact_seed.replace("I", "L"))
        if "L" in compact_seed:
            add(compact_seed.replace("L", "I"))
        # rn/m ambiguity already appears in OCR output repair; precompute it for
        # known names too so exact alias lookup can catch it before fuzzy match.
        if "RN" in compact_seed:
            add(compact_seed.replace("RN", "M"))
        if "M" in compact_seed and len(compact_seed) >= 5:
            add(compact_seed.replace("M", "RN"))
        # Arcanine-style rounded A/R/C strokes can be read as H/R/E in the small
        # GBA/DS/fan-game nameplates the monitor sees.
        if compact_seed.startswith("ARCA"):
            add("HREA" + compact_seed[4:])
    return aliases


@dataclass(frozen=True)
class MatchResult:
    key: str
    display_name: str
    score: float
    raw_text: str
    normalized_text: str


class PokemonRepository:
    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)
        self.processed_path = self.project_root / "processed_pokemon_cache.json"
        self.form_reference_path = self.project_root / "data" / "form_reference.json"
        self.profile_index_path = self.project_root / "data" / "pokemon_profile_details_index.json"
        self.profile_shards_dir = self.project_root / "data" / "profile_details_shards"

        self.pokemon: Dict[str, Dict[str, Any]] = {}
        self.forms_by_species: Dict[str, List[str]] = {}
        self.candidates: List[str] = []
        self.candidate_to_key: Dict[str, str] = {}
        self.ocr_alias_to_candidate: Dict[str, str] = {}
        self._profile_index: Dict[str, Any] = {}
        self._loaded_shards: Dict[str, Dict[str, Any]] = {}
        self.load()

    def load(self) -> None:
        with self.processed_path.open("r", encoding="utf-8") as f:
            records = json.load(f)
        for record in records:
            key = record.get("name")
            if not key:
                continue
            self.pokemon[key] = record
            self._add_candidate(record.get("display_name") or clean_display(key), key)
            self._add_candidate(key, key)
            if record.get("species"):
                self._add_candidate(record["species"], key)

        if self.form_reference_path.exists():
            with self.form_reference_path.open("r", encoding="utf-8") as f:
                form_ref = json.load(f)
            for raw_key, meta in form_ref.items():
                if raw_key not in self.pokemon:
                    continue
                for field in (
                    "raw_display",
                    "form_display",
                    "species_display",
                    "type_display",
                    "stats_display",
                    "type_key",
                    "stats_key",
                ):
                    if meta.get(field):
                        self._add_candidate(meta[field], raw_key)

        # Deduplicate while preserving order.
        seen = set()
        deduped = []
        for c in self.candidates:
            if c not in seen:
                seen.add(c)
                deduped.append(c)
        self.candidates = deduped
        self._build_ocr_alias_index()

        # Group all local forms by base species so the monitor can offer a
        # manual form selector. This matters for regional/forms where the game
        # may display only the base name while type/stats/effectiveness differ.
        self.forms_by_species = {}
        for form_key, form_record in self.pokemon.items():
            species_key = form_record.get("species") or form_key
            self.forms_by_species.setdefault(species_key, []).append(form_key)
        for species_key, keys in self.forms_by_species.items():
            base = self.pokemon.get(species_key, {})
            base_types = tuple(base.get("types", []) or [])
            base_stats = tuple(sorted((base.get("stats", {}) or {}).items()))

            def form_sort_key(k: str):
                rec = self.pokemon.get(k, {})
                display = rec.get("display_name") or clean_display(k)
                lowered = display.lower()
                # Base first, then regional forms, then the rest alphabetically.
                regional_rank = 0 if any(tag in lowered for tag in ("alola", "galar", "hisui", "paldea")) else 1
                return (0 if k == species_key else 1, regional_rank, display)

            keys.sort(key=form_sort_key)

        if self.profile_index_path.exists():
            with self.profile_index_path.open("r", encoding="utf-8") as f:
                self._profile_index = json.load(f)

    def _add_candidate(self, text: str, key: str) -> None:
        if not text:
            return
        normal = normalize_name(str(text))
        if len(normal) < 2:
            return
        self.candidates.append(normal)
        # Preserve the first/base mapping for ambiguous aliases such as "Garchomp"
        # appearing on both the base form and Mega form. Exact form candidates
        # such as "Garchomp Mega" remain separate and still resolve to that form.
        self.candidate_to_key.setdefault(normal, key)

    def _build_ocr_alias_index(self) -> None:
        """Build a small exact-lookup map of likely OCR distortions to names."""
        alias_to_candidate: Dict[str, str] = {}
        ambiguous_aliases: set[str] = set()
        for candidate in self.candidates:
            key = self.candidate_to_key.get(candidate)
            if not key:
                continue
            for alias in build_known_name_ocr_aliases(candidate):
                if alias in self.candidate_to_key:
                    # Exact known names are handled before alias lookup.
                    continue
                existing = alias_to_candidate.get(alias)
                if existing and self.candidate_to_key.get(existing) != key:
                    ambiguous_aliases.add(alias)
                    alias_to_candidate.pop(alias, None)
                    continue
                if alias not in ambiguous_aliases:
                    alias_to_candidate[alias] = candidate
        self.ocr_alias_to_candidate = alias_to_candidate

    def _make_match(self, candidate: str, score: float, raw_text: str, normalized: str) -> Optional[MatchResult]:
        key = self.candidate_to_key.get(candidate)
        if not key or key not in self.pokemon:
            return None
        record = self.pokemon.get(key, {})
        return MatchResult(
            key=key,
            display_name=record.get("display_name") or clean_display(key),
            score=float(score),
            raw_text=raw_text,
            normalized_text=normalized,
        )

    def _trim_after_battle_gender_marker(self, raw_text: str) -> str:
        """Drop level/HP noise that appears after a visible gender marker."""
        raw_text = raw_text or ""
        if not raw_text:
            return raw_text
        upper = raw_text.upper()
        # Nidoran's species name itself contains a gender marker; do not turn
        # Nidoran♂/Nidoran♀ into the ambiguous base text "Nidoran".
        if re.search(r"NIDORAN\s*[♀♂]", upper):
            return raw_text
        positions = [pos for marker in ("♀", "♂") if (pos := raw_text.find(marker)) >= 0]
        if not positions:
            return raw_text
        split_at = min(positions)
        left = raw_text[:split_at]
        if len(re.sub(r"[^A-Za-z]", "", left)) < 2:
            return raw_text
        return left.strip()

    def _clean_ocr_nameplate_text(self, raw_text: str) -> str:
        """Remove common battle UI noise before matching OCR output.

        Tesseract may read a full GBA/DS nameplate as text such as
        ``Heatmor Lv58 HP``. Since we only need the Pokémon name, stripping
        level/HP fragments makes exact and fuzzy matching much more reliable.
        """
        text = normalize_name(self._trim_after_battle_gender_marker(raw_text))
        if not re.match(r"^NIDORAN\s+[MF]\b", text):
            text = re.sub(r"\b[MF]\s+L[VWUYI]?\s*[A-Z0-9]{0,4}\b.*$", " ", text)
        text = re.sub(r"\bL[VW]\s*\d{1,3}\b", " ", text)
        text = re.sub(r"\bLEVEL\s*\d{1,3}\b", " ", text)
        text = re.sub(r"\bHP\b", " ", text)
        text = re.sub(r"\b(MALE|FEMALE)\b", " ", text)
        text = re.sub(r"\b[MF]\b$", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _ocr_candidate_variants(self, normalized: str, cleaned: str) -> List[str]:
        """Return conservative OCR variants for pixel-font nameplate reads."""
        variants: List[str] = []

        def add(value: str) -> None:
            value = re.sub(r"\s+", " ", value or "").strip()
            if value and value not in variants:
                variants.append(value)

        for value in (normalized, cleaned):
            add(value)
            for repaired in build_ocr_text_variants(value):
                add(repaired)
            # Fan-game level markers often OCR as "Lyd", "Luad", "Lusi", etc.
            # Split only when there is whitespace before the level-ish token.
            for pattern in (
                r"\s+L[VWUYI][A-Z0-9]{0,4}\b.*$",
                r"\s+L\s*[VWUYI]?\s*[A-Z0-9]{1,4}\b.*$",
                r"\s+LEVEL\s*[A-Z0-9]{0,4}\b.*$",
            ):
                add(re.sub(pattern, "", value, flags=re.IGNORECASE))
            words = [w for w in re.split(r"\s+", value) if w]
            for n in (1, 2, 3):
                if len(words) >= n:
                    add(" ".join(words[:n]))

        # Very small, exact/substring-oriented substitutions seen in chunky
        # pixel fonts. These are not used to match tiny fragments because the
        # short-noise guard below still runs before fuzzy matching.
        for value in list(variants):
            compact = re.sub(r"[^A-Z]", "", value)
            if len(compact) < 4:
                continue
            if compact.startswith(("UNIX", "UNIK")):
                add("O" + compact[1:])
            if compact.startswith("LRO"):
                add("CRO" + compact[3:])
        return variants

    def match_name(self, raw_text: str, min_score: float = 84) -> Optional[MatchResult]:
        normalized = normalize_name(raw_text)
        if len(normalized) < 2:
            return None

        cleaned = self._clean_ocr_nameplate_text(raw_text)
        candidates_to_try = self._ocr_candidate_variants(normalized, cleaned)

        # Fast path: exact normalized candidate. This fixes cases where OCR has
        # correctly read a name like "Heatmor" but the fuzzy path is unavailable
        # or overly conservative in a packaged build.
        for value in candidates_to_try:
            if value in self.candidate_to_key:
                return self._make_match(value, 100.0, raw_text, normalized)

        # Precomputed known-name aliases catch stable scale/pixel-font OCR shapes
        # such as Roselia -> ROSELIG before broad fuzzy matching has to guess.
        for value in candidates_to_try:
            alias_candidate = self.ocr_alias_to_candidate.get(value)
            if alias_candidate:
                match = self._make_match(alias_candidate, 97.0, raw_text, normalized)
                if match and match.score >= min_score:
                    return match

        # Do not fuzzy-match tiny fragments. When there is no Pokémon name on
        # screen, OCR often returns scraps like "1", "WW", "I WW", or short
        # partials like "Onit". Those can accidentally score well against
        # longer names. Exact short names above are still accepted.
        cleaned_letters = re.sub(r"[^A-Z]", "", cleaned or normalized)
        if len(cleaned_letters) <= 4:
            return None

        # Reads like "Uni Lyd" are usually a short partial name plus a badly
        # read level marker. Fuzzy matching those can jump to unrelated longer
        # Pokémon such as Reuniclus. Exact short names and exact substitutions
        # have already returned above, so do not fuzzy-match this shape.
        words = [w for w in re.split(r"\s+", cleaned or normalized) if w]
        if len(words) >= 2:
            first_letters = re.sub(r"[^A-Z]", "", words[0])
            levelish_rest = any(re.fullmatch(r"L[VWUYI]?[A-Z0-9]{0,4}", word) for word in words[1:])
            if len(first_letters) < 4 and levelish_rest:
                return None

        # Substring path: useful when a user selects the whole nameplate and OCR
        # includes level/HP text along with the name. Prefer the longest matching
        # Pokémon candidate to avoid short aliases winning.
        for value in candidates_to_try:
            if len(value) >= 4:
                for candidate in sorted(self.candidates, key=len, reverse=True):
                    if len(candidate) < 4:
                        continue
                    candidate_compact = re.sub(r"[^A-Z]", "", candidate)
                    value_compact = re.sub(r"[^A-Z]", "", value)
                    contains_full_candidate = candidate in value or (
                        len(candidate_compact) >= 4 and candidate_compact in value_compact
                    )
                    is_strong_partial = (
                        len(value_compact) >= 5
                        and len(candidate_compact) >= 5
                        and value_compact in candidate_compact
                        and (len(value_compact) / max(1, len(candidate_compact))) >= 0.72
                    )
                    if contains_full_candidate or is_strong_partial:
                        match = self._make_match(candidate, 98.0, raw_text, normalized)
                        if match and match.score >= min_score:
                            return match

        best_candidate = None
        best_score = 0.0
        for value in candidates_to_try:
            if process and fuzz:
                result = process.extractOne(value, self.candidates, scorer=fuzz.WRatio)
                if not result:
                    continue
                candidate, score, _idx = result
                score = float(score)
            else:
                result = difflib.get_close_matches(value, self.candidates, n=1, cutoff=0)
                if not result:
                    continue
                candidate = result[0]
                score = difflib.SequenceMatcher(None, value, candidate).ratio() * 100
            if score > best_score:
                best_candidate = candidate
                best_score = score

        if not best_candidate or best_score < min_score:
            return None
        return self._make_match(best_candidate, best_score, raw_text, normalized)


    def get_species_key(self, key: str) -> str:
        record = self.pokemon.get(key) or {}
        return record.get("species") or key

    def same_species(self, left_key: str, right_key: str) -> bool:
        if not left_key or not right_key:
            return False
        if left_key not in self.pokemon or right_key not in self.pokemon:
            return False
        return self.get_species_key(left_key) == self.get_species_key(right_key)

    def _form_signature(self, key: str) -> tuple:
        record = self.pokemon.get(key, {}) or {}
        types = tuple(record.get("types", []) or [])
        stats = tuple(sorted((record.get("stats", {}) or {}).items()))
        return types, stats

    def get_form_options(self, key: str) -> List[Dict[str, Any]]:
        """Return meaningful alternate forms for the detected species.

        The game often displays the base species name for regional or other
        forms. The monitor keeps the OCR result, but lets the user switch the
        data card to another form until that slot detects a different species.
        Purely cosmetic duplicates are hidden unless they differ in typing or
        stats, keeping the menu compact.
        """
        if not key or key not in self.pokemon:
            return []
        species_key = self.get_species_key(key)
        keys = list(self.forms_by_species.get(species_key, []))
        if len(keys) <= 1:
            return []

        base_signature = self._form_signature(species_key)
        meaningful = []
        for form_key in keys:
            differs = self._form_signature(form_key) != base_signature
            if form_key == species_key or differs:
                meaningful.append(form_key)

        # Hide purely cosmetic duplicates. The battle monitor form button is
        # intended for forms that change useful battle data such as typing/stats.
        if len(meaningful) <= 1:
            return []

        options = []
        for form_key in meaningful:
            record = self.pokemon.get(form_key, {}) or {}
            display = record.get("display_name") or clean_display(form_key)
            options.append({
                "key": form_key,
                "display_name": display,
                "types": record.get("types", []) or [],
                "is_current": form_key == key,
                "is_base": form_key == species_key,
            })
        return options

    def _load_profile_details(self, key: str) -> Dict[str, Any]:
        key_to_shard = self._profile_index.get("key_to_shard", {}) if isinstance(self._profile_index, dict) else {}
        shard_id = key_to_shard.get(key) or (key[:1].lower() if key else "")
        if not shard_id:
            return {}
        if shard_id not in self._loaded_shards:
            shard_path = self.profile_shards_dir / f"{shard_id}.json"
            if not shard_path.exists():
                self._loaded_shards[shard_id] = {}
            else:
                with shard_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                self._loaded_shards[shard_id] = data.get("profiles", {}) if isinstance(data, dict) else {}
        return self._loaded_shards.get(shard_id, {}).get(key, {}) or {}

    def get_battle_summary(self, key: str) -> Dict[str, Any]:
        record = self.pokemon.get(key)
        if not record:
            return {}
        details = self._load_profile_details(key)
        if not details and record.get("species") and record["species"] != key:
            details = self._load_profile_details(record["species"])

        stats = record.get("stats", {}) or {}
        attack = stats.get("attack") or 0
        sp_attack = stats.get("special_attack") or 0
        defense = stats.get("defense") or 0
        sp_defense = stats.get("special_defense") or 0

        if attack == sp_attack:
            attack_bias = "Balanced offenses"
        else:
            attack_bias = "Physical attacker" if attack > sp_attack else "Special attacker"

        if defense == sp_defense:
            defensive_note = "Balanced defenses"
        else:
            lower = "Defense" if defense < sp_defense else "Special Defense"
            defensive_note = f"Lower {lower}"

        return {
            "key": key,
            "display_name": record.get("display_name") or clean_display(key),
            "types": record.get("types", []),
            "effectiveness": record.get("effectiveness", {}) or {},
            "stats": stats,
            "attack_bias": attack_bias,
            "defensive_note": defensive_note,
            "abilities": details.get("abilities", []) if isinstance(details, dict) else [],
            "sprite_url": record.get("sprite_url"),
        }

    def format_summary_text(self, key: str) -> str:
        summary = self.get_battle_summary(key)
        if not summary:
            return ""

        stats = summary["stats"]
        eff = summary["effectiveness"]
        stat_order = [
            ("hp", "HP"),
            ("attack", "Attack"),
            ("defense", "Defense"),
            ("special_attack", "Sp. Atk"),
            ("special_defense", "Sp. Def"),
            ("speed", "Speed"),
            ("total", "Total"),
        ]
        lines = []
        lines.append(summary["display_name"])
        lines.append("Types: " + " / ".join(t.title() for t in summary["types"]))
        lines.append("")
        lines.append("Base Stats:")
        for key, label in stat_order:
            lines.append(f"- {label}: {stats.get(key, '—')}")
        lines.append("")
        lines.append(f"Offense: {summary['attack_bias']} — Atk {stats.get('attack', '—')} / SpA {stats.get('special_attack', '—')}")
        lines.append(f"Bulk: {summary['defensive_note']} — Def {stats.get('defense', '—')} / SpD {stats.get('special_defense', '—')}")
        lines.append("")

        for field in ("four_times_effective", "super_effective", "two_times_resistant", "four_times_resistant", "immune"):
            values = eff.get(field) or []
            if values:
                lines.append(f"{TYPE_LABELS[field]}: " + ", ".join(t.title() for t in values))
        lines.append("")

        abilities = summary.get("abilities") or []
        if abilities:
            lines.append("Abilities:")
            for ability in abilities:
                hidden = " (Hidden)" if ability.get("is_hidden") else ""
                effect = ability.get("effect") or ability.get("flavor_text") or ""
                lines.append(f"- {ability.get('name', 'Unknown')}{hidden}: {effect}")
        else:
            lines.append("Abilities: not found in local profile-detail cache")
        return "\n".join(lines).strip()
