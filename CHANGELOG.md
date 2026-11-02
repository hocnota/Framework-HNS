# Journal des versions

Format : une section `## X.Y.Z — AAAA-MM-JJ` par version publiée (tag `vX.Y.Z`).

Politique de version :

- **MAJEURE** : nouveau format d'archive (`hocnota-package/2`) ou rupture de l'API
  `step`/`tool`/`Context` — les projets doivent être adaptés.
- **MINEURE** : fonctionnalité compatible (commande, option, type d'argument accepté).
- **CORRECTIVE** : correctif sans changement de comportement attendu.

Compatibilité : toutes les versions 0.x produisent le format `hocnota-package/1`
(lanceur protocole 1), accepté par HocNota depuis l'introduction des paquets HNS.

## 0.2.0 — 2026-11-02

Première version publiée.

- Décorateurs `@step` / `@tool`, contexte `Context` identique à celui du lanceur HocNota.
- Schéma des outils déduit des signatures (`str`, `int`, `float`, `bool`, `date`,
  `Literal`, `list`, `Optional`) et des docstrings (`Args:`).
- **Contrôles de document** : `@check(accept=…, artifacts=…)` et `Reject("message")`. Un nœud
  Script placé sur le flux du document laisse passer le fichier d'un job ou le refuse par sa
  sortie « erreur ». Nécessite une plateforme HocNota qui connaît la section `checks` du
  manifeste ; les paquets sans contrôle restent importables partout.
- Commandes `init`, `validate`, `run-step`, `call`, `check`, `test` (jeu de référence),
  `build` (dépendances pur Python embarquées), `inspect` ; option `--sandbox`.
- Gabarit de projet avec `AGENTS.md` pour les IA de code.
- Guide de bout en bout : `docs/guide-projet.md`.
