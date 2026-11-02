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

Une exception levée par une étape arrête le job : son message est celui que verra
l'utilisateur (ou celui que la sortie « erreur » du nœud HNS remplace).

Dans le bac à sable HocNota, ce module est remplacé par celui du lanceur :
les décorateurs y renvoient la fonction telle quelle (le manifeste, construit
ici, dit déjà ce qui est une étape ou un outil) et ``Context`` y est identique.
Le code d'un paquet ne doit donc rien attendre d'autre de ce module.
"""

from pathlib import Path

from hocnota_scripts._launcher_v1 import Context  # même classe que dans le bac à sable

InputFile = Path

STEP_ATTR = "__hocnota_step__"
TOOL_ATTR = "__hocnota_tool__"


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
