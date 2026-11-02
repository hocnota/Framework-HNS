# Framework HNS

**Framework HNS** (HocNota Scripts) : création de **paquets HNS** (`.hnpkg`, format
`hocnota-package/1`). Un paquet contient :

- des **étapes d'import** (`@step`) qui transforment un fichier fourni par
  l'utilisateur (ex. un classeur Excel joint à un chat) en **artefacts**
  (ex. une base SQLite) ;
- des **outils** (`@tool`) typés, offerts à un agent HocNota, qui lisent ces
  artefacts ;
- des **consignes** (`instructions.md`) ajoutées au prompt de l'agent.

Dans HocNota, le paquet importé devient un nœud **Script** de pipeline : relié au
flux des documents supports et à la patte MCP d'un agent. Tout s'exécute dans le
bac à sable de HocNota (Python 3.12, sans réseau, lecture seule).

**Documentation**

- [Guide : de l'initialisation d'un projet à la production sur HocNota](docs/guide-projet.md)
  (écrit pour être suivi par une IA de code comme par un développeur) ;
- [Journal des versions](CHANGELOG.md).

## Installation

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install "hocnota-scripts @ git+https://github.com/hocnota/Framework-HNS@v0.2.0"
hocnota-scripts init mon-paquet && cd mon-paquet
pip install -r requirements-dev.txt
```

Le projet créé contient un `AGENTS.md` qui donne à une IA de code
les règles du format et le lien vers le guide de la version utilisée.

## Cycle de travail

```bash
hocnota-scripts validate                                   # manifeste + règles du format
hocnota-scripts run-step --input classeur=fichier.xlsx     # → build/artifacts/
hocnota-scripts call lire_lignes '{"limite": 3}'           # appel d'outil
hocnota-scripts test                                       # tests/golden.jsonl
hocnota-scripts build                                      # → dist/<nom>-<version>.hnpkg
hocnota-scripts inspect dist/<nom>-<version>.hnpkg
```

`--sandbox` (run-step, call, test) rejoue dans `python:3.12-slim` sans réseau,
système de fichiers en lecture seule, 512 Mo — au plus près du bac à sable.

## Écrire un paquet

`hocnota.toml` déclare le paquet, ses entrées et ses artefacts ; les étapes et
les outils sont découverts par leurs décorateurs dans les modules listés.

```python
from datetime import date
from typing import Literal
from hocnota_scripts import Context, step, tool

@step(inputs=["catalogue"], outputs=["produits"], timeout_s=90)
def importer(ctx: Context, catalogue):
    """Catalogue Excel → produits.db."""
    ...                                   # écrire ctx.output_path("produits")
    return {"maj_stocks": "2026-10-15"}   # métadonnées montrées à l'agent

@tool(artifacts=["produits"])
def chiffrer_commande(ctx: Context, date_livraison: date, quantite: int = 1,
                      fournisseur: Literal["atlas", "boreal"] = "atlas") -> dict:
    """Prix d'une commande, remise de quantité comprise.

    Args:
        date_livraison: date de livraison souhaitée
        quantite: nombre d'unités
    """
    conn = ctx.sqlite("produits")         # lecture seule
    ...
```

Règles du format (vérifiées au build **et** à l'import dans HocNota) :

| Règle | Pourquoi |
|---|---|
| Dépendances **pur Python** uniquement (wheels `py3-none-any`), embarquées dans `vendor/` | pas de réseau ni de compilation dans le bac à sable, `/tmp` monté `noexec` |
| Types d'arguments : `str`, `int`, `float`, `bool`, `date`, `Literal`, `list[...]` de ceux-ci | sous-ensemble JSON Schema accepté par tous les fournisseurs de LLM |
| Noms réservés : `skill_*`, `list_all`, `get_columns_by_value`, `get_columns_by_search`, `check_spell` ; paramètres `args`, `config`, `ctx`… | déjà utilisés par HocNota |
| Somme des `timeout_s` des étapes ≤ 120 s ; outil ≤ 60 s ; sortie ≤ 20 000 caractères | plafonds du bac à sable |
| Archive ≤ 32 Mo | envoyée au bac à sable à chaque exécution |
| Un outil ne peut pas modifier un artefact | ouvert en lecture seule (`mode=ro&immutable=1`) |

À l'exécution, `hocnota_scripts` est fourni par le lanceur de HocNota : n'en
importez que `step`, `tool`, `Context`, `InputFile`. Une valeur `date` arrive
convertie depuis la chaîne JSON `AAAA-MM-JJ`. Un `print()` est permis (il part
dans les journaux, pas dans le résultat).

## Jeu de référence

`tests/golden.jsonl`, une ligne par cas :

```json
{"id": "q01", "tool": "chiffrer_commande", "args": {"date_livraison": "2026-12-05"}, "expect": {"total": 1234.5}}
```

`expect` est comparé par inclusion (les autres champs du résultat sont libres) ;
`"expect_error": true` attend un échec.

## Fichiers fournis par HocNota

`hocnota_scripts/rules.py`, `hocnota_scripts/_launcher_v1.py` et
`hocnota_scripts/schema/hocnota-package-1.json` sont les règles du format et le
lanceur utilisés par la plateforme. Ne les modifiez pas : un paquet construit avec
des règles différentes serait refusé à l'import ou ne s'exécuterait pas de la même
façon.
