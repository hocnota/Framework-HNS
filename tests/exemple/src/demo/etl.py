import csv
import sqlite3

from hocnota_scripts import Context, step


@step(inputs=["grille"], outputs=["prix"], timeout_s=30)
def importer(ctx: Context, grille):
    out = ctx.output_path("prix")
    print("import de", grille.name)  # must not corrupt the result channel
    conn = sqlite3.connect(out)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE prix (produit TEXT PRIMARY KEY, montant REAL)")
    with open(grille, newline="", encoding="utf-8") as fh:
        rows = [(r["produit"], float(r["montant"])) for r in csv.DictReader(fh)]
    conn.executemany("INSERT INTO prix VALUES (?, ?)", rows)
    conn.commit()
    conn.close()
    return {"lignes": len(rows), "source": grille.name}
