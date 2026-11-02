# Guide : un paquet HNS, de l'initialisation à la production

Ce guide est la référence pour créer, tester, livrer et maintenir un **paquet de
scripts** HocNota avec le **Framework HNS** (paquet `hocnota-scripts`). Il est écrit pour être suivi
**à la lettre par une IA de code** (et par un développeur) : chaque étape donne les
commandes, les règles à respecter et le critère de réussite.

Version du format couverte : **`hocnota-package/1`** (lanceur protocole 1).

---

## 0. Règles impératives (à relire avant chaque modification)

1. **Aucune valeur métier n'est calculée par le modèle.** Tout montant, toute date,
   toute disponibilité sort d'un outil. Le prompt (`instructions.md`) le rappelle à
   l'agent.
2. **Python 3.12, bibliothèque standard + dépendances PUR Python** (wheels
   `py3-none-any`) déclarées dans `hocnota.toml`. Aucune extension compilée
   (pandas, numpy, lxml… sont exclus). Aucun accès réseau à l'exécution.
3. **Les outils sont en lecture seule.** Seule une étape d'import produit des
   données. Un outil ne doit jamais écrire dans un artefact.
4. **Types d'arguments autorisés** : `str`, `int`, `float`, `bool`,
   `datetime.date`, `Literal[...]`, `list[...]` de ces types, `Optional[...]`.
   Rien d'autre (pas de `dict`, pas de classe, pas de `*args`/`**kwargs`).
5. **Noms réservés** : outils `skill_*`, `list_all`, `get_columns_by_value`,
   `get_columns_by_search`, `check_spell` ; paramètres `args`, `callbacks`,
   `run_manager`, `config`, `ctx`.
6. **Du module `hocnota_scripts`, n'importer que** `step`, `tool`, `Context`,
   `InputFile`. Dans HocNota, ce module est remplacé par celui du lanceur.
7. **Ne jamais réutiliser un numéro de version** déjà importé dans HocNota :
   incrémenter `version` dans `hocnota.toml` avant chaque `build` livré.
8. **Changer la structure d'un artefact = incrémenter son `schema_version`.**
9. **Rien n'est livré sans** `hocnota-scripts validate`, `hocnota-scripts test`
   (jeu de référence vert) et `hocnota-scripts build` sans erreur.
10. **L'import dans HocNota et l'approbation sont faits par des humains** (voir §11).
    L'IA prépare l'archive et la fiche de livraison ; elle ne contourne jamais
    l'approbation.

---

## 1. Vue d'ensemble

```
 fichier source (ex. Excel)          joint au chat par un rédacteur, ou importé
          │                          depuis le panneau du nœud HNS
          ▼
 ┌──────────────────┐   @step   ┌─────────────────┐
 │ étape(s) d'import│ ────────► │ artefact(s)     │  ex. produits.db (SQLite),
 └──────────────────┘           │ version N       │  partagé par tous les
                                └────────┬────────┘  utilisateurs du pipeline
                                         │ lecture seule
                                ┌────────▼────────┐
     agent IA du chat ─────────►│ outils (@tool)  │──► résultat JSON → réponse
                                └─────────────────┘
```

| Terme | Sens |
|---|---|
| **Paquet** | Archive `.hnpkg` produite par `hocnota-scripts build`. |
| **Entrée** (`[[inputs]]`) | Type de fichier que le paquet sait importer (extension, motif de nom). |
| **Étape** (`@step`) | Fonction qui lit les entrées et écrit des artefacts. Les étapes s'enchaînent dans un seul run. |
| **Artefact** (`[[artifacts]]`) | Données produites : une base SQLite (`kind = "sqlite"`) ou un fichier. |
| **Seed** | Artefact initial livré dans l'archive, utilisé tant qu'aucun import n'a eu lieu. |
| **Outil** (`@tool`) | Fonction offerte à l'agent ; schéma JSON déduit de la signature. |
| **Version de paquet** | Une archive importée. Un administrateur **approuve le paquet une fois** ; ses versions suivantes sont en service dès l'import. |
| **Version de données** | Résultat d'un import pour un nœud HNS donné. Une seule est « en vigueur ». |
| **Nœud HNS** | Le paquet placé dans un pipeline HocNota. |
| **Rédacteur** | Utilisateur ou équipe autorisé à remplacer les données en joignant un fichier au chat. |

