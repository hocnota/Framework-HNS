"""Sandbox-side launcher for script packages — protocol 1.

This file is sent AS-IS to the skill-runner as the run's entrypoint; it never
comes from the package archive, so the HocNota ↔ sandbox protocol cannot be
altered by a package. It must therefore stay standard-library only and
importable on its own (no ``app.*`` import).

Workdir laid out by HocNota (app/script_packages/runner.py):

    launcher.py          this file
    package.hnpkg        the package archive, extracted here into _pkg/
    in/<input>/<file>    step inputs (e.g. the Excel attached to the chat)
    art/<filename>       artifacts a tool reads (e.g. data.db)

Invocation:  ``python3 launcher.py step``, ``python3 launcher.py tool <name>``
             or ``python3 launcher.py check``
stdin:       ``{"args": {...}, "inputs": {name: path}, "artifacts": {name: path}}``
             (``check`` also takes ``"checks": [names]`` and the document as
             input ``document``)
Result:      ``output/result.json`` — never stdout, which package code may
             print to. Step outputs land in ``output/artifacts/<filename>``.

The checks here are a courtesy to package authors (clear errors): the launcher
runs in the same process as package code, so HocNota enforces every real limit
on its side after the run.
"""

import contextlib
import datetime
import importlib
import json
import sqlite3
import sys
import traceback
import types
import zipfile
from pathlib import Path, PurePosixPath

LAUNCHER_PROTOCOL = 1

ARCHIVE = "package.hnpkg"
EXTRACT_DIR = "_pkg"
OUTPUT_DIR = Path("output")
OUTPUT_ARTIFACTS = OUTPUT_DIR / "artifacts"
RESULT_FILE = OUTPUT_DIR / "result.json"

_MAX_EXTRACT_BYTES = 256 * 1024 * 1024


class PackageError(Exception):
    """An error the package author should read as-is (no traceback)."""


class Reject(Exception):
    """Raised by a document check to refuse the document. The message is what
    the pipeline's error exit tells the user — write it for them."""


# ── The ``hocnota_scripts`` module seen by package code ──────────────────────
# Package code imports its decorators from the SDK. The SDK is not installed in
# the sandbox, so the launcher provides the runtime half: decorators that just
# return the function (the manifest, built by the SDK, already says what is a
# step or a tool) and the Context object handed to every call.

def _passthrough_decorator(*args, **kwargs):
    if len(args) == 1 and callable(args[0]) and not kwargs:
        return args[0]
    return lambda fn: fn


class Context:
    """What a step or a tool receives as its first argument."""

    def __init__(self, inputs: dict, artifacts: dict, outputs: dict):
        self._inputs = {k: Path(v) for k, v in (inputs or {}).items() if v}
        self._artifacts = {k: Path(v) for k, v in (artifacts or {}).items() if v}
        self._outputs = outputs

    def input_path(self, name: str):
        """Path of a step input, or None when no file was provided."""
        return self._inputs.get(name)

    def output_path(self, name: str) -> Path:
        """Where a step must write the artifact ``name``."""
        if name not in self._outputs:
            raise PackageError(f"« {name} » n'est pas une sortie de cette étape")
        path = self._outputs[name]
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def artifact_path(self, name: str) -> Path:
        """Path of an artifact to read: produced earlier in this run, else provided."""
        produced = self._outputs.get(name)
        if produced is not None and produced.exists():
            return produced
        if name not in self._artifacts:
            raise PackageError(f"artefact « {name} » non disponible")
        return self._artifacts[name]

    def sqlite(self, name: str, row_factory=None) -> sqlite3.Connection:
        """Read-only connection to a SQLite artifact."""
        path = self.artifact_path(name).resolve()
        conn = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
        if row_factory is not None:
            conn.row_factory = row_factory
        return conn

    def log(self, message) -> None:
        print(str(message), file=sys.stderr)


def _install_sdk_stub() -> None:
    mod = types.ModuleType("hocnota_scripts")
    mod.step = _passthrough_decorator
    mod.tool = _passthrough_decorator
    mod.check = _passthrough_decorator
    mod.Context = Context
    mod.Reject = Reject
    mod.InputFile = Path
    mod.LAUNCHER_PROTOCOL = LAUNCHER_PROTOCOL
    sys.modules["hocnota_scripts"] = mod


# ── Package extraction ───────────────────────────────────────────────────────

def _extract(archive: Path, target: Path) -> None:
    total = 0
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            parts = PurePosixPath(name).parts
            if name.startswith("/") or ".." in parts:
                raise PackageError(f"chemin interdit dans l'archive : {name}")
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise PackageError(f"lien symbolique interdit dans l'archive : {name}")
            total += info.file_size
            if total > _MAX_EXTRACT_BYTES:
                raise PackageError("archive trop volumineuse une fois décompressée")
        zf.extractall(target)


def _load_entry(entry: str):
    module_name, func_name = entry.split(":", 1)
    module = importlib.import_module(module_name)
    func = getattr(module, func_name, None)
    if not callable(func):
        raise PackageError(f"point d'entrée introuvable : {entry}")
    return func


def _jsonable(value):
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _finalise_sqlite(path: Path) -> None:
    """Fold any WAL into the main file: HocNota stores a single file."""
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.execute("PRAGMA journal_mode=DELETE")
    finally:
        conn.close()


# ── Modes ────────────────────────────────────────────────────────────────────

