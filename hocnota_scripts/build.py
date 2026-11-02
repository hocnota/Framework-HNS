"""Vendorisation des dépendances et construction de l'archive ``.hnpkg``."""

import hashlib
import io
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from hocnota_scripts.project import Project, ProjectError

# Mêmes plafonds que l'import côté HocNota (app/script_packages/archive.py).
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
_NATIVE_SUFFIXES = (".so", ".pyd", ".dll", ".dylib", ".exe")
_SKIP_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache"}
CACHE_DIR = ".hocnota"


def _pure_wheel(name: str) -> bool:
    # Tag de plateforme « any » + ABI « none » : rien de compilé.
    return name.endswith("-none-any.whl")


def vendor_dependencies(project: Project, *, refresh: bool = False) -> Path | None:
    """Télécharge les dépendances (wheels pures) et renvoie le dossier à embarquer.

    Mis en cache dans ``.hocnota/vendor-<empreinte>/`` : un build sans changement
    de dépendances ne retouche pas au réseau.
    """
    deps = sorted(project.dependencies)
    if not deps:
        return None
    digest = hashlib.sha256("\n".join(deps).encode()).hexdigest()[:16]
    target = project.root / CACHE_DIR / f"vendor-{digest}"
    if target.is_dir() and not refresh:
        return target
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [
            sys.executable, "-m", "pip", "download", "--quiet",
            "--only-binary=:all:", "--python-version", "3.12",
            "--implementation", "py", "--abi", "none", "--platform", "any",
            "--dest", tmp, *deps,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise ProjectError(
                "téléchargement des dépendances impossible — seules les wheels pur Python "
                f"(py3-none-any) sont acceptées :\n{proc.stderr.strip()}"
            )
        wheels = sorted(Path(tmp).glob("*.whl"))
        native = [w.name for w in wheels if not _pure_wheel(w.name)]
        if native:
            raise ProjectError(f"dépendances natives refusées par le bac à sable : {native}")
        staging = Path(tmp) / "vendor"
        for wheel in wheels:
            with zipfile.ZipFile(wheel) as zf:
                zf.extractall(staging)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            import shutil
            shutil.rmtree(target)
        staging.rename(target)
    return target


def _walk(base: Path):
    for path in sorted(base.rglob("*")):
        if path.is_file() and not (set(path.relative_to(base).parts) & _SKIP_DIRS) and path.suffix != ".pyc":
            yield path


def build_archive(project: Project, *, with_seeds: bool = True, vendor_dir: Path | None = None) -> bytes:
    """Assemble l'archive en mémoire. ``with_seeds=False`` = ce que reçoit le bac à sable."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(project.manifest, ensure_ascii=False, indent=2))
        if project.instructions_path:
            zf.write(project.instructions_path, project.instructions_path.name)
        for path in _walk(project.source_dir):
            rel = path.relative_to(project.source_dir).as_posix()
            if rel.endswith(_NATIVE_SUFFIXES):
                raise ProjectError(f"binaire natif interdit dans les sources : {rel}")
            zf.write(path, f"pkg/{rel}")
        if vendor_dir:
            for path in _walk(vendor_dir):
                rel = path.relative_to(vendor_dir).as_posix()
                if rel.endswith(_NATIVE_SUFFIXES):
                    raise ProjectError(f"binaire natif dans une dépendance : {rel}")
                zf.write(path, f"vendor/{rel}")
        if with_seeds:
            for arcname, local in project.seeds.items():
                zf.write(local, arcname)
    data = buf.getvalue()
    if len(data) > MAX_ARCHIVE_BYTES:
        raise ProjectError(
            f"archive de {len(data) / 1e6:.1f} Mo : au-delà de {MAX_ARCHIVE_BYTES // (1024 * 1024)} Mo, "
            "HocNota la refusera"
        )
    return data


def build(project: Project, out_dir: Path | None = None, *, refresh: bool = False) -> Path:
    vendor_dir = vendor_dependencies(project, refresh=refresh)
    data = build_archive(project, vendor_dir=vendor_dir)
    out_dir = out_dir or project.root / "dist"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / project.archive_name
    out.write_bytes(data)
    return out