Comment HocNota exécute un paquet :

- à chaque message du chat, **si et seulement si** un rédacteur a joint un **nouveau**
  fichier correspondant à une entrée, les étapes s'exécutent ; sinon rien ne tourne ;
- les étapes tournent dans un bac à sable dédié (1,5 Gio, 120 s au total) ;
- chaque **appel d'outil** est un **nouveau processus** Python dans le bac à sable
  (≈ 0,1 à 0,5 s de surcoût), qui reçoit l'archive et les artefacts à lire ;
- l'agent reçoit en plus les **consignes** (`instructions.md`) et une ligne
  **« État des données »** : version, date d'import, fichier source et les
  métadonnées renvoyées par l'étape.

---

## 2. Prérequis

| Besoin | Détail |
|---|---|
| Python ≥ 3.11 en local | Le bac à sable exécute **Python 3.12** : visez 3.12. |
| Docker (facultatif) | Pour `--sandbox`, qui rejoue dans `python:3.12-slim` sans réseau. |
| Accès Internet au build | Pour télécharger les dépendances (`pip download`). |
| Le fichier source réel | Au moins un exemplaire, pour écrire et tester l'import. |
| Comptes HocNota (humains) | Un **gestionnaire des compétences** (importe), un **administrateur** (approuve), un **gestionnaire de pipelines** (câble le nœud). |

---

## 3. Initialiser le projet

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install "hocnota-scripts @ git+https://github.com/hocnota/Framework-HNS@v0.3.0"
hocnota-scripts --version
hocnota-scripts init catalogue-produits     # nom : minuscules, chiffres, tirets
cd catalogue-produits
pip install -r requirements-dev.txt         # SDK épinglé + dépendances du paquet
git init && git add -A && git commit -m "Squelette du paquet"
hocnota-scripts validate                    # doit afficher « valide »
```

Arborescence produite :

```
catalogue-produits/
├── hocnota.toml            # déclaration du paquet (§5)
├── src/catalogue_produits/
│   ├── etl.py              # étapes d'import (@step)
│   └── outils.py           # outils (@tool)
├── instructions.md         # consignes pour l'agent (§8)
├── seed/                   # artefact initial éventuel (§9)
├── tests/golden.jsonl      # jeu de référence (§10)
├── requirements-dev.txt
├── AGENTS.md              # règles pour l'IA de code de ce projet
└── README.md
```

Le dossier `src/<module>/` peut contenir plusieurs fichiers et sous-packages :
tout `src/` est embarqué. Déclarez dans `modules` ceux qui contiennent des
`@step`/`@tool`.

---

## 4. Concevoir avant de coder

Répondre par écrit (dans le README du projet) à ces questions avant d'écrire du code :

1. **Source** : quel fichier, quelle forme (feuilles, plages, formules), quel nom
   (→ `filename_pattern`), quelle fréquence de mise à jour, qui le fournit (→ rédacteurs) ?
2. **Données** : quel schéma SQLite minimal permet de répondre à toutes les questions ?
   Tables normalisées, clés, **index** sur les colonnes de recherche. Ne recopiez
   pas le tableur : modélisez ce qu'il calcule.
3. **Calcul** : quelles règles le fichier applique-t-il (formules, arrondis, remises,
   barèmes) ? Elles seront réimplémentées en Python dans les outils, puis
   **vérifiées contre le fichier** (jeu de référence).
4. **Questions des utilisateurs** : listez 15 à 30 questions réelles. Chaque question
   doit être couverte par **un** appel d'outil, au plus deux.
5. **Outils** : peu nombreux (3 à 10), **à grain large** (un outil qui renvoie un devis
   complet plutôt que cinq outils élémentaires), paramètres en énumérations dès que
   possible.
6. **Métadonnées** : quelles informations l'agent doit-il connaître sur les données
   (date de mise à jour, version du catalogue, période couverte) ? Elles sont
   renvoyées par l'étape (`return {...}`) et affichées à l'agent.

---

## 5. `hocnota.toml` (référence)

```toml
[package]
name = "catalogue-produits"       # identifiant du paquet dans HocNota, ne change jamais
version = "1.0.0"                 # X.Y.Z ; incrémenter à CHAQUE livraison
description = "Catalogue de pièces détachées : recherche de références, comparaison de fournisseurs et chiffrage de commandes."
source = "src"
modules = ["catalogue_produits.etl", "catalogue_produits.outils"]
instructions = "instructions.md"
dependencies = ["openpyxl>=3.1"]  # PUR Python uniquement

