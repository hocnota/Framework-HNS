"""Exécution locale d'une étape, d'un outil ou d'un contrôle de document, avec le lanceur de HocNota.

Le répertoire de travail est organisé exactement comme le fait HocNota pour le
bac à sable (``launcher.py``, ``package.hnpkg`` sans seeds, ``in/``, ``art/``) :
ce qui passe ici passe dans HocNota, aux différences d'environnement près —
que l'option ``sandbox`` supprime en exécutant dans ``python:3.12-slim`` sans
réseau, système de fichiers en lecture seule et mêmes plafonds.
"""

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from hocnota_scripts import _launcher_v1
from hocnota_scripts.build import build_archive, vendor_dependencies
from hocnota_scripts.project import Project

SANDBOX_IMAGE = "python:3.12-slim"


def _prepare(project: Project, workdir: Path, inputs: dict[str, Path], artifacts: dict[str, Path]) -> dict:
    shutil.copy(_launcher_v1.__file__, workdir / "launcher.py")
    archive = build_archive(project, with_seeds=False, vendor_dir=vendor_dependencies(project))
    (workdir / "package.hnpkg").write_bytes(archive)
    request: dict = {"inputs": {}, "artifacts": {}}
    for name, src in inputs.items():
        rel = Path("in") / name / Path(src).name
        (workdir / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, workdir / rel)
        request["inputs"][name] = rel.as_posix()
    by_name = {a["name"]: a for a in project.manifest["artifacts"]}
    for name, src in artifacts.items():
        rel = Path("art") / by_name[name]["filename"]
        (workdir / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, workdir / rel)
        request["artifacts"][name] = rel.as_posix()
    return request


def _launch(workdir: Path, argv: list[str], request: dict, timeout_s: int, sandbox: bool) -> tuple[dict, str]:
    if sandbox:
        cmd = [
            "docker", "run", "--rm", "-i", "--network", "none", "--read-only",
            "--tmpfs", "/tmp:size=128m,noexec", "--memory", "512m", "--cpus", "1",
            "--user", "1000:1000", "-v", f"{workdir}:/work", "-w", "/work",
            SANDBOX_IMAGE, "python3", "launcher.py", *argv,
        ]
    else:
        cmd = [sys.executable, "-I", "launcher.py", *argv]
    try:
        proc = subprocess.run(cmd, cwd=workdir, input=json.dumps(request), capture_output=True,
                              text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"délai dépassé ({timeout_s} s)"}, ""
    result_file = workdir / "output" / "result.json"
    if not result_file.is_file():
        return {"ok": False, "error": "aucun résultat (le processus a été tué ?)"}, proc.stderr
    return json.loads(result_file.read_text(encoding="utf-8")), proc.stderr


def default_artifacts(project: Project, artifacts: dict[str, Path]) -> dict[str, Path]:
    """Artefacts explicites, sinon dernière construction locale, sinon seed."""
    out = dict(artifacts)
    for art in project.manifest["artifacts"]:
        if art["name"] in out:
            continue
        built = project.root / "build" / "artifacts" / art["filename"]
        if built.is_file():
            out[art["name"]] = built
        elif art.get("seed"):
            out[art["name"]] = project.seeds[art["seed"]]
    return out


def run_steps(project: Project, inputs: dict[str, Path], out_dir: Path | None = None,
              *, sandbox: bool = False) -> tuple[dict, str]:
    out_dir = out_dir or project.root / "build" / "artifacts"
    timeout = sum(s["timeout_s"] for s in project.manifest["steps"]) + 10
    with tempfile.TemporaryDirectory(prefix="hnrun_") as tmp:
        workdir = Path(tmp)
        request = _prepare(project, workdir, inputs, {})
        result, stderr = _launch(workdir, ["step"], request, timeout, sandbox)
        if result.get("ok"):
            out_dir.mkdir(parents=True, exist_ok=True)
            for name, rel in result["artifacts"].items():
                shutil.copy(workdir / rel, out_dir / Path(rel).name)
                result["artifacts"][name] = str(out_dir / Path(rel).name)
            (out_dir / "meta.json").write_text(json.dumps(result.get("meta", {}), ensure_ascii=False, indent=2))
    return result, stderr


def call_tool(project: Project, name: str, args: dict, artifacts: dict[str, Path] | None = None,
              *, sandbox: bool = False) -> tuple[dict, str]:
    tool = next((t for t in project.manifest["tools"] if t["name"] == name), None)
    if tool is None:
        return {"ok": False, "error": f"outil inconnu : {name}"}, ""
    # HocNota valide les arguments contre le schéma AVANT d'appeler le bac à sable.
    import jsonschema
    try:
        jsonschema.validate(args, tool["input_schema"])
    except jsonschema.ValidationError as exc:
        return {"ok": False, "error": f"arguments invalides : {exc.message}"}, ""
    arts = {k: v for k, v in default_artifacts(project, artifacts or {}).items() if k in tool["artifacts"]}
    with tempfile.TemporaryDirectory(prefix="hnrun_") as tmp:
        workdir = Path(tmp)
        request = _prepare(project, workdir, {}, arts)
        request["args"] = args
        return _launch(workdir, ["tool", name], request, tool["timeout_s"] + 10, sandbox)


def matching_checks(project: Project, filename: str) -> list[dict]:
    """Les contrôles que HocNota exécuterait pour ce fichier : même règle
    (extension acceptée, motif de nom facultatif), même ordre."""
    ext = Path(filename).suffix.lower()
    out = []
    for check in project.manifest["checks"]:
        if ext not in check["accept"]:
            continue
        pattern = check.get("filename_pattern")
        if pattern and not re.search(pattern, filename, re.IGNORECASE):
            continue
        out.append(check)
    return out


def run_check(project: Project, document: Path, artifacts: dict[str, Path] | None = None,
              *, sandbox: bool = False) -> tuple[dict, str]:
    """Contrôle ``document`` comme le ferait un nœud HNS placé sur le flux du document.

    Renvoie l'enveloppe du lanceur : ``{"ok": True, "rejected": bool, "message": …,
    "meta": {…}}``, ou ``{"ok": False, "error": …}`` (contrôle impossible).
    ``{"ok": True, "skipped": True}`` quand aucun contrôle n'accepte ce fichier.
    """
    selected = matching_checks(project, Path(document).name)
    if not selected:
        return {"ok": True, "skipped": True, "rejected": False, "message": None, "meta": {}, "checks": []}, ""
    wanted = {a for c in selected for a in c["artifacts"]}
    arts = {k: v for k, v in default_artifacts(project, artifacts or {}).items() if k in wanted}
    missing = sorted(wanted - set(arts))
    if missing:
        return {"ok": False, "error": f"aucune donnée « {missing[0]} » disponible pour ce contrôle "
                                      "(lancez run-step, ou passez --artifact)"}, ""
    with tempfile.TemporaryDirectory(prefix="hnrun_") as tmp:
        workdir = Path(tmp)
        request = _prepare(project, workdir, {"document": Path(document)}, arts)
        request["checks"] = [c["name"] for c in selected]
        timeout = min(sum(c["timeout_s"] for c in selected), 60) + 10
        return _launch(workdir, ["check"], request, timeout, sandbox)
