from hocnota_scripts import Context, tool


@tool(artifacts=["prix"])
def prix_produit(ctx: Context, produit: str):
    """Prix d'un produit de la grille.

    Args:
        produit: Nom du produit
    """
    row = ctx.sqlite("prix").execute(
        "SELECT montant FROM prix WHERE produit = ?", (produit,)
    ).fetchone()
    if row is None:
        return {"trouve": False, "produit": produit}
    return {"trouve": True, "produit": produit, "montant": row[0]}


@tool(artifacts=["prix"])
def lister_produits(ctx: Context):
    """Liste des produits et de la date de la grille."""
    rows = ctx.sqlite("prix").execute("SELECT produit FROM prix ORDER BY produit").fetchall()
    return {"produits": [r[0] for r in rows]}