[[inputs]]
name = "catalogue"                # identifiant (a-z, 0-9, _)
accept = [".xlsx"]                # extensions acceptées, en minuscules
filename_pattern = "catalogue"    # regex, insensible à la casse ; facultatif
description = "Catalogue Excel « catalogue_pieces_XX.xlsx »"
required = false

[[artifacts]]
name = "produits"
kind = "sqlite"                   # "sqlite" ou "file"
filename = "produits.db"
schema_version = 1                # +1 à chaque changement de structure
seed = "seed/produits.db"         # facultatif
```

Règles vérifiées par `validate` (et à nouveau par HocNota à l'import) :

| Règle | Limite |
|---|---|
| Entrées / artefacts / étapes | 10 max chacun |
| Outils | 32 max |
| Somme des `timeout_s` des étapes | ≤ 120 s (défaut 60 s par étape) |
| `timeout_s` d'un outil | ≤ 60 s (défaut 15 s) |
| `max_output_chars` d'un outil | 100 à 20 000 (défaut 20 000) |
| Description du paquet | ≤ 1 000 caractères ; d'un outil ≤ 2 000 |
| `instructions.md` | ≤ 8 000 caractères |
| Chaque artefact | produit par une étape **ou** fourni en seed |

`filename_pattern` est appliqué aux fichiers **joints au chat** (pour ne pas importer
un fichier sans rapport). Il ne l'est pas aux imports explicites depuis le panneau du
nœud, où seule l'extension compte.

---

## 6. Écrire l'étape d'import

```python
import sqlite3
from hocnota_scripts import Context, step


@step(inputs=["catalogue"], outputs=["produits"], timeout_s=90)
def importer(ctx: Context, catalogue):
    """Catalogue Excel → produits.db."""
    from openpyxl import load_workbook        # dépendance embarquée (vendor/)

    wb = load_workbook(catalogue, read_only=True, data_only=True)
    out = ctx.output_path("produits")         # chemin où ÉCRIRE l'artefact
    conn = sqlite3.connect(out)
    ...                                       # créer tables + index, insérer
    _controles_de_coherence(conn)             # lever ValueError si incohérent
    conn.commit()
    conn.execute("VACUUM")
    conn.close()
    return {                                  # métadonnées montrées à l'agent
        "version_catalogue": "2026-T4",
        "maj_stocks": "2026-10-15",
        "periode": "2026-11-01 → 2027-10-31",
    }
