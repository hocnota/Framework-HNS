"""Outils offerts à l'agent. Chaque paramètre typé devient un champ du schéma
JSON de l'outil ; la docstring donne sa description."""

from hocnota_scripts import Context, tool


@tool(artifacts=["base"])
def compter_lignes(ctx: Context) -> dict:
    """Nombre de lignes importées."""
    (n,) = ctx.sqlite("base").execute("SELECT count(*) FROM lignes").fetchone()
    return {"lignes": n}


@tool(artifacts=["base"])
def lire_lignes(ctx: Context, limite: int = 10) -> dict:
    """Premières lignes de la table.

    Args:
        limite: nombre maximal de lignes renvoyées (1 à 100)
    """
    import sqlite3

    limite = max(1, min(int(limite), 100))
    conn = ctx.sqlite("base", row_factory=sqlite3.Row)
    rows = conn.execute("SELECT * FROM lignes LIMIT ?", (limite,)).fetchall()
    return {"lignes": [dict(r) for r in rows]}
