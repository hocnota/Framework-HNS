# Journal des versions

Format : une section `## X.Y.Z — AAAA-MM-JJ` par version publiée (tag `vX.Y.Z`).

Politique de version :

- **MAJEURE** : nouveau format d'archive (`hocnota-package/2`) ou rupture de l'API
  `step`/`tool`/`Context` — les projets doivent être adaptés.
- **MINEURE** : fonctionnalité compatible (commande, option, type d'argument accepté).
- **CORRECTIVE** : correctif sans changement de comportement attendu.

Compatibilité : toutes les versions 0.x produisent le format `hocnota-package/1`
(lanceur protocole 1), accepté par HocNota depuis l'introduction des paquets HNS.

## 0.3.1 — 2026-11-03

Documentation et gabarit de projet seulement : aucun changement de code ni de format.

- **Fichier d'un dossier externe** : un nœud HNS peut prendre son fichier source dans
  un dossier SharePoint ou S3 connecté à HocNota. Le fichier est relu à chaque
  lancement du pipeline (chat, analyse de document, extraction) et réimporté quand son
  empreinte SHA-256 change, ou quand une nouvelle version du paquet est importée. Le
  guide décrit ce que cela implique pour un paquet : un seul fichier reçu
  (`filename_pattern` ignoré), import qui ne dépend que du fichier, message d'erreur
  répété à chaque lancement tant que le fichier n'est pas corrigé.
- Guide : corrections — une étape en échec arrête le job (§6, §13) ; le nœud s'appelle
  « HNS » dans l'éditeur (§12.3).

## 0.3.0 — 2026-11-02

- **Retiré** : `@check`, `Reject`, la commande `check`, les cas `document` / `verdict` du
  jeu de référence et la section `checks` du manifeste (ajoutés en 0.2.0). Le contrôle du
  document d'un job n'a pas d'intérêt : un paquet n'a rien à faire sur le flux du document.
  Un paquet construit avec 0.2.0 contient `"checks": []` et doit être reconstruit.
- Une exception levée par une étape arrête le job de l'utilisateur avec son message.
  Le nœud HNS a une sortie « erreur » pour la remplacer par un message du pipeline.

## 0.2.0 — 2026-11-02

Première version publiée.

- Décorateurs `@step` / `@tool`, contexte `Context` identique à celui du lanceur HocNota.
- Schéma des outils déduit des signatures (`str`, `int`, `float`, `bool`, `date`,
  `Literal`, `list`, `Optional`) et des docstrings (`Args:`).
- **Contrôles de document** : `@check` et `Reject` (retirés en 0.3.0).
- Commandes `init`, `validate`, `run-step`, `call`, `check`, `test` (jeu de référence),
  `build` (dépendances pur Python embarquées), `inspect` ; option `--sandbox`.
- Gabarit de projet avec `AGENTS.md` pour les IA de code.
- Guide de bout en bout : `docs/guide-projet.md`.