```

Contrat :

| Élément | Règle |
|---|---|
| Signature | `fonction(ctx, **entrées)` : un paramètre par entrée listée dans `inputs`, valant un `pathlib.Path` ou `None` si le fichier n'a pas été fourni. |
| Sorties | Écrire chaque artefact listé dans `outputs` à `ctx.output_path(nom)`. Une sortie manquante fait échouer l'import. |
| Retour | `dict` JSON (≤ 64 Kio, valeurs simples de préférence) ou `None`. |
| Enchaînement | Les étapes s'exécutent dans l'ordre des modules puis du fichier ; une étape lit la sortie d'une précédente avec `ctx.artifact_path(nom)` ou `ctx.sqlite(nom)`. |
| Erreurs | Lever `ValueError("message clair pour un humain")` : l'import échoue, **les données précédentes restent en vigueur**, le message est montré à l'agent et dans l'historique du nœud. |
| Journal | `print()` ou `ctx.log()` : visible dans la trace (« Journal du script »), jamais dans le résultat. |
| Ressources | 1,5 Gio de mémoire, 120 s, fichiers écrits ≤ 128 Mio, artefacts ≤ 64 Mio au total. |

Bonnes pratiques :

- **Contrôles de cohérence obligatoires** : nombre de lignes attendu, valeurs non
  nulles, plages de dates, absence de doublons. Un fichier mal formé doit **échouer**,
  pas produire une base fausse.
- openpyxl : `read_only=True, data_only=True` (valeurs calculées, pas les formules).
  Les cellules fusionnées et les formules non recalculées sont les pièges usuels.
- SQLite : index sur les colonnes filtrées, `VACUUM` à la fin, types explicites,
  montants en `REAL` arrondis comme le fichier source (ou en centimes `INTEGER`).
  **Gardez la base petite** (élaguez le passé si inutile) : elle est envoyée au bac à
  sable à **chaque** appel d'outil.
- Déterminisme : aucune dépendance à l'heure courante sauf pour une métadonnée.

---

## 7. Écrire les outils

```python
from datetime import date
from typing import Literal, Optional
from hocnota_scripts import Context, tool

Fournisseur = Literal["atlas", "boreal", "cobalt", "delta"]


@tool(artifacts=["produits"])
def chiffrer_commande(ctx: Context, date_livraison: date, reference: str, fournisseur: Fournisseur,
                      quantite: int = 1, transporteur: Optional[str] = None) -> dict:
    """Prix d'une commande pour UNE référence, remise de quantité comprise.

    Args:
        date_livraison: date de livraison souhaitée (AAAA-MM-JJ)
        reference: référence du produit (ex. « BLN-M8 »)
        fournisseur: fournisseur de la commande
        quantite: nombre d'unités (1 à 500)
        transporteur: transporteur ; par défaut celui du fournisseur
    """
    if not 1 <= quantite <= 500:
        raise ValueError("quantite doit être comprise entre 1 et 500")
    conn = ctx.sqlite("produits")             # lecture seule
    ...
    return {"reference": reference, "date_livraison": date_livraison.isoformat(), "quantite": quantite,
            "prix_unitaire": 0.42, "total": 84.0, "devise": "EUR",
            "palier_remise": 3, "en_stock": True}
```

Contrat :

| Élément | Règle |
|---|---|
| Premier paramètre | `ctx` (le contexte), toujours. |
| Paramètres | Types du §0, règle 4. Sans valeur par défaut = obligatoire. `Literal` → énumération proposée au modèle. `date` → reçu en `datetime.date` (le modèle envoie `AAAA-MM-JJ`). |
| Description | Première phrase de la docstring = description de l'outil ; section `Args:` = description de chaque paramètre. **Écrivez-les pour le modèle** : quand utiliser l'outil, unités, bornes. |
| Retour | Valeur JSON (dict de préférence). Les `date`/`Decimal` sont convertis en chaîne. |
| Taille | ≤ `max_output_chars` (20 000 par défaut) une fois sérialisé ; au-delà HocNota tronque. Visez **< 4 000 caractères** : la sortie entre dans le contexte du modèle. |
| Erreur métier | `raise ValueError("…")` : l'agent reçoit `Erreur : ValueError: …` et peut corriger ses arguments. |
| Données | `ctx.sqlite("nom")` (connexion en lecture seule ; `row_factory=sqlite3.Row` possible) ou `ctx.artifact_path("nom")`. |
| Arguments invalides | Rejetés par HocNota **avant** l'exécution, contre le schéma JSON. |

Conception :

- **Un appel = une réponse complète.** Un processus par appel : préférez
  `comparer_fournisseurs(reference, quantite, fournisseurs: list[Fournisseur])` à quatre
  appels `chiffrer_commande`.
- **Renvoyer les éléments de justification** (palier de remise, période, règle appliquée)
  pour que l'agent puisse expliquer le résultat sans l'inventer.
- **Nommer les unités** dans les clés (`prix_unitaire`, `devise`).
- **Pas d'état** entre deux appels ; pas d'écriture de fichier hors `/tmp`.
- Prévoir un outil de **référentiel** (`lister_referentiels` : fournisseurs, catégories,
  périodes couvertes) : l'agent l'appelle quand une question est ambiguë.

### 7.1 Faire échouer une étape avec un message clair

Une étape qui lève une exception **arrête le job** de l'utilisateur (le tour de chat,
dont l'import est la première étape) : l'exception est le canal d'erreur du paquet, et
son message est ce que l'utilisateur lira.

```python
@step(inputs=["catalogue"], outputs=["produits"])
def importer(ctx: Context, catalogue):
    wb = load_workbook(catalogue, read_only=True, data_only=True)
    if "Produits" not in wb.sheetnames:
        raise ValueError("Ce classeur n'est pas un catalogue : l'onglet « Produits » est absent.")
    ...
