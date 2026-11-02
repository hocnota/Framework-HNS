"""Jeu de questions de référence : ``tests/golden.jsonl``.

Une ligne = un appel d'outil et le résultat attendu :

    {"id": "q01", "tool": "chiffrer_commande", "args": {...}, "expect": {"total": 1234.5}}

ou un document à contrôler et le verdict attendu (``"document"`` : chemin relatif au
projet) :

    {"id": "d01", "document": "tests/docs/valide.xlsx", "verdict": "accepted", "expect": {"onglets": 4}}
    {"id": "d02", "document": "tests/docs/sans_onglet.xlsx", "verdict": "rejected",
     "message_contains": "onglet « Produits »"}

``verdict`` vaut ``accepted`` (défaut), ``rejected``, ``skipped`` (aucun contrôle ne
concerne ce type de fichier) ou ``failed`` (contrôle impossible : exception, délai).

``expect`` est comparé en inclusion : chaque clé attendue doit être présente
avec la même valeur (récursivement ; une liste doit être égale) — le résultat
peut contenir d'autres champs. ``"expect_error": true`` attend un échec.
"""

import json
from pathlib import Path

from hocnota_scripts.local_run import call_tool, run_check
from hocnota_scripts.project import Project


def matches(expected, actual, path="") -> list[str]:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [f"{path or '.'} : objet attendu, reçu {type(actual).__name__}"]
        diffs = []
        for key, value in expected.items():
            if key not in actual:
                diffs.append(f"{path}.{key} : absent")
            else:
                diffs.extend(matches(value, actual[key], f"{path}.{key}"))
        return diffs
    if isinstance(expected, float) or isinstance(actual, float):
        try:
            return [] if abs(float(expected) - float(actual)) < 1e-6 else [f"{path} : {expected!r} ≠ {actual!r}"]
        except (TypeError, ValueError):
            pass
    return [] if expected == actual else [f"{path or '.'} : {expected!r} ≠ {actual!r}"]


def _verdict(result: dict) -> str:
    if not result.get("ok"):
        return "failed"
    if result.get("skipped"):
        return "skipped"
    return "rejected" if result.get("rejected") else "accepted"


def _check_case(project: Project, case: dict, sandbox: bool) -> list[str]:
    document = project.root / case["document"]
    if not document.is_file():
        return [f"document introuvable : {case['document']}"]
    result, stderr = run_check(project, document, sandbox=sandbox)
    expected = case.get("verdict", "accepted")
    got = _verdict(result)
    if got != expected:
        detail = result.get("message") or result.get("error") or ""
        diffs = [f"verdict {got!r} au lieu de {expected!r}" + (f" : {detail}" if detail else "")]
        if stderr.strip():
            diffs.append(stderr.strip()[-500:])
        return diffs
    diffs = []
    needle = case.get("message_contains")
    if needle and needle not in (result.get("message") or result.get("error") or ""):
        diffs.append(f"message sans « {needle} » : {result.get('message') or result.get('error')!r}")
    if "expect" in case:
        diffs.extend(matches(case["expect"], result.get("meta", {})))
    return diffs


def run_golden(project: Project, path: Path, *, sandbox: bool = False) -> list[tuple[str, list[str]]]:
    """Renvoie [(id, différences)] — liste vide de différences = succès."""
    report = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        case = json.loads(line)
        case_id = case.get("id", f"ligne {n}")
        if "document" in case:
            report.append((case_id, _check_case(project, case, sandbox)))
            continue
        result, stderr = call_tool(project, case["tool"], case.get("args", {}), sandbox=sandbox)
        if case.get("expect_error"):
            report.append((case_id, [] if not result.get("ok") else ["succès inattendu"]))
        elif not result.get("ok"):
            report.append((case_id, [f"échec : {result.get('error')}"] + ([stderr.strip()[-500:]] if stderr.strip() else [])))
        else:
            report.append((case_id, matches(case.get("expect", {}), result["result"])))
    return report
