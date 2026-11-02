"""Framework HNS : création de paquets HNS (format hocnota-package/1).

Le code d'un paquet n'importe que ``step``, ``tool``, ``check``, ``Reject``,
``Context`` et ``InputFile`` : c'est tout ce que le lanceur de HocNota fournit à l'exécution.
"""

from hocnota_scripts.api import Context, InputFile, Reject, check, step, tool
from hocnota_scripts.rules import FORMAT

__all__ = ["Context", "InputFile", "Reject", "check", "step", "tool", "FORMAT"]
__version__ = "0.2.0"