```

- Écrivez le message **pour l'utilisateur** : une phrase claire, sans jargon ni trace,
  qui dit **ce qui ne va pas et comment corriger**. HocNota y ajoute le type de
  l'exception (« ValueError: … ») ; la trace complète reste dans le journal du script.
- Les données précédentes restent en vigueur : un import raté ne casse rien.
- Dans le pipeline, la sortie **« erreur »** du nœud HNS permet de remplacer ce message
  par celui d'un nœud « Message d'erreur », puis d'aboutir à la « Sortie erreur ».
  Sans liaison, le job échoue avec le message du script.
- Un **outil** qui lève une exception ne fait pas échouer le job : l'erreur revient
  à l'agent, qui l'explique à l'utilisateur.

---

## 8. `instructions.md`

Ajouté tel quel au prompt système de l'agent, à côté des descriptions d'outils.
≤ 8 000 caractères. Contenu attendu :

- le **périmètre** (« tu réponds aux questions sur le catalogue de pièces détachées ») ;
- **« Ne donne jamais un montant de mémoire : appelle toujours un outil »** ;
- comment présenter les résultats (prix unitaire selon la quantité, devise,
  fourchette quand le prix dépend du fournisseur) ;
- **mentionner la date des données** (fournie dans « État des données ») quand elle
  conditionne la réponse (stocks, prix) ;
- quand **poser une question** plutôt que supposer (dates, quantités) ;
- les **mentions obligatoires** (ex. prix indicatifs, hors frais de port).

Ne pas y décrire les outils un par un : leurs descriptions sont déjà envoyées.

---

## 9. Seed (données initiales)

Facultatif mais recommandé : sans seed, les outils échouent tant qu'aucun fichier n'a
été importé dans le nœud. Pour en produire un :

```bash
hocnota-scripts run-step --input catalogue=chemin/vers/fichier.xlsx   # → build/artifacts/produits.db
cp build/artifacts/produits.db seed/produits.db
```

puis déclarer `seed = "seed/produits.db"` dans `hocnota.toml`. Le seed est dans
l'archive (≤ 32 Mo au total) ; il n'est jamais envoyé au bac à sable avec le code.

---

## 10. Tester en local

```bash
hocnota-scripts validate                                      # manifeste + règles
hocnota-scripts run-step --input catalogue=fichier.xlsx       # import → build/artifacts/ + meta.json
hocnota-scripts call lister_referentiels                      # outil sur build/artifacts/ (sinon seed)
hocnota-scripts call chiffrer_commande '{"date_livraison": "2026-12-05", "reference": "BLN-M8", "fournisseur": "atlas"}'
hocnota-scripts test                                          # jeu de référence
hocnota-scripts test --sandbox                                # idem dans python:3.12-slim, sans réseau
```

`run-step` et `call` utilisent **le même lanceur** que HocNota et valident les
arguments **comme HocNota**. `call` signale une sortie qui serait tronquée.

### Jeu de référence `tests/golden.jsonl`

Une ligne par cas ; les lignes vides et celles qui commencent par `#` sont ignorées :

