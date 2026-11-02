"""Ligne de commande ``hocnota-scripts``.

    hocnota-scripts init mon-paquet                      # nouveau projet
    hocnota-scripts validate                             # manifeste + règles du format
    hocnota-scripts run-step --input classeur=fichier.xlsx   # → build/artifacts/
    hocnota-scripts call lire_lignes '{"limite": 3}'     # appel d'outil (JSON)
    hocnota-scripts test                                 # rejoue tests/golden.jsonl
    hocnota-scripts build                                # → dist/<nom>-<version>.hnpkg
    hocnota-scripts inspect dist/x.hnpkg                 # résumé d'une archive

``--sandbox`` (run-step, call, test) exécute dans ``python:3.12-slim`` sans
réseau, comme le bac à sable de HocNota.
"""

import argparse
import io
import json
import re
import sys
import zipfile
from pathlib import Path

from hocnota_scripts.project import ProjectError, load_project

TEMPLATES = Path(__file__).with_name("templates") / "projet"


def _pairs(values: list[str] | None, flag: str) -> dict[str, Path]:
    out = {}
    for item in values or []:
        if "=" not in item:
            raise ProjectError(f"{flag} attend nom=chemin, reçu « {item} »")
        name, path = item.split("=", 1)
        if not Path(path).is_file():
            raise ProjectError(f"fichier introuvable : {path}")
        out[name] = Path(path).resolve()
    return out


def cmd_init(args) -> int:
    from hocnota_scripts import __version__

    target = Path(args.directory).resolve()
    if target.exists() and any(target.iterdir()):
        raise ProjectError(f"{target} existe et n'est pas vide")
    name = target.name.lower()
    if not re.match(r"^[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?$", name):
        raise ProjectError("nom de dossier attendu en minuscules, chiffres et tirets (ex. catalogue-produits)")
    module = name.replace("-", "_")
    for src in sorted(TEMPLATES.rglob("*")):
        if not src.is_file():
            continue
        rel = Path(str(src.relative_to(TEMPLATES)).replace("__module__", module).removesuffix(".tpl"))
        if rel.name == "gitignore":  # un .gitignore dans le paquet pip serait ignoré par setuptools
            rel = rel.with_name(".gitignore")
        dst = target / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        text = (src.read_text(encoding="utf-8").replace("{{name}}", name).replace("{{module}}", module)
                .replace("{{sdk_version}}", __version__))
        dst.write_text(text, encoding="utf-8")
    print(f"Projet créé dans {target}")
    print("Ensuite : cd", target.name, "&& pip install -r requirements-dev.txt && hocnota-scripts validate")
    return 0


def cmd_validate(args) -> int:
    project = load_project(args.project)
    m = project.manifest
    print(f"{m['name']} {m['version']} — format {m['format']} : valide")
    for kind in ("inputs", "artifacts", "steps", "tools"):
        names = ", ".join(i["name"] for i in m[kind]) or "—"
        print(f"  {kind:<10} {names}")
    return 0


def cmd_run_step(args) -> int:
    from hocnota_scripts.local_run import run_steps
    project = load_project(args.project)
    result, stderr = run_steps(project, _pairs(args.input, "--input"),
                               Path(args.out) if args.out else None, sandbox=args.sandbox)
    if stderr.strip():
        print(stderr.rstrip(), file=sys.stderr)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def cmd_call(args) -> int:
    from hocnota_scripts.local_run import call_tool
    project = load_project(args.project)
    try:
        tool_args = json.loads(args.arguments or "{}")
    except json.JSONDecodeError as exc:
        raise ProjectError(f"arguments JSON invalides : {exc}")
    result, stderr = call_tool(project, args.tool, tool_args, _pairs(args.artifact, "--artifact"),
                               sandbox=args.sandbox)
    if stderr.strip():
        print(stderr.rstrip(), file=sys.stderr)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    tool = next((t for t in project.manifest["tools"] if t["name"] == args.tool), None)
    if tool and result.get("ok"):
        size = len(json.dumps(result["result"], ensure_ascii=False))
        if size > tool["max_output_chars"]:
            print(f"⚠ sortie de {size} caractères : HocNota la tronquera à {tool['max_output_chars']}",
                  file=sys.stderr)
    return 0 if result.get("ok") else 1


def cmd_test(args) -> int:
    from hocnota_scripts.golden import run_golden
    project = load_project(args.project)
    path = Path(args.file) if args.file else project.root / "tests" / "golden.jsonl"
    if not path.is_file():
        raise ProjectError(f"jeu de référence introuvable : {path}")
    report = run_golden(project, path, sandbox=args.sandbox)
    failed = 0
    for case_id, diffs in report:
        print(("✔ " if not diffs else "✘ ") + case_id)
        for d in diffs:
            print("    " + d)
        failed += bool(diffs)
    print(f"{len(report) - failed}/{len(report)} réussis")
    return 1 if failed else 0


def cmd_build(args) -> int:
    from hocnota_scripts.build import build
    project = load_project(args.project)
    out = build(project, Path(args.out) if args.out else None, refresh=args.refresh)
    print(f"{out} ({out.stat().st_size / 1e6:.2f} Mo)")
    return 0


def cmd_inspect(args) -> int:
    data = Path(args.archive).read_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        names = zf.namelist()
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    for top in ("pkg/", "vendor/", "seed/"):
        print(f"{top:<8} {sum(n.startswith(top) for n in names)} fichier(s)")
    print(f"taille   {len(data) / 1e6:.2f} Mo")
    return 0


def main(argv: list[str] | None = None) -> int:
    from hocnota_scripts import __version__
    from hocnota_scripts.rules import FORMAT

    parser = argparse.ArgumentParser(prog="hocnota-scripts", description=__doc__.split("\n\n")[0])
    parser.add_argument("--version", action="version",
                        version=f"hocnota-scripts {__version__} (format {FORMAT})")
    sub = parser.add_subparsers(dest="command", required=True)

    def with_project(p):
        p.add_argument("--project", default=".", help="dossier du projet (défaut : .)")
        return p

    p = sub.add_parser("init", help="crée un projet")
    p.add_argument("directory")
    p.set_defaults(func=cmd_init)

    with_project(sub.add_parser("validate", help="valide le manifeste")).set_defaults(func=cmd_validate)

    p = with_project(sub.add_parser("run-step", help="exécute les étapes d'import"))
    p.add_argument("--input", action="append", metavar="NOM=FICHIER")
    p.add_argument("--out", help="dossier des artefacts (défaut : build/artifacts)")
    p.add_argument("--sandbox", action="store_true")
    p.set_defaults(func=cmd_run_step)

    p = with_project(sub.add_parser("call", help="appelle un outil"))
    p.add_argument("tool")
    p.add_argument("arguments", nargs="?", help="arguments JSON")
    p.add_argument("--artifact", action="append", metavar="NOM=FICHIER")
    p.add_argument("--sandbox", action="store_true")
    p.set_defaults(func=cmd_call)

    p = with_project(sub.add_parser("test", help="rejoue le jeu de référence"))
    p.add_argument("file", nargs="?")
    p.add_argument("--sandbox", action="store_true")
    p.set_defaults(func=cmd_test)

    p = with_project(sub.add_parser("build", help="construit l'archive .hnpkg"))
    p.add_argument("--out")
    p.add_argument("--refresh", action="store_true", help="re-télécharge les dépendances")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("inspect", help="résume une archive")
    p.add_argument("archive")
    p.set_defaults(func=cmd_inspect)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ProjectError as exc:
        print(f"erreur : {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
