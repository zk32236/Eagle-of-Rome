# src/core/scenario_validation.py
"""
EOR20261013-02 GUI Readiness — slice S-A (scenario / configuration).

Authoritative, fail-closed scenario SELECTION + VALIDATION for the production GUI
launch chain::

    gui_main.main  ->  session_api.create_gui_prototype_session
                   ->  scenario_validation.prepare_selected_scenario  (single capture)
                   ->  ScenarioLoader.initialize_validated_scenario  (validated snapshot)

Design intent (GR-F10 / GR-F11 / S-A R02 provenance):
  * the GUI scenario name is a launch parameter, not a hardcoded constant;
  * an explicitly selected scenario is validated BEFORE any exposed GameState /
    session is created, so an invalid input can never produce a half-open session;
  * the selected file is captured ONCE, parsed/validated, and returned as a
    recursively-immutable :class:`ValidatedScenarioSnapshot` that the bounded loader
    entry consumes verbatim; the envelope is validator-only (no public/bypass
    constructor, no reassignment/re-initialization) and the bounded entry admits it
    only via :func:`is_usable_snapshot` (validator origin, not ``isinstance`` alone);
  * there is NO silent fallback to ``gui_prototype.json`` for an explicitly selected
    scenario, and the GUI route has no edge to the historical filename loader or its
    built-in whole-scenario default. The historical silent-fallback path stays
    confined to non-selected / CLI callers of ``ScenarioLoader.load_scenario`` itself.

Scope of the preflight (S-A):
  1..6 factions; non-empty unique string faction ids; boolean ownership flags;
  derived ``player_<faction_id>`` ids unique; exactly one HUMAN-or-AI controller per
  faction (1:1 faction<->player); explicit player records are rejected as unsupported;
  nonnegative permitted economic values; legal figure-generation schema; required
  card/config resources present.

Effective-economy note (S-A item 5):
  per-faction ``treasury`` in the scenario JSON is IGNORED by ``ScenarioLoader`` at
  HEAD (``_load_factions`` always uses ``economic_rules.faction_initial_treasury``).
  This module REPORTS the effective value and never invents a new finance rule.
"""

from __future__ import annotations

import hashlib
import json
import os
import weakref
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any, Dict, Optional

from src.core.config import Config


MIN_FACTIONS = 1
MAX_FACTIONS = 6
# GUI readiness requires at least one human-driven seat (spec MVP0.7-12 §2.2:
# `_turn_order` contains HUMAN players only; AI seats are driven by
# AutoPlayerProcessor). A 0-HUMAN (all-AI) scenario is rejected fail-closed here.
# TEMPORARY S-A rule: a future "6 AI mode" requirement may revisit this.
MIN_HUMANS = 1
DEFAULT_SCENARIO_FILE = "gui_prototype.json"
SCENARIO_SUFFIX = ".json"

CONTROLLER_HUMAN = "HUMAN"
CONTROLLER_AI = "AI"


class ScenarioValidationError(ValueError):
    """Raised when a scenario selection is illegal (fail-closed)."""


