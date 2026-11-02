# Framework HNS — instructions pour l'IA de code

Ce dépôt est le **Framework HNS** (paquet `hocnota-scripts`), qui sert à écrire des paquets HNS. Pour
**créer un paquet** (projet client), ne travaillez pas ici : suivez
[docs/guide-projet.md](docs/guide-projet.md) dans un projet créé par
`hocnota-scripts init`.

## Carte du dépôt

| Fichier | Rôle |
|---|---|
| `hocnota_scripts/api.py` | `@step`, `@tool`, `Context` (réexporté du lanceur) |
| `hocnota_scripts/schema_infer.py` | signature Python → `input_schema` JSON (sous-ensemble portable) |
| `hocnota_scripts/project.py` | lecture de `hocnota.toml`, découverte des décorateurs, manifeste |
| `hocnota_scripts/build.py` | vendorisation (wheels pures), archive `.hnpkg` |
| `hocnota_scripts/local_run.py` | exécution locale avec le lanceur HocNota (option `--sandbox` Docker) |
| `hocnota_scripts/golden.py` | jeu de référence `tests/golden.jsonl` |
| `hocnota_scripts/cli.py` | commandes `init`, `validate`, `run-step`, `call`, `test`, `build`, `inspect` |
| `hocnota_scripts/templates/projet/` | gabarit des projets (`*.tpl`, `{{name}}`, `{{module}}`, `{{sdk_version}}`) |
| `hocnota_scripts/schema/hocnota-package-1.json`, `rules.py`, `_launcher_v1.py` | **copies verbatim de HocNota — ne pas modifier ici** |
| `tests/exemple/` | paquet de conformance (même manifeste que la fixture HocNota) |
| `docs/guide-projet.md` | guide de bout en bout pour les projets clients |

## Règles

1. Les trois fichiers du contrat ne se modifient jamais ici : ils viennent de la
   plateforme HocNota, qui décide seule d'une évolution du format.
2. Le code exécuté dans le bac à sable (lanceur) est en bibliothèque standard. Le
   framework lui-même ne dépend que de `jsonschema`.
3. `__version__` (dans `hocnota_scripts/__init__.py`) est la seule source de la
   version ; chaque version publiée a sa section dans `CHANGELOG.md`.
4. Toute évolution visible des projets clients met à jour `docs/guide-projet.md` et,
   si besoin, le gabarit (dont `AGENTS.md.tpl`).
5. Messages et documentation en français.
6. **Dépôt public : aucune donnée ni aucun nom de client ou de projet client**, nulle
   part (code, exemples, tests, messages de commit). Les exemples utilisent un domaine
   fictif : le catalogue de pièces détachées `catalogue-produits`.

## Commandes

```bash
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest -q                                  # tests
```
