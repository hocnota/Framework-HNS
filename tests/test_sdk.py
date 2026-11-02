import datetime
import io
import json
import os
import sqlite3
import sys
import zipfile
from pathlib import Path
from typing import Annotated, Literal, Optional

import pytest

from hocnota_scripts import cli
from hocnota_scripts.build import build, build_archive
from hocnota_scripts.golden import matches, run_golden
from hocnota_scripts.local_run import call_tool, run_steps
from hocnota_scripts.project import ProjectError, load_project
from hocnota_scripts.schema_infer import SchemaError, infer_input_schema, parse_docstring_args

EXEMPLE = Path(__file__).with_name("exemple")
HOCNOTA_REPO = os.getenv("HOCNOTA_REPO")


# ── Inférence de schéma ──────────────────────────────────────────────────────

def test_schema_from_signature_and_docstring():
    def chiffrer(ctx, date_livraison: datetime.date, quantite: int = 2,
                 fournisseur: Literal["a", "b"] = "a", options: list[str] | None = None,
                 note: Annotated[str, "commentaire libre"] = "",
                 remise: Optional[float] = None):
        """Chiffre.

        Args:
            date_livraison: date de livraison
                (AAAA-MM-JJ)
            quantite: nombre d'unités
        """

    assert infer_input_schema(chiffrer) == {
        "type": "object",
        "properties": {
            "date_livraison": {"type": "string", "format": "date", "description": "date de livraison (AAAA-MM-JJ)"},
            "quantite": {"type": "integer", "description": "nombre d'unités", "default": 2},
            "fournisseur": {"type": "string", "enum": ["a", "b"], "default": "a"},
            "options": {"type": "array", "items": {"type": "string"}},
            "note": {"type": "string", "description": "commentaire libre", "default": ""},
            "remise": {"type": "number"},
        },
        "required": ["date_livraison"],
    }


@pytest.mark.parametrize("bad", [
    lambda ctx, x: None,                       # annotation manquante
    lambda ctx, *x: None,                      # *args
])
def test_schema_rejects_untyped(bad):
    with pytest.raises(SchemaError):
        infer_input_schema(bad)


def test_schema_rejects_dict():
    def f(ctx, x: dict): ...
    with pytest.raises(SchemaError):
        infer_input_schema(f)


def test_docstring_parser_stops_at_next_section():
    doc = """Titre.

    Args:
        a: premier
    Returns:
        rien
    """
    assert parse_docstring_args(doc) == {"a": "premier"}


# ── Projet et manifeste ──────────────────────────────────────────────────────

def test_project_manifest():
    project = load_project(EXEMPLE)
    m = project.manifest
    assert m["format"] == "hocnota-package/1"
    assert [s["entry"] for s in m["steps"]] == ["demo.etl:importer"]
    assert [t["name"] for t in m["tools"]] == ["prix_produit", "lister_produits"]
    assert m["tools"][0]["input_schema"]["required"] == ["produit"]
    assert m["artifacts"][0]["seed"] == "seed/prix.db"


def test_missing_config(tmp_path):
    with pytest.raises(ProjectError):
        load_project(tmp_path)


@pytest.mark.skipif(not HOCNOTA_REPO, reason="HOCNOTA_REPO non défini")
def test_same_manifest_as_hocnota_conformance_fixture():
    sys.path.insert(0, HOCNOTA_REPO)
    from app.script_packages.manifest import validate_manifest
    from tests.fixtures.script_packages.conformance import MANIFEST
    assert load_project(EXEMPLE).manifest == validate_manifest(MANIFEST)


@pytest.mark.skipif(not HOCNOTA_REPO, reason="HOCNOTA_REPO non défini")
@pytest.mark.parametrize("sdk_file, hocnota_file", [
    ("schema/hocnota-package-1.json", "app/script_packages/schema/hocnota-package-1.json"),
    ("rules.py", "app/script_packages/manifest.py"),
    ("_launcher_v1.py", "app/script_packages/launcher.py"),
])
def test_copies_in_sync_with_hocnota(sdk_file, hocnota_file):
    import hocnota_scripts
    sdk = Path(hocnota_scripts.__file__).parent / sdk_file
    assert sdk.read_bytes() == (Path(HOCNOTA_REPO) / hocnota_file).read_bytes(), (
        f"{sdk_file} diverge de HocNota : recopier {hocnota_file}"
    )


# ── Exécution locale ─────────────────────────────────────────────────────────

def test_run_steps_then_call_tool(tmp_path):
    project = load_project(EXEMPLE)
    out = tmp_path / "artifacts"
    result, stderr = run_steps(project, {"grille": EXEMPLE / "grille_v2.csv"}, out)
    assert result["ok"], result
    assert result["meta"] == {"lignes": 3, "source": "grille_v2.csv"}
    assert sqlite3.connect(out / "prix.db").execute("SELECT count(*) FROM prix").fetchone() == (3,)
    assert "import de" in stderr

    r, _ = call_tool(project, "prix_produit", {"produit": "kiwi"}, {"prix": out / "prix.db"})
    assert r == {"ok": True, "result": {"trouve": True, "produit": "kiwi", "montant": 0.8}}


