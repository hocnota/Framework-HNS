"""Décorateurs et contexte utilisés par le code d'un paquet.

    from hocnota_scripts import Context, step, tool

    @step(inputs=["catalogue"], outputs=["produits"], timeout_s=90)
    def importer(ctx: Context, catalogue):
        ...                       # écrit ctx.output_path("produits")
        return {"maj_stocks": "2026-10-15"}   # métadonnées affichées à l'agent

    @tool(artifacts=["produits"])
    def chiffrer_commande(ctx: Context, date_livraison: date, quantite: int = 1) -> dict:
        '''Chiffre une commande.

        Args:
            date_livraison: date de livraison souhaitée (AAAA-MM-JJ)
            quantite: nombre d'unités
        '''
        conn = ctx.sqlite("produits")
        ...

    @check(accept=[".xlsx"], artifacts=["produits"])
    def verifier_catalogue(ctx: Context, document):
        if not est_conforme(document):
            raise Reject("Le catalogue n'a pas le format attendu : onglet « Produits » absent.")
        return {"onglets": 4}     # constats donnés aux agents reliés au nœud

Un contrôle de document s'exécute quand le nœud HNS est placé sur le flux du
document : il reçoit le fichier du job, et soit le laisse passer (en renvoyant des
constats), soit le refuse en levant ``Reject`` — le message est celui que verra
l'utilisateur. Tout autre échec (exception, délai) est un contrôle impossible, qui
sort lui aussi par la sortie « erreur » du nœud.

Dans le bac à sable HocNota, ce module est remplacé par celui du lanceur :
les décorateurs y renvoient la fonction telle quelle (le manifeste, construit
ici, dit déjà ce qui est une étape ou un outil) et ``Context`` y est identique.
Le code d'un paquet ne doit donc rien attendre d'autre de ce module.
"""

from pathlib import Path

from hocnota_scripts._launcher_v1 import Context, Reject  # mêmes classes que dans le bac à sable

InputFile = Path

STEP_ATTR = "__hocnota_step__"
TOOL_ATTR = "__hocnota_tool__"
CHECK_ATTR = "__hocnota_check__"


def _decorator(attr: str, defaults: dict):
    def factory(fn=None, **options):
        unknown = set(options) - set(defaults)
        if unknown:
            raise TypeError(f"options inconnues : {sorted(unknown)}")

        def mark(func):
            setattr(func, attr, {**defaults, **options})
            return func

        return mark(fn) if callable(fn) else mark

    return factory


step = _decorator(STEP_ATTR, {
    "name": None, "description": None, "inputs": None, "outputs": None, "timeout_s": None,
})
step.__doc__ = "Marque une étape d'import : (ctx, **entrées) → écrit ses sorties, renvoie un dict de métadonnées ou None."

tool = _decorator(TOOL_ATTR, {
    "name": None, "description": None, "artifacts": None, "timeout_s": None,
    "max_output_chars": None, "input_schema": None,
})
tool.__doc__ = "Marque un outil offert à l'agent : (ctx, **arguments) → valeur JSON."

check = _decorator(CHECK_ATTR, {
    "name": None, "description": None, "accept": None, "filename_pattern": None,
    "artifacts": None, "timeout_s": None,
})
check.__doc__ = (
    "Marque un contrôle de document : (ctx, document) → dict de constats ou None ; "
    "lève Reject(\"message\") pour refuser le document."
)