```json
{"id": "q01-boulon-atlas", "tool": "chiffrer_commande", "args": {"date_livraison": "2026-12-05", "reference": "BLN-M8", "fournisseur": "atlas", "quantite": 200}, "expect": {"prix_unitaire": 0.42, "devise": "EUR"}}
{"id": "q02-hors-periode", "tool": "chiffrer_commande", "args": {"date_livraison": "2030-01-01", "reference": "BLN-M8", "fournisseur": "atlas"}, "expect_error": true}
```

- `expect` est comparé **par inclusion**, récursivement : les clés attendues doivent
  être égales (les nombres à 10⁻⁶ près), les autres clés sont libres.
- Les valeurs attendues viennent de la **source de vérité** (le fichier Excel lui-même,
  ou un calcul de référence validé contre lui) — **jamais** du code testé.
- Couvrir : chaque outil, chaque fournisseur/catégorie, les bornes (première et dernière
  date, quantité min/max), les cas d'erreur, les cas réels du §4.
- Le jeu de référence tourne sur `build/artifacts/` s'il existe, sinon sur le seed :
  lancez `run-step` sur le fichier de référence avant `test`.

Des tests `pytest` classiques peuvent compléter (fonctions de calcul pures).

---

## 11. Construire et livrer l'archive

```bash
# 1. incrémenter `version` dans hocnota.toml (règle 7), et `schema_version` si la base change
hocnota-scripts validate && hocnota-scripts test
hocnota-scripts build                       # → dist/catalogue-produits-1.0.0.hnpkg
hocnota-scripts inspect dist/catalogue-produits-1.0.0.hnpkg
git commit -am "Version 1.0.0" && git tag v1.0.0
```

`build` télécharge les dépendances en wheels pures (refuse toute dépendance native),
les embarque dans `vendor/` et refuse une archive > 32 Mo. Le cache
`.hocnota/vendor-*` évite de retélécharger ; `--refresh` le reconstruit.

**L'IA s'arrête ici** et remet une **fiche de livraison** (dans la réponse ou
`LIVRAISON.md`) contenant :

1. le chemin de l'archive, sa version, et ce qui a changé ;
2. si `schema_version` a changé : « les données existantes ne seront plus utilisées,
   réimporter le fichier source » ;
3. le résultat de `hocnota-scripts test` ;
4. les étapes HocNota du §12 qui restent à faire, adaptées au paquet (nom de l'entrée,
   extension, motif de nom de fichier, outils, rédacteurs pressentis) ;
5. 3 à 5 questions de recette à poser dans le chat avec la réponse attendue.

---

## 12. Mise en production sur HocNota (étapes humaines)

### 12.1 Importer l'archive — gestionnaire des compétences

**Manager → Outils → Paquets HNS → Importer une archive** : choisir le fichier
`.hnpkg` et l'espace de stockage (ignoré pour une nouvelle version d'un paquet
existant). L'archive est entièrement contrôlée ; un refus donne la liste des erreurs
(ex. « binaire natif interdit », « mots-clés non portables »).

- Premier import : le paquet est créé, il est **en attente d'approbation** (§12.2).
- Import suivant (même `name`, nouvelle `version`) : si le paquet est approuvé, la
  nouvelle version est **en service dès l'import**, sans nouvelle approbation.
- Même version déjà importée : refus (409) — incrémenter la version.

### 12.2 Approuver le paquet — administrateur, première livraison seulement

