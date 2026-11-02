# {{name}}

Paquet HNS (format `hocnota-package/1`), créé avec
le Framework HNS (`hocnota-scripts` v{{sdk_version}}). Guide : https://github.com/hocnota/Framework-HNS/blob/v{{sdk_version}}/docs/guide-projet.md

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
hocnota-scripts validate
hocnota-scripts run-step --input classeur=mon-fichier.xlsx   # → build/artifacts/base.db
hocnota-scripts call lire_lignes '{"limite": 3}'
hocnota-scripts test                                         # tests/golden.jsonl
hocnota-scripts build                                        # → dist/{{name}}-0.1.0.hnpkg
```

Mise en production (étapes humaines, détaillées au §12 du guide) : importer l'archive
(Manager → Outils → Paquets HNS), la faire approuver à la première livraison (Admin → Compétences),
ajouter un nœud « HNS » au pipeline de chat, choisir les rédacteurs, charger les
données, tester puis activer.

## Conception

<!-- À compléter avant de coder (§4 du guide) : fichier source, schéma des données,
règles de calcul, questions des utilisateurs, outils, métadonnées. -->
