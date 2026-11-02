"""Lecture d'un projet (``hocnota.toml``) et construction du manifeste.

    [package]
    name = "catalogue-produits"
    version = "1.0.0"
    description = "Catalogue de pièces détachées"
    source = "src"                                  # dossier contenant les packages Python
    modules = ["catalogue_produits.etl", "catalogue_produits.outils"]
    instructions = "instructions.md"                # optionnel
    dependencies = ["openpyxl>=3.1"]                # PUR Python uniquement

    [[inputs]]
    name = "catalogue"
    accept = [".xlsx"]
    filename_pattern = "catalogue"

    [[artifacts]]
    name = "produits"
    kind = "sqlite"
    filename = "produits.db"
    schema_version = 1
    seed = "seed/produits.db"                       # chemin dans le projet, optionnel

Les étapes, les outils et les contrôles de document ne se déclarent pas ici : ils
sont découverts par leurs décorateurs dans ``modules``.
"""

import importlib
import inspect
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from hocnota_scripts.api import CHECK_ATTR, STEP_ATTR, TOOL_ATTR
from hocnota_scripts.rules import FORMAT, ManifestError, validate_manifest
from hocnota_scripts.schema_infer import infer_input_schema, summary

CONFIG = "hocnota.toml"


class ProjectError(Exception):
    pass


@dataclass
class Project:
    root: Path
    config: dict
    manifest: dict = field(default_factory=dict)
    seeds: dict[str, Path] = field(default_factory=dict)  # chemin dans l'archive → fichier local

    @property
    def package(self) -> dict:
        return self.config["package"]

    @property
    def source_dir(self) -> Path:
        return self.root / self.package.get("source", "src")

    @property
    def dependencies(self) -> list[str]:
        return list(self.package.get("dependencies", []))

    @property
    def instructions_path(self) -> Path | None:
        name = self.package.get("instructions")
        return self.root / name if name else None

    @property
    def archive_name(self) -> str:
        return f"{self.package['name']}-{self.package['version']}.hnpkg"


def _discover(project: Project) -> tuple[list[dict], list[dict], list[dict]]:
    src = str(project.source_dir.resolve())
    if src not in sys.path:
        sys.path.insert(0, src)
    steps, tools, checks = [], [], []
    for module_name in project.package.get("modules", []):
        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:
            raise ProjectError(f"module {module_name} introuvable : {exc}") from exc
        for attr, func in inspect.getmembers(module, inspect.isfunction):
            if func.__module__ != module_name:
                continue  # importé d'ailleurs : compté dans son propre module
            entry = f"{module_name}:{func.__name__}"
            if hasattr(func, STEP_ATTR):
                opts = getattr(func, STEP_ATTR)
                step = {
                    "name": opts["name"] or func.__name__,
                    "entry": entry,
                    "inputs": opts["inputs"] or [],
                    "outputs": opts["outputs"] or [],
                }
                if opts["description"] or summary(func.__doc__):
                    step["description"] = opts["description"] or summary(func.__doc__)
                if opts["timeout_s"]:
                    step["timeout_s"] = opts["timeout_s"]
                steps.append((func.__code__.co_firstlineno, module_name, step))
            if hasattr(func, TOOL_ATTR):
                opts = getattr(func, TOOL_ATTR)
                tool = {
                    "name": opts["name"] or func.__name__,
                    "description": opts["description"] or summary(func.__doc__),
                    "entry": entry,
                    "input_schema": opts["input_schema"] or infer_input_schema(func),
                    "artifacts": opts["artifacts"] or [],
                }
                for key in ("timeout_s", "max_output_chars"):
                    if opts[key]:
                        tool[key] = opts[key]
                tools.append((func.__code__.co_firstlineno, module_name, tool))
            if hasattr(func, CHECK_ATTR):
                opts = getattr(func, CHECK_ATTR)
                check = {
                    "name": opts["name"] or func.__name__,
                    "entry": entry,
                    "accept": opts["accept"] or [],
                    "artifacts": opts["artifacts"] or [],
                }
                if opts["description"] or summary(func.__doc__):
                    check["description"] = opts["description"] or summary(func.__doc__)
                if opts["filename_pattern"]:
                    check["filename_pattern"] = opts["filename_pattern"]
                if opts["timeout_s"]:
                    check["timeout_s"] = opts["timeout_s"]
                checks.append((func.__code__.co_firstlineno, module_name, check))
    # Ordre stable : ordre des modules déclarés, puis ordre dans le fichier —
    # les étapes et les contrôles s'exécutent dans cet ordre.
    order = {m: i for i, m in enumerate(project.package.get("modules", []))}
    for found in (steps, tools, checks):
        found.sort(key=lambda t: (order[t[1]], t[0]))
    return [s for _, _, s in steps], [t for _, _, t in tools], [c for _, _, c in checks]


def load_project(root: Path | str = ".") -> Project:
    root = Path(root).resolve()
    path = root / CONFIG
    if not path.is_file():
        raise ProjectError(f"{CONFIG} introuvable dans {root}")
    config = tomllib.loads(path.read_text(encoding="utf-8"))
    if "package" not in config:
        raise ProjectError(f"{CONFIG} : section [package] manquante")
    project = Project(root=root, config=config)
    pkg = project.package

    artifacts = []
    for art in config.get("artifacts", []):
        art = dict(art)
        seed = art.pop("seed", None)
        if seed:
            local = root / seed
            if not local.is_file():
                raise ProjectError(f"seed introuvable : {seed}")
            art["seed"] = f"seed/{local.name}"
            project.seeds[art["seed"]] = local
        artifacts.append(art)

    steps, tools, checks = _discover(project)
    manifest = {
        "format": FORMAT,
        "runtime": {"python": "3.12"},
        "name": pkg.get("name"),
        "version": pkg.get("version"),
        "description": pkg.get("description", ""),
        "inputs": [dict(i) for i in config.get("inputs", [])],
        "artifacts": artifacts,
        "steps": steps,
        "tools": tools,
        "checks": checks,
    }
    if project.instructions_path:
        if not project.instructions_path.is_file():
            raise ProjectError(f"instructions introuvables : {pkg['instructions']}")
        manifest["instructions"] = project.instructions_path.name
    try:
        project.manifest = validate_manifest(manifest)
    except ManifestError as exc:
        raise ProjectError("manifeste invalide :\n  - " + "\n  - ".join(exc.errors)) from exc
    return project