**Admin → Compétences → Paquets HNS en attente d'approbation** :
**Examiner** (revue de sécurité par l'IA, facultative) puis **Approuver**.
L'approbation se donne une seule fois, au paquet : les mises à jour n'y repassent pas.

Sur la même page, vérifier que le bac à sable est **opérationnel** et que le **bac à
sable des imports** l'est aussi. L'exécution des scripts doit être activée sur la
plateforme. Si l'organisation désactive « Exiger une approbation administrateur », un
nouveau paquet s'exécute dès son premier import (déconseillé).

### 12.3 Câbler le pipeline de chat — gestionnaire de pipelines

Dans **Manager → Designer**, créer ou ouvrir un pipeline de chat et poser :

| Nœud (bibliothèque) | Réglage |
|---|---|
| **Entrée chat** (Chat) | — |
| **Document support** (Entrée / Sortie) | Nombre maximal de fichiers suffisant (une conversation cumule ses pièces jointes). |
| **Script** (Analyse IA) | Paquet ; outils à masquer éventuellement ; **Droits d'écriture** (équipes / personnes). |
| **Agent IA** (Analyse IA) | Mode **Chat** ; un agent dont le modèle **gère les appels d'outils** ; « Utiliser les documents supports » inutile pour le fichier importé. |
| **Sortie chat** (Chat) | — |

Liens :

```
Document support ──► Entrée chat (patte « support »)
Document support ──► Script (entrée « Documents supports », à gauche)
Script (sortie « MCP », en haut) ──► Agent IA (patte « MCP »)
Entrée chat ──► Agent IA ──(patte « réponse »)──► Sortie chat
```

**Enregistrer**. Les droits d'écriture se choisissent parmi les membres des équipes
auxquelles le pipeline est affecté : affecter le pipeline à ses équipes d'abord
(liste des pipelines → **Équipes**).

**Variante : message d'erreur personnalisé.** Si l'import échoue, le job s'arrête avec
le message du script. Pour le remplacer par le vôtre, ajoutez :

| Nœud | Réglage |
|---|---|
| **Message d'erreur** (Flux) | Le message à afficher. |
| **Sortie erreur** (Entrée / Sortie) | — |

```
Script (sortie « erreur », à droite) ──► Message d'erreur ──► Sortie erreur
```

Le job passe alors au statut « Refusé » (non facturé) avec votre message ; sans cette
liaison, il est en « Échec » avec le message du script. Le détail des nœuds montre
l'étape en échec et le journal du script.

### 12.4 Charger les données

Dans le panneau du nœud HNS, section **Données** :

- **Importer un fichier maintenant…** avec le fichier source réel → une version 1
  « en vigueur » apparaît, avec les métadonnées renvoyées par l'étape ;
- sinon, les outils utilisent le seed (« Aucun import : les outils lisent les données
  initiales »).

**Essayer un outil** sur les données en vigueur, avec des arguments JSON, pour un
contrôle rapide.

### 12.5 Recette et activation

1. **▶ Tester** (panneau de test) : poser les questions de recette. Le **détail des
   nœuds** montre l'import éventuel et chaque appel d'outil, étiqueté « Paquet ».
   Un fichier joint dans le panneau de test est importé **pour le test seulement**.
2. Vérifier que chaque montant de la réponse provient d'un appel d'outil.
3. **Activer** le pipeline. Les utilisateurs des équipes affectées le voient dans
   l'application (onglet 💬).

---

## 13. Faire vivre le paquet

### Nouvelles données (cas courant)

- Un **rédacteur** joint le nouveau fichier dans le chat : il est importé à son
  prochain message, la nouvelle version vaut pour **tout le monde**, l'agent le
  confirme. Un fichier déjà importé (même contenu) ne l'est jamais deux fois.
- Ou un gestionnaire utilise **Importer un fichier maintenant…** dans le nœud.
- **Revenir en arrière** : panneau du nœud → historique → **Rendre courante**.
  HocNota garde les 5 dernières versions de données.
- Un import en échec ne change rien aux données en vigueur ; le message d'erreur est
  dans « Derniers imports » et l'agent prévient l'utilisateur.

### Nouvelle version du code

| Changement | Version | `schema_version` | Données existantes |
|---|---|---|---|
| Correctif d'un outil, nouvelle formulation | Z+1 (1.0.1) | inchangé | conservées |
| Nouvel outil, nouveau paramètre optionnel | Y+1 (1.1.0) | inchangé | conservées |
| Structure de la base modifiée | Y+1 ou X+1 | **+1** | **ignorées** (retour au seed) : réimporter le fichier source |
| Nouvelle entrée, outil supprimé, paramètre obligatoire changé | X+1 (2.0.0) | selon le cas | selon le cas |

Puis : `build` → import (§12.1). **La nouvelle version est en service dès l'import** :
aucune validation ne la précède, `hocnota-scripts test` doit donc être vert avant. Si
`schema_version` a changé, les données existantes sont ignorées immédiatement :
réimporter aussitôt le fichier source.

**Retour arrière du code** : supprimer la version fautive dans la fiche du paquet
(Manager → Paquets HNS → Ouvrir → Versions) ; la version précédente reprend la
main.

---

## 14. Dépannage

| Symptôme | Cause probable | Action |
|---|---|---|
| `dépendances natives refusées` au build | Dépendance compilée (numpy, lxml…) | La retirer ; réécrire en Python pur. |
| `mots-clés non portables` / `type non pris en charge` | Type de paramètre hors §0 règle 4 | Utiliser `Literal`, `list[str]`, `date`… |
| `nom d'outil réservé` / `nom de paramètre réservé` | §0 règle 5 | Renommer. |
| Import refusé (409) | Version déjà importée | Incrémenter `version`. |
| Nœud « non approuvé » | Première approbation pas encore donnée | Approbation (§12.2). |
| Le fichier joint n'est pas importé | Mauvaise extension ou `filename_pattern` ; nœud non relié au Document support ; fichier identique déjà importé ; auteur non rédacteur (l'agent le dit) | Vérifier le câblage, le nom du fichier, les droits d'écriture, « Derniers imports ». |
| `délai d'exécution dépassé` | Étape > `timeout_s` ou outil > 15 s | Optimiser (openpyxl `read_only`, index SQLite), augmenter `timeout_s` dans les limites. |
| `artefact trop volumineux` / `sorties trop volumineuses` | Base > 64 Mio | Élaguer, normaliser, `VACUUM`. |
| `bac à sable occupé` | Appels concurrents nombreux | Réessai automatique par l'agent ; réduire le nombre d'appels par réponse. |
| « Données … au format différent » | `schema_version` modifié | Réimporter le fichier source. |
| L'agent répond sans appeler d'outil | Modèle sans appels d'outils fiables (petits modèles locaux) | Changer le modèle de l'agent ; renforcer `instructions.md`. Le détail des nœuds affiche « Aucun outil appelé ». |
| Résultat tronqué | Sortie > `max_output_chars` | Réduire la sortie, paginer, résumer. |