def run_steps(manifest: dict, request: dict) -> dict:
    artifacts = {a["name"]: a for a in manifest.get("artifacts", [])}
    inputs = request.get("inputs") or {}
    provided = request.get("artifacts") or {}
    for spec in manifest.get("inputs", []):
        if spec.get("required") and not inputs.get(spec["name"]):
            raise PackageError(f"entrée obligatoire manquante : {spec['name']}")

    outputs = {name: OUTPUT_ARTIFACTS / art["filename"] for name, art in artifacts.items()}
    meta: dict = {}
    produced: set[str] = set()
    for step in manifest.get("steps", []):
        ctx = Context(inputs, provided, {k: outputs[k] for k in step["outputs"]})
        func = _load_entry(step["entry"])
        kwargs = {name: ctx.input_path(name) for name in step.get("inputs", [])}
        returned = func(ctx, **kwargs)
        if returned is not None:
            if not isinstance(returned, dict):
                raise PackageError(f"l'étape {step['name']} doit renvoyer un dict ou None")
            meta.update(_jsonable(returned))
        for name in step["outputs"]:
            if not outputs[name].is_file():
                raise PackageError(f"l'étape {step['name']} n'a pas produit « {name} »")
            produced.add(name)

    for name in produced:
        if artifacts[name]["kind"] == "sqlite":
            _finalise_sqlite(outputs[name])
    return {
        "ok": True,
        "meta": meta,
        "artifacts": {name: str(outputs[name]) for name in sorted(produced)},
    }


def _coerce_dates(schema: dict, args: dict) -> dict:
    """JSON has no date type: ``format: date`` strings become ``datetime.date``,
    so package code annotated ``date`` receives what it declared."""
    props = (schema or {}).get("properties") or {}

    def conv(spec, value):
        if spec.get("format") == "date" and isinstance(value, str):
            try:
                return datetime.date.fromisoformat(value)
            except ValueError:
                raise PackageError(f"date invalide (attendu AAAA-MM-JJ) : {value}")
        return value

    out = dict(args)
    for name, value in args.items():
        spec = props.get(name) or {}
        if spec.get("type") == "array" and isinstance(value, list):
            out[name] = [conv(spec.get("items") or {}, v) for v in value]
        else:
            out[name] = conv(spec, value)
    return out


def run_tool(manifest: dict, request: dict, tool_name: str) -> dict:
    tool = next((t for t in manifest.get("tools", []) if t["name"] == tool_name), None)
    if tool is None:
        raise PackageError(f"outil inconnu : {tool_name}")
    ctx = Context({}, request.get("artifacts") or {}, {})
    func = _load_entry(tool["entry"])
    args = request.get("args") or {}
    if not isinstance(args, dict):
        raise PackageError("les arguments d'un outil doivent être un objet JSON")
    args = _coerce_dates(tool.get("input_schema") or {}, args)
    return {"ok": True, "result": _jsonable(func(ctx, **args))}


def run_checks(manifest: dict, request: dict) -> dict:
    """Run the named document checks in order on the document, until one rejects.

    A rejection is an outcome, not a failure: ``ok`` stays true and
    ``rejected`` carries the message. ``meta`` merges what the checks returned.
    """
    specs = {c["name"]: c for c in manifest.get("checks", [])}
    inputs = request.get("inputs") or {}
    if not inputs.get("document"):
        raise PackageError("document à contrôler manquant")
    ctx = Context(inputs, request.get("artifacts") or {}, {})
    document = ctx.input_path("document")
    meta: dict = {}
    done: list[dict] = []
    for name in request.get("checks") or []:
        spec = specs.get(name)
        if spec is None:
            raise PackageError(f"contrôle inconnu : {name}")
        func = _load_entry(spec["entry"])
        try:
            returned = func(ctx, document)
        except Reject as exc:
            done.append({"name": name, "status": "rejected"})
            return {"ok": True, "rejected": True, "message": str(exc), "meta": meta, "checks": done}
        if returned is not None:
            if not isinstance(returned, dict):
                raise PackageError(f"le contrôle {name} doit renvoyer un dict ou None")
            meta.update(_jsonable(returned))
        done.append({"name": name, "status": "ok"})
    return {"ok": True, "rejected": False, "message": None, "meta": meta, "checks": done}


def main(argv: list[str]) -> int:
    OUTPUT_DIR.mkdir(exist_ok=True)
    try:
        if (not argv or argv[0] not in ("step", "tool", "check")
                or (argv[0] == "tool" and len(argv) < 2)):
            raise PackageError("usage : launcher.py step | launcher.py tool <nom> | launcher.py check")
        request = json.loads(sys.stdin.read() or "{}")
        root = Path(EXTRACT_DIR)
        _extract(Path(ARCHIVE), root)
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        sys.path[:0] = [str((root / "pkg").resolve()), str((root / "vendor").resolve())]
        _install_sdk_stub()
        # Package code may print freely: stdout is not the result channel,
        # and whatever it prints is better read next to its tracebacks.
        with contextlib.redirect_stdout(sys.stderr):
            if argv[0] == "step":
                result = run_steps(manifest, request)
            elif argv[0] == "check":
                result = run_checks(manifest, request)
            else:
                result = run_tool(manifest, request, argv[1])
        code = 0
    except PackageError as exc:
        result, code = {"ok": False, "error": str(exc)}, 1
    except Exception as exc:  # noqa: BLE001 — reported to the caller, traceback on stderr
        traceback.print_exc(file=sys.stderr)
        result, code = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:2000]}, 1
    RESULT_FILE.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
