# Framework, épinglé sur la version qui a créé ce projet. Pour en changer :
# modifier le tag, `pip install -r requirements-dev.txt`, puis `hocnota-scripts test`.
hocnota-scripts @ git+https://github.com/hocnota/Framework-HNS@v{{sdk_version}}
# Dépendances du paquet, pour l'exécution locale (même liste que `dependencies`
# dans hocnota.toml — pur Python uniquement).
openpyxl>=3.1