def test_failing_step_reports_the_script_message(tmp_path):
    """L'exception d'une étape est son canal d'erreur : HocNota arrête le job avec ce message."""
    import shutil
    project_dir = tmp_path / "p"
    shutil.copytree(EXEMPLE, project_dir)
    (project_dir / "src" / "demo" / "etl.py").write_text(
        "from hocnota_scripts import Context, step\n\n\n"
        "@step(inputs=['grille'], outputs=['prix'])\n"
        "def importer(ctx: Context, grille):\n"
        "    raise ValueError('Aucun produit dans la grille')\n"
    )
    for name in [m for m in sys.modules if m == "demo" or m.startswith("demo.")]:
        del sys.modules[name]  # le module est déjà importé depuis le projet d'origine
    result, _ = run_steps(load_project(project_dir), {"grille": EXEMPLE / "grille_v2.csv"}, tmp_path / "out")
    assert not result["ok"] and result["error"] == "ValueError: Aucun produit dans la grille"


def test_call_tool_validates_arguments_like_hocnota():
    project = load_project(EXEMPLE)
    r, _ = call_tool(project, "prix_produit", {"produit": 3})
    assert not r["ok"] and r["error"].startswith("arguments invalides")


def test_golden_on_seed():
    project = load_project(EXEMPLE)
    report = run_golden(project, EXEMPLE / "tests" / "golden.jsonl")
    assert report == [("seed-poire", []), ("seed-liste", []), ("argument-manquant", [])]


def test_matches_is_inclusive():
    assert matches({"a": 1}, {"a": 1, "b": 2}) == []
    assert matches({"a": {"b": 1.0}}, {"a": {"b": 1}}) == []
    assert matches({"a": 1}, {"a": 2}) == [".a : 1 ≠ 2"]


# ── Archive ──────────────────────────────────────────────────────────────────

def test_build_archive(tmp_path):
    project = load_project(EXEMPLE)
    out = build(project, tmp_path)
    assert out.name == "conformance-demo-1.0.0.hnpkg"
    with zipfile.ZipFile(out) as zf:
        names = set(zf.namelist())
        manifest = json.loads(zf.read("manifest.json"))
    assert {"manifest.json", "instructions.md", "pkg/demo/etl.py", "pkg/demo/outils.py",
            "seed/prix.db"} <= names
    assert not any("__pycache__" in n for n in names)
    assert manifest == project.manifest


def test_archive_without_seeds():
    data = build_archive(load_project(EXEMPLE), with_seeds=False)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        assert not any(n.startswith("seed/") for n in zf.namelist())


@pytest.mark.skipif(not HOCNOTA_REPO, reason="HOCNOTA_REPO non défini")
def test_hocnota_accepts_built_archive(tmp_path):
    pytest.importorskip("fastapi")
    sys.path.insert(0, HOCNOTA_REPO)
    from app.script_packages.archive import read_package
    pkg = read_package(build(load_project(EXEMPLE), tmp_path).read_bytes())
    assert pkg.manifest["name"] == "conformance-demo"


# ── Ligne de commande ────────────────────────────────────────────────────────

def test_init_creates_a_valid_project(tmp_path, capsys):
    target = tmp_path / "mon-paquet"
    assert cli.main(["init", str(target)]) == 0
    assert (target / ".gitignore").is_file()
    assert (target / "src" / "mon_paquet" / "etl.py").is_file()
    from hocnota_scripts import __version__
    # The project's AI instructions, pinned to this framework version.
    agents = (target / "AGENTS.md").read_text()
    assert f"blob/v{__version__}/docs/guide-projet.md" in agents and "src/mon_paquet/etl.py" in agents
    assert f"Framework-HNS@v{__version__}" in (target / "requirements-dev.txt").read_text()
    assert "{{" not in "".join(f.read_text() for f in target.rglob("*") if f.is_file())
    assert cli.main(["validate", "--project", str(target)]) == 0
    assert "mon-paquet 0.1.0" in capsys.readouterr().out


def test_generated_project_does_not_commit_its_virtualenv(tmp_path):
    """The generated README creates .venv inside the project."""
    import subprocess

    target = tmp_path / "mon-paquet"
    assert cli.main(["init", str(target)]) == 0
    venv_file = target / ".venv" / "bin" / "python"
    venv_file.parent.mkdir(parents=True)
    venv_file.write_text("")
    subprocess.run(["git", "init", "-q"], cwd=target, check=True)
    subprocess.run(["git", "add", "-A"], cwd=target, check=True)
    staged = subprocess.run(["git", "ls-files"], cwd=target, check=True,
                            capture_output=True, text=True).stdout.splitlines()
    assert "hocnota.toml" in staged
    assert not [f for f in staged if f.startswith(".venv/")]


def test_cli_reports_project_errors(tmp_path, capsys):
    assert cli.main(["validate", "--project", str(tmp_path)]) == 2
    assert "hocnota.toml introuvable" in capsys.readouterr().err


def test_version_flag(capsys):
    from hocnota_scripts import __version__
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"hocnota-scripts {__version__} (format hocnota-package/1)"
