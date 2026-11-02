"""Manifest of a script package — format ``hocnota-package/1``.

Structure is checked against the canonical JSON Schema
(``schema/hocnota-package-1.json``, copied verbatim into the hocnota-scripts
SDK). What JSON Schema cannot say is checked here: cross-references between
inputs/steps/artifacts/tools, reserved tool names, and the portable subset a
tool's ``input_schema`` must stay within so every LLM provider accepts it.

The SDK runs the same rules at build time; HocNota re-runs them at import
because the archive comes from outside.
"""

import json
import re
from functools import lru_cache
from pathlib import Path

import jsonschema

FORMAT = "hocnota-package/1"
SCHEMA_PATH = Path(__file__).with_name("schema") / "hocnota-package-1.json"

# Sum of a package's step timeouts: the steps run in sequence inside ONE
# sandbox run, whose wall clock the runner caps at 120 s.
MAX_TOTAL_STEP_TIMEOUT_S = 120
DEFAULT_STEP_TIMEOUT_S = 60
# Document checks of a package run in sequence inside ONE sandbox run, on the
# tools lane (a job waits for them): same reasoning as the steps, tighter cap.
MAX_TOTAL_CHECK_TIMEOUT_S = 60
DEFAULT_CHECK_TIMEOUT_S = 30
DEFAULT_TOOL_TIMEOUT_S = 15
DEFAULT_MAX_OUTPUT_CHARS = 20_000
MAX_INSTRUCTIONS_CHARS = 8_000

# Tool names the agent loop already treats specially: skill tools, and the
# correspondence tools whose results are redacted BY NAME in logs and traces
# (mcp_agent._REDACTED_TOOLS) — a package tool sharing one would be silently
# redacted, or shadow the built-in.
_RESERVED_TOOL_NAMES = frozenset({
    "get_columns_by_value", "get_columns_by_search", "list_all",
    "check_spell", "check_spelling",
})
_RESERVED_TOOL_PREFIXES = ("skill_",)

# LangChain turns tool properties into keyword arguments; these collide with
# its own call machinery (see the `script_args` comment in skill_tools.py).
_FORBIDDEN_PROPERTIES = frozenset({"args", "callbacks", "run_manager", "config", "ctx"})
_PROPERTY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")

# Portable subset of JSON Schema for tool arguments. Gemini and several
# Ollama-served models reject $ref / oneOf / additionalProperties & co, and a
# tool the provider refuses breaks the whole agent turn, not just the tool.
_PRIMITIVES = frozenset({"string", "integer", "number", "boolean"})
_PROPERTY_KEYS = frozenset({
    "type", "description", "enum", "default", "items", "format",
    "minimum", "maximum", "minLength", "maxLength", "pattern", "minItems", "maxItems",
})
_ITEM_KEYS = frozenset({"type", "description", "enum", "format", "minimum", "maximum"})
_SCHEMA_KEYS = frozenset({"type", "properties", "required", "description"})