---

## 15. Définition de « terminé » pour une IA de code

- [ ] `hocnota-scripts validate` : valide.
- [ ] `hocnota-scripts run-step` sur le fichier source réel : OK, métadonnées correctes.
- [ ] `hocnota-scripts test` : 100 % vert, ≥ 15 cas, valeurs issues de la source de vérité.
- [ ] `hocnota-scripts test --sandbox` : vert (si Docker disponible).
- [ ] Chaque outil : sortie < 4 000 caractères sur les cas courants, description et `Args:` rédigées pour le modèle.
- [ ] `instructions.md` : règle « jamais de montant de mémoire », date des données, mentions.
- [ ] `version` incrémentée ; `schema_version` incrémenté si la base a changé.
- [ ] `hocnota-scripts build` sans erreur ; archive ≤ 32 Mo.
- [ ] Fiche de livraison (§11) remise.

---

## 16. Contrat technique (référence)

| | |
|---|---|
| Format d'archive | `hocnota-package/1` : `manifest.json`, `pkg/`, `vendor/`, `seed/`, `instructions.md` |
| Exécution | Python 3.12, sans réseau, système de fichiers en lecture seule, `/tmp` noexec |
| Lanceur | protocole 1 : `launcher.py step` / `launcher.py tool <nom>`, requête JSON sur stdin, résultat dans `output/result.json` |
| Artefacts en entrée d'outil | ouverts en lecture seule (`mode=ro&immutable=1`) |
| Limites voie « imports » | 120 s, 1,5 Gio, charge utile 96 Mio, sorties 64 Mio |
| Limites voie « outils » | 60 s par outil, 512 Mio, charge utile 24 Mio (archive sans seed + artefacts lus) |
| Compatibilité | SDK 0.x ↔ HocNota avec `app/script_packages/` (format 1) |

Le schéma JSON du manifeste est dans `hocnota_scripts/schema/hocnota-package-1.json`.
