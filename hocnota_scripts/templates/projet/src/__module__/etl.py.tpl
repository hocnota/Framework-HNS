"""Import : classeur Excel → base SQLite."""

import sqlite3

from hocnota_scripts import Context, step


@step(inputs=["classeur"], outputs=["base"], timeout_s=90)
def importer(ctx: Context, classeur):
    """Charge la première feuille du classeur dans la table `lignes`."""
    from openpyxl import load_workbook  # embarqué dans vendor/ par `hocnota-scripts build`

    wb = load_workbook(classeur, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    rows = ws.iter_rows(values_only=True)
    header = [str(h) for h in next(rows)]

    conn = sqlite3.connect(ctx.output_path("base"))
    cols = ", ".join(f'"{h}"' for h in header)
    conn.execute(f"CREATE TABLE lignes ({cols})")
    marks = ", ".join("?" for _ in header)
    n = 0
    for row in rows:
        conn.execute(f"INSERT INTO lignes VALUES ({marks})", row[: len(header)])
        n += 1
    conn.commit()
    conn.close()
    # Métadonnées montrées à l'agent avec l'état des données.
    return {"lignes": n, "feuille": ws.title}