class ManifestError(ValueError):
    """The manifest is invalid. ``errors`` lists every problem found."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


@lru_cache(maxsize=1)
def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _schema_errors(data) -> list[str]:
    validator = jsonschema.Draft202012Validator(_schema())
    out = []
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in err.absolute_path) or "(racine)"
        out.append(f"{where} : {err.message}")
    return out


def _check_property(path: str, spec, errors: list[str]) -> None:
    if not isinstance(spec, dict):
        errors.append(f"{path} : doit être un objet")
        return
    extra = set(spec) - _PROPERTY_KEYS
    if extra:
        errors.append(f"{path} : mots-clés non portables {sorted(extra)}")
    ptype = spec.get("type")
    if ptype == "array":
        items = spec.get("items")
        if not isinstance(items, dict):
            errors.append(f"{path} : un tableau doit déclarer 'items'")
            return
        if set(items) - _ITEM_KEYS:
            errors.append(f"{path}/items : mots-clés non portables {sorted(set(items) - _ITEM_KEYS)}")
        if items.get("type") not in _PRIMITIVES:
            errors.append(f"{path}/items : seuls les tableaux de types simples sont acceptés")
    elif ptype not in _PRIMITIVES:
        errors.append(f"{path} : type '{ptype}' non pris en charge (string, integer, number, boolean, array)")
    elif "items" in spec:
        errors.append(f"{path} : 'items' réservé aux tableaux")
    if "enum" in spec and not (isinstance(spec["enum"], list) and spec["enum"]):
        errors.append(f"{path} : 'enum' doit être une liste non vide")


def check_input_schema(path: str, schema, errors: list[str]) -> None:
    """Append to ``errors`` every way ``schema`` leaves the portable subset."""
    if not isinstance(schema, dict):
        errors.append(f"{path} : doit être un objet")
        return
    extra = set(schema) - _SCHEMA_KEYS
    if extra:
        errors.append(f"{path} : mots-clés non portables {sorted(extra)}")
    if schema.get("type") != "object":
        errors.append(f"{path} : 'type' doit valoir 'object'")
    props = schema.get("properties", {})
    if not isinstance(props, dict):
        errors.append(f"{path}/properties : doit être un objet")
        return
    for name, spec in props.items():
        if not _PROPERTY_RE.match(name):
            errors.append(f"{path}/properties/{name} : nom de paramètre invalide")
        elif name in _FORBIDDEN_PROPERTIES:
            errors.append(f"{path}/properties/{name} : nom de paramètre réservé")
        _check_property(f"{path}/properties/{name}", spec, errors)
    required = schema.get("required", [])
    if not isinstance(required, list) or any(r not in props for r in required):
        errors.append(f"{path}/required : doit lister des propriétés déclarées")


def _dupes(items: list[dict]) -> list[str]:
    seen, dupes = set(), []
    for item in items:
        name = item.get("name")
        if name in seen:
            dupes.append(name)
        seen.add(name)
    return dupes


def validate_manifest(data) -> dict:
    """Return ``data`` with defaults filled in, or raise ManifestError.

    Defaults are written into the returned dict (a copy) so that everything
    downstream — storage, the executor, the UI — reads explicit values.
    """
    errors = _schema_errors(data)
    if errors:
        raise ManifestError(errors)

    m = json.loads(json.dumps(data))  # deep copy, JSON-only values
    m.setdefault("inputs", [])
    m.setdefault("artifacts", [])
    m.setdefault("steps", [])
    m.setdefault("tools", [])
    m.setdefault("checks", [])

    for section in ("inputs", "artifacts", "steps", "tools", "checks"):
        for name in _dupes(m[section]):
            errors.append(f"{section} : nom en double « {name} »")

    inputs = {i["name"] for i in m["inputs"]}
    artifacts = {a["name"]: a for a in m["artifacts"]}

    produced: set[str] = set()
    total_timeout = 0
    for i, step in enumerate(m["steps"]):
        step.setdefault("inputs", [])
        step.setdefault("timeout_s", DEFAULT_STEP_TIMEOUT_S)
        total_timeout += step["timeout_s"]
        for ref in step["inputs"]:
            if ref not in inputs:
                errors.append(f"steps/{i}/inputs : entrée inconnue « {ref} »")
        for ref in step["outputs"]:
            if ref not in artifacts:
                errors.append(f"steps/{i}/outputs : artefact inconnu « {ref} »")
            produced.add(ref)
    if total_timeout > MAX_TOTAL_STEP_TIMEOUT_S:
        errors.append(
            f"steps : la somme des timeout_s ({total_timeout} s) dépasse {MAX_TOTAL_STEP_TIMEOUT_S} s"
        )

    for inp in m["inputs"]:
        inp.setdefault("required", False)
        pattern = inp.get("filename_pattern")
        if pattern is not None:
            try:
                re.compile(pattern)
            except re.error:
                errors.append(f"inputs/{inp['name']} : filename_pattern n'est pas une expression régulière valide")

    for art in m["artifacts"]:
        art.setdefault("schema_version", 1)
        if art["name"] not in produced and not art.get("seed"):
            errors.append(
                f"artifacts/{art['name']} : ni produit par une étape ni fourni en seed — l'outil n'aurait jamais de données"
            )

    total_check_timeout = 0
    for i, check in enumerate(m["checks"]):
        check.setdefault("artifacts", [])
        check.setdefault("timeout_s", DEFAULT_CHECK_TIMEOUT_S)
        total_check_timeout += check["timeout_s"]
        for ref in check["artifacts"]:
            if ref not in artifacts:
                errors.append(f"checks/{i}/artifacts : artefact inconnu « {ref} »")
        pattern = check.get("filename_pattern")
        if pattern is not None:
            try:
                re.compile(pattern)
            except re.error:
                errors.append(f"checks/{check['name']} : filename_pattern n'est pas une expression régulière valide")
    if total_check_timeout > MAX_TOTAL_CHECK_TIMEOUT_S:
        errors.append(
            f"checks : la somme des timeout_s ({total_check_timeout} s) dépasse {MAX_TOTAL_CHECK_TIMEOUT_S} s"
        )

    for i, tool in enumerate(m["tools"]):
        name = tool["name"]
        if name in _RESERVED_TOOL_NAMES or name.startswith(_RESERVED_TOOL_PREFIXES):
            errors.append(f"tools/{i} : nom d'outil réservé « {name} »")
        tool.setdefault("artifacts", [])
        tool.setdefault("timeout_s", DEFAULT_TOOL_TIMEOUT_S)
        tool.setdefault("max_output_chars", DEFAULT_MAX_OUTPUT_CHARS)
        for ref in tool["artifacts"]:
            if ref not in artifacts:
                errors.append(f"tools/{i}/artifacts : artefact inconnu « {ref} »")
        check_input_schema(f"tools/{i}/input_schema", tool["input_schema"], errors)

    if errors:
        raise ManifestError(errors)
    return m


def entry_module_paths(entry: str) -> tuple[str, str]:
    """``pkg.mod:func`` → the two archive paths the module may live at."""
    module = entry.split(":", 1)[0].replace(".", "/")
    return f"pkg/{module}.py", f"pkg/{module}/__init__.py"
