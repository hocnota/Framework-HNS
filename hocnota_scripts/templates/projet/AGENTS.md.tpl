# {{name}} — instructions pour l'IA de code

Ce dépôt est un **paquet HNS** (format `hocnota-package/1`), construit
avec le Framework HNS (`hocnota-scripts` v{{sdk_version}}).

Guide complet, à suivre pour toute tâche (conception, import, outils, tests,
livraison, mise en production) :
https://github.com/hocnota/Framework-HNS/blob/v{{sdk_version}}/docs/guide-projet.md

## Ce que fait ce dépôt

- `src/{{module}}/etl.py` : étape(s) d'import `@step` — fichier source → artefacts
  (`ctx.output_path(nom)`), renvoie un dict de métadonnées montrées à l'agent.
- `src/{{module}}/outils.py` : outils `@tool` offerts à l'agent HocNota, en lecture
  seule sur les artefacts (`ctx.sqlite(nom)`).
- (facultatif) un module de contrôles `@check` : lit le document d'un job, le laisse
  passer (renvoie des constats) ou le refuse (`raise Reject("message pour l'utilisateur")`).
  Voir §7.1 du guide.
- `hocnota.toml` : nom, version, entrées, artefacts, dépendances.
- `instructions.md` : consignes ajoutées au prompt de l'agent.
- `tests/golden.jsonl` : jeu de référence (appel d'outil → résultat attendu).

## Règles impératives

1. Aucun montant ni calcul métier laissé au modèle : tout sort d'un outil.
2. Python 3.12 ; bibliothèque standard + dépendances **pur Python** déclarées dans
   `hocnota.toml` (aussi dans `requirements-dev.txt` pour le local). Pas de réseau.
3. Les outils ne modifient jamais les données.
4. Paramètres d'outil : `str`, `int`, `float`, `bool`, `date`, `Literal[...]`,
   `list[...]` de ceux-ci, `Optional[...]`. Docstring : première phrase = description,
   section `Args:` = description de chaque paramètre, écrites pour le modèle.
5. Noms réservés : outils `skill_*`, `list_all`, `get_columns_by_value`,
   `get_columns_by_search`, `check_spell` ; paramètres `args`, `callbacks`,
   `run_manager`, `config`, `ctx`.
6. N'importer de `hocnota_scripts` que `step`, `tool`, `check`, `Reject`, `Context`,
   `InputFile`.
7. Erreur métier d'un outil ou d'une étape → `raise ValueError("message clair")`.
   `Reject` est réservé aux contrôles de document et à un verdict métier ; un défaut
   du contrôle lui-même doit planter, pas refuser. Contrôles de cohérence
   obligatoires dans l'import : un fichier mal formé doit échouer.
8. Sorties d'outil compactes (< 4 000 caractères visés, 20 000 max).
9. Avant toute livraison : incrémenter `version` dans `hocnota.toml` ; incrémenter
   `schema_version` de l'artefact si la structure des données change.
10. Les valeurs attendues du jeu de référence viennent de la source de vérité
    (le fichier source), jamais du code testé.

## Commandes

```bash
pip install -r requirements-dev.txt
hocnota-scripts validate                               # manifeste + règles du format
hocnota-scripts run-step --input <entrée>=<fichier>    # import → build/artifacts/
hocnota-scripts call <outil> '<json>'                  # appel d'outil
hocnota-scripts check <fichier>                        # contrôle d'un document (@check)
hocnota-scripts test                                   # tests/golden.jsonl (après run-step)
hocnota-scripts test --sandbox                         # idem, sans réseau, Python 3.12 (Docker)
hocnota-scripts build                                  # → dist/{{name}}-<version>.hnpkg
hocnota-scripts inspect dist/<archive>.hnpkg
```

## Définition de « terminé »

- `validate` OK, `run-step` OK sur le fichier source réel, `test` 100 % vert ;
- `version` incrémentée (et `schema_version` si besoin), `build` sans erreur ;
- fiche de livraison remise : archive, changements, résultat des tests, étapes
  HocNota restantes (import, approbation à la première livraison, câblage du nœud HNS, droits d'écriture,
  chargement des données, recette), questions de recette avec réponses attendues.

L'import dans HocNota et la première approbation du paquet sont faits par des
humains : ne pas chercher à les automatiser. Une mise à jour d'un paquet approuvé est
en service dès son import : ne jamais la livrer sans jeu de référence vert.
