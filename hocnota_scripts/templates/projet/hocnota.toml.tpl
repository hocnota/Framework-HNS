# Paquet HNS — format hocnota-package/1.
# Les étapes (@step) et les outils (@tool) sont découverts dans `modules`.

[package]
name = "{{name}}"
version = "0.1.0"
description = "Décrivez ce que ce paquet permet à un agent de faire."
source = "src"
modules = ["{{module}}.etl", "{{module}}.outils"]
instructions = "instructions.md"
# Dépendances PUR Python uniquement (wheels py3-none-any) : elles sont
# embarquées dans l'archive, le bac à sable n'a pas accès au réseau.
dependencies = ["openpyxl>=3.1"]

# Fichier fourni par l'utilisateur (joint au chat) qui déclenche l'import.
[[inputs]]
name = "classeur"
accept = [".xlsx"]
description = "Classeur Excel source"

# Données produites par l'import et lues par les outils.
[[artifacts]]
name = "base"
kind = "sqlite"
filename = "base.db"
schema_version = 1
# seed = "seed/base.db"   # base livrée avec le paquet, utilisée tant qu'aucun import n'a eu lieu
