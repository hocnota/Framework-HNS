import csv

from hocnota_scripts import Context, Reject, check


@check(accept=[".csv"], artifacts=["prix"], timeout_s=20)
def verifier_grille(ctx: Context, document):
    with open(document, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows or "produit" not in rows[0]:
        raise Reject("Grille illisible : colonne « produit » absente.")
    connus = {r[0] for r in ctx.sqlite("prix").execute("SELECT produit FROM prix")}
    inconnus = sorted({r["produit"] for r in rows} - connus)
    if inconnus == sorted({r["produit"] for r in rows}):
        raise Reject("Aucun produit de la grille n'est connu.")
    return {"lignes": len(rows), "produits_nouveaux": len(inconnus)}