def _deep_freeze(value: Any) -> Any:
    """Recursively freeze mappings/sequences into an owned immutable representation.

    ``dict`` -> read-only mapping proxy; ``list``/``tuple`` -> ``tuple``. Scalars are
    returned as-is (``bytes``/``str``/``int``/``bool``/``None`` are already immutable).
    No mutable alias to the source is retained: the containers are rebuilt here, so a
    frozen outer record wrapping mutable nested dicts/lists is not sufficient and is
    not what this returns.
    """
    if isinstance(value, Mapping):
        return MappingProxyType({k: _deep_freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(v) for v in value)
    return value


def _deep_thaw(value: Any) -> Any:
    """Recursively rebuild a fresh owned mutable structure from a frozen one."""
    if isinstance(value, Mapping):
        return {k: _deep_thaw(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_deep_thaw(v) for v in value]
    return value


# --- validator-only origin enforcement -------------------------------------
# ``_MINT_TOKEN`` is module-private: only :func:`prepare_selected_scenario` (the sole
# holder of the token) can construct a usable envelope. A public
# ``ValidatedScenarioSnapshot(...)`` call is refused before any state is stored, so
# construction is not a public bypass API.
_MINT_TOKEN = object()

# Registry of validator-issued envelopes. The bounded loader entry demands validator
# ORIGIN via this registry (not merely ``isinstance``): a same-class object forged or
# constructed outside the preparation path is not a member and is rejected.
_ISSUED_SNAPSHOTS = weakref.WeakSet()


class ValidatedScenarioSnapshot:
    """Immutable, validator-only, single-capture envelope for a validated selection.

    Only :func:`prepare_selected_scenario` produces a usable instance, after parsing
    and validating the exact bytes it captured. It carries (i) the canonical filename
    and resolved approved source path, (ii) the exact captured ``bytes`` with length
    and SHA-256, (iii) the recursively immutable parsed configuration, and (iv) the
    validation/effective-value report — configuration and report both derived from the
    same capture.

    Origin + immutability enforcement (S-A r5):

    * construction requires the module-private minting token, so there is **no**
      public/bypass constructor accepting arbitrary bytes/config/report;
    * attribute reassignment/deletion and re-initialization are rejected, so the
      envelope cannot be rebound or swapped after validation (re-calling the ordinary
      initializer cannot replace config while keeping the original bytes/hash);
    * the bounded loader entry admits an envelope only through
      :func:`is_usable_snapshot`, which demands validator origin plus metadata/bytes
      integrity — never ``isinstance`` alone.
    """

    __slots__ = ("_canonical_name", "_path", "_raw_bytes", "_byte_length", "_sha256",
                 "_config", "_report", "_sealed", "__weakref__")

    def __init__(self, canonical_name=None, path=None, raw_bytes=None,
                 parsed_config=None, report=None, *, _issuer=None):
        # Validator-only origin: a public/bypass construction is refused outright.
        if _issuer is not _MINT_TOKEN:
            raise TypeError(
                "ValidatedScenarioSnapshot is validator-only; obtain a usable "
                "envelope from scenario_validation.prepare_selected_scenario()")
        # Re-initialization of an existing envelope is forbidden (immutability).
        if getattr(self, "_sealed", False):
            raise TypeError(
                "ValidatedScenarioSnapshot is immutable; cannot re-initialize")
        if not isinstance(raw_bytes, (bytes, bytearray)):
            raise TypeError("snapshot raw bytes must be bytes-like")
        owned = bytes(raw_bytes)  # owned immutable copy
        object.__setattr__(self, "_canonical_name", str(canonical_name))
        object.__setattr__(self, "_path", str(path))
        object.__setattr__(self, "_raw_bytes", owned)
        object.__setattr__(self, "_byte_length", len(owned))
        object.__setattr__(self, "_sha256", hashlib.sha256(owned).hexdigest())
        object.__setattr__(self, "_config", _deep_freeze(parsed_config))
        object.__setattr__(self, "_report", _deep_freeze(report))
        object.__setattr__(self, "_sealed", True)

    # ---- immutability: no reassignment / deletion after construction ----
    def __setattr__(self, name, value):
        raise AttributeError(
            "ValidatedScenarioSnapshot is immutable: reassignment forbidden")

    def __delattr__(self, name):
        raise AttributeError(
            "ValidatedScenarioSnapshot is immutable: deletion forbidden")

    @property
    def canonical_name(self) -> str:
        return self._canonical_name

    @property
    def path(self) -> str:
        return self._path

    @property
    def raw_bytes(self) -> bytes:
        return self._raw_bytes

    @property
    def byte_length(self) -> int:
        return self._byte_length

    @property
    def sha256(self) -> str:
        return self._sha256

    @property
    def frozen_config(self) -> Any:
        """The recursively immutable parsed configuration (read-only)."""
        return self._config

    @property
    def frozen_report(self) -> Any:
        """The recursively immutable validation/effective report (read-only)."""
        return self._report

    def config_copy(self) -> dict:
        """Fresh owned mutable config dict derived solely from the frozen capture.

        The bounded loader entry privately deep-thaws exactly once through this method.
        Every field value and sequence order is preserved; the copy is derived only
        from the validated snapshot (never a filename reread, replacement JSON or the
        built-in scenario).
        """
        return _deep_thaw(self._config)

    def report_copy(self) -> dict:
        """Fresh owned mutable report dict derived solely from the frozen capture."""
        return _deep_thaw(self._report)


def is_usable_snapshot(obj: Any) -> bool:
    """True only for a validator-issued, sealed, integrity-consistent envelope.

    Used by the bounded loader entry for admission. It demands validator ORIGIN
    (minted by :func:`prepare_selected_scenario`), the sealed state, and that the
    retained length/SHA still match the retained bytes — so a same-class object forged
    outside the preparation path, a re-initialized/swapped instance, or one whose
    metadata diverged from its bytes is rejected. A read-only property or a matching
    class name is not proof that preparation ran.
    """
    if not isinstance(obj, ValidatedScenarioSnapshot):
        return False
    if not getattr(obj, "_sealed", False):
        return False
    if obj not in _ISSUED_SNAPSHOTS:
        return False
    try:
        raw = obj._raw_bytes
        if not isinstance(raw, bytes):
            return False
        if obj._byte_length != len(raw):
            return False
        if obj._sha256 != hashlib.sha256(raw).hexdigest():
            return False
    except AttributeError:
        return False
    return True


def _product_root() -> Path:
    # src/core/scenario_validation.py -> <root>
    return Path(__file__).resolve().parent.parent.parent


def scenarios_dir() -> Path:
    """Approved directory holding selectable scenario files."""
    return _product_root() / "data" / "scenarios"


def resolve_scenario_path(scenario_file: str) -> Path:
    """Resolve a bare scenario filename to an absolute path under ``data/scenarios``.

    Rejects absolute paths, drive letters, UNC paths, path separators, traversal and
    non-``.json`` names — an explicitly selected scenario must be a bare file name
    inside the approved scenarios directory.
    """
    if not isinstance(scenario_file, str) or not scenario_file.strip():
        raise ScenarioValidationError("scenario_file must be a non-empty string")
    # Canonical-name discipline (R02): only a bare, exactly-named file inside the
    # approved directory is accepted. A non-canonical selection (e.g. whitespace
    # wrapped ``" gr_f_3h.json "``) is rejected here so the SAME validated name is
    # consumed by both preflight and loader — never a raw/loader-divergent name.
    if scenario_file != scenario_file.strip():
        raise ScenarioValidationError(
            "scenario selection must be a canonical bare filename without "
            f"surrounding whitespace: {scenario_file!r}")

    name = scenario_file.strip()
    if os.path.sep in name or "/" in name or "\\" in name:
        raise ScenarioValidationError(
            f"scenario selection must be a bare filename, got {scenario_file!r}")
    if name in (".", "..") or name.startswith(".."):
        raise ScenarioValidationError(f"illegal scenario name {scenario_file!r}")
    # Windows drive-letter / UNC defense (harmless on POSIX).
    if len(name) >= 2 and name[1] == ":":
        raise ScenarioValidationError(f"absolute scenario path rejected: {scenario_file!r}")
    if not name.endswith(SCENARIO_SUFFIX):
        raise ScenarioValidationError(
            f"scenario file must end with {SCENARIO_SUFFIX}: {scenario_file!r}")

    base = scenarios_dir().resolve()
    resolved = (base / name).resolve()
    if resolved.parent != base:
        raise ScenarioValidationError(
            f"scenario outside approved directory: {scenario_file!r}")
    if not resolved.is_file():
        raise ScenarioValidationError(f"scenario not found: {name}")
    return resolved


def effective_faction_treasury(config_path: Optional[str] = None) -> int:
    """Effective per-faction starting treasury.

    The loader ignores per-faction JSON ``treasury`` values and always uses
    ``economic_rules.faction_initial_treasury`` (single source of truth).

    ``Config`` legitimately falls back to built-in defaults for an absent config
    path, so a non-existent path is treated as ``None`` (same effective value,
    no spurious warning).
    """
    if config_path and not Path(config_path).is_file():
        config_path = None
    cfg = Config(config_path)
    return int(cfg.get("economic_rules.faction_initial_treasury", 10))


def _require_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ScenarioValidationError(f"{label} must be an integer")
    return value


def validate_scenario_data(
    config: Any,
    *,
    scenario_file: Optional[str] = None,
    config_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Validate an already-parsed scenario object (no file I/O). Fail-closed.

    Returns a preflight report. Raises :class:`ScenarioValidationError` on any
    illegal shape/value.
    """
    if not isinstance(config, dict):
        raise ScenarioValidationError("scenario root must be a JSON object")

    initial = config.get("initial_state")
    if not isinstance(initial, dict):
        raise ScenarioValidationError("scenario requires an 'initial_state' object")

    # Explicit player records are unsupported: controllers are derived 1:1 from factions.
    if "players" in config or "players" in initial:
        raise ScenarioValidationError(
            "explicit player records are not supported; controllers are derived 1:1 from factions")

    factions = initial.get("factions")
    if not isinstance(factions, list):
        raise ScenarioValidationError("'initial_state.factions' must be a list")
    faction_count = len(factions)
    if not (MIN_FACTIONS <= faction_count <= MAX_FACTIONS):
        raise ScenarioValidationError(
            f"faction count must be {MIN_FACTIONS}..{MAX_FACTIONS}, got {faction_count}")

    # Permitted economic values.
    if "treasury" in initial:
        national = initial["treasury"]
        if isinstance(national, bool) or not isinstance(national, (int, float)) or national < 0:
            raise ScenarioValidationError(
                "'initial_state.treasury' must be a nonnegative number")

    # Start year / seed (legality only; seed scope is reported, not asserted effective).
    if "start_year" in config:
        _require_int(config["start_year"], "start_year")
    if "random_seed" in initial:
        _require_int(initial["random_seed"], "random_seed")

    effective = effective_faction_treasury(config_path)

    seen_faction_ids = set()
    seen_player_ids = set()
    faction_rows = []
    human_count = 0
    ai_count = 0

    for index, fac in enumerate(factions):
        if not isinstance(fac, dict):
            raise ScenarioValidationError(f"faction #{index} must be an object")

        fid = fac.get("id")
        if not isinstance(fid, str) or not fid.strip():
            raise ScenarioValidationError(
                f"faction #{index} requires a non-empty string id")
        if fid in seen_faction_ids:
            raise ScenarioValidationError(f"duplicate faction_id {fid!r}")
        seen_faction_ids.add(fid)

        fname = fac.get("name")
        if not isinstance(fname, str) or not fname.strip():
            raise ScenarioValidationError(
                f"faction {fid!r} requires a non-empty string name")

        if "is_player" not in fac:
            raise ScenarioValidationError(f"faction {fid!r} requires 'is_player'")
        is_player = fac["is_player"]
        if not isinstance(is_player, bool):
            raise ScenarioValidationError(
                f"faction {fid!r} 'is_player' must be a boolean, got {type(is_player).__name__}")

        declared_treasury = None
        if "treasury" in fac:
            declared_treasury = fac["treasury"]
            if (isinstance(declared_treasury, bool)
                    or not isinstance(declared_treasury, (int, float))
                    or declared_treasury < 0):
                raise ScenarioValidationError(
                    f"faction {fid!r} 'treasury' must be a nonnegative number")

        player_id = f"player_{fid}"
        if player_id in seen_player_ids:
            raise ScenarioValidationError(f"duplicate derived player_id {player_id!r}")
        seen_player_ids.add(player_id)

        controller = CONTROLLER_HUMAN if is_player else CONTROLLER_AI
        if is_player:
            human_count += 1
        else:
            ai_count += 1
        faction_rows.append({
            "id": fid,
            "name": fname,
            "controller": controller,
            "player_id": player_id,
            "declared_treasury_ignored": declared_treasury,
            "effective_treasury": effective,
        })

    # Fail-closed: at least one HUMAN seat is required (spec MVP0.7-12 §2.2).
    if human_count < MIN_HUMANS:
        raise ScenarioValidationError(
            f"scenario must declare at least {MIN_HUMANS} HUMAN player(s) "
            f"(GUI requires >=1 HUMAN, MVP0.7-12 §2.2); got {human_count} "
            f"HUMAN / {ai_count} AI")

    # Figure-generation schema (counts/ages).
    per_faction: Dict[str, Any] = {}
    figure_generation = initial.get("figure_generation")
    if figure_generation is not None:
        if not isinstance(figure_generation, dict):
            raise ScenarioValidationError("'figure_generation' must be an object")
        per = figure_generation.get("per_faction", {})
        if not isinstance(per, dict):
            raise ScenarioValidationError("'figure_generation.per_faction' must be an object")
        for tier, spec in per.items():
            if not isinstance(spec, dict):
                raise ScenarioValidationError(
                    f"figure_generation.per_faction[{tier!r}] must be an object")
            if "count" in spec:
                count = spec["count"]
                if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                    raise ScenarioValidationError(
                        f"figure count[{tier!r}] must be a nonnegative integer")
            if "age_range" in spec:
                age_range = spec["age_range"]
                ok = (
                    isinstance(age_range, (list, tuple))
                    and len(age_range) == 2
                    and all(isinstance(v, int) and not isinstance(v, bool) and v >= 0
                            for v in age_range)
                    and age_range[0] <= age_range[1]
                )
                if not ok:
                    raise ScenarioValidationError(
                        f"age_range[{tier!r}] must be [min, max] nonnegative ints, min<=max")
            per_faction[tier] = dict(spec)

    return {
        "scenario_file": scenario_file,
        "faction_count": faction_count,
        "human_count": human_count,
        "ai_count": ai_count,
        "factions": faction_rows,
        "player_ids": sorted(seen_player_ids),
        "controller_bijection": True,
        "min_humans": MIN_HUMANS,
        "human_required": human_count >= MIN_HUMANS,
        "effective_faction_treasury": effective,
        "effective_economy_note": (
            "per-faction 'treasury' is ignored by ScenarioLoader; effective value comes "
            "from economic_rules.faction_initial_treasury"),
        "start_year": config.get("start_year"),
        "random_seed": initial.get("random_seed"),
        "national_treasury": initial.get("treasury"),
        "figure_generation": per_faction,
    }


def prepare_selected_scenario(
    scenario_file: str,
    *,
    config_path: Optional[str] = None,
) -> ValidatedScenarioSnapshot:
    """Resolve, capture ONCE, parse + validate a selected scenario. Fail-closed.

    This is the single source of a GUI scenario selection: it resolves the approved
    canonical name, reads the selected file bytes exactly once, parses and validates
    that capture, and returns a recursively immutable
    :class:`ValidatedScenarioSnapshot` whose configuration and report are both derived
    from the same bytes. Raises :class:`ScenarioValidationError` on resolution / read /
    decode / JSON / schema / resource failure; it never substitutes a default scenario.

    No GameState / session is created or mutated here.
    """
    # Canonical resolution (bare filename under the approved directory; raises if
    # illegal or if the file is missing).
    path = resolve_scenario_path(scenario_file)

    # Resources the loader requires (checked before capture, fail-closed).
    provinces_path = _product_root() / "data" / "cards" / "provinces.json"
    if not provinces_path.is_file():
        raise ScenarioValidationError(f"required card file missing: {provinces_path.name}")
    # NOTE: game config is OPTIONAL — Config legitimately falls back to built-in
    # defaults when the path is absent (historical behaviour, e.g. callers that pass
    # a phase name positionally). The effective economy is reported from the
    # resolved config in validate_scenario_data.

    # ---- exact single byte capture ----
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ScenarioValidationError(
            f"scenario unreadable: {scenario_file}: {exc}") from exc
    try:
        config = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ScenarioValidationError(f"invalid JSON in {scenario_file}: {exc}") from exc

    report = validate_scenario_data(
        config, scenario_file=path.name, config_path=config_path)
    report["path"] = str(path)
    report["sha256"] = hashlib.sha256(raw).hexdigest()
    report["size_bytes"] = len(raw)

    snapshot = ValidatedScenarioSnapshot(
        path.name, path, raw, config, report, _issuer=_MINT_TOKEN)
    _ISSUED_SNAPSHOTS.add(snapshot)
    return snapshot


def preflight_scenario(
    scenario_file: str,
    *,
    config_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Detached, mutable preflight report (report-only compatibility entry).

    Delegates to :func:`prepare_selected_scenario` and returns a fresh mutable copy of
    the report. No GameState / session is created or mutated here. Raises
    :class:`ScenarioValidationError` for any illegal selection.
    """
    snapshot = prepare_selected_scenario(scenario_file, config_path=config_path)
    return snapshot.report_copy()
