"""Signature Python → ``input_schema`` JSON (sous-ensemble portable du format 1).

Types pris en charge : ``str``, ``int``, ``float``, ``bool``, ``datetime.date``
(chaîne au format date), ``Literal[...]`` (énumération), ``list[...]`` de ces
types, ``Optional[...]`` / ``X | None``. Les descriptions viennent de la section
``Args:`` de la docstring (style Google). Un paramètre avec valeur par défaut
n'est pas obligatoire ; sa valeur par défaut est publiée si elle est JSON.
"""

import datetime
import inspect
import json
import re
import types
import typing

_PRIMITIVES = {str: "string", int: "integer", float: "number", bool: "boolean"}


class SchemaError(TypeError):
    pass


def _unwrap_optional(tp):
    origin = typing.get_origin(tp)
    if origin in (typing.Union, types.UnionType):
        args = [a for a in typing.get_args(tp) if a is not type(None)]
        if len(args) == 1:
            return args[0], True
    return tp, False


def _scalar(tp, where: str) -> dict:
    if tp in _PRIMITIVES:
        return {"type": _PRIMITIVES[tp]}
    if tp is datetime.date:
        return {"type": "string", "format": "date"}
    if typing.get_origin(tp) is typing.Literal:
        values = list(typing.get_args(tp))
        kinds = {type(v) for v in values}
        if len(kinds) != 1 or next(iter(kinds)) not in _PRIMITIVES:
            raise SchemaError(f"{where} : Literal doit contenir des valeurs simples d'un même type")
        return {"type": _PRIMITIVES[next(iter(kinds))], "enum": values}
    raise SchemaError(f"{where} : type non pris en charge ({tp!r})")


def _property(tp, where: str) -> dict:
    if typing.get_origin(tp) is typing.Annotated:
        base, *extra = typing.get_args(tp)
        prop = _property(base, where)
        desc = next((e for e in extra if isinstance(e, str)), None)
        if desc:
            prop["description"] = desc
        return prop
    if typing.get_origin(tp) in (list, typing.List):
        (item,) = typing.get_args(tp) or (None,)
        if item is None:
            raise SchemaError(f"{where} : précisez le type des éléments (list[str]…)")
        return {"type": "array", "items": _scalar(item, where)}
    return _scalar(tp, where)


def parse_docstring_args(doc: str | None) -> dict[str, str]:
    """``Args:`` (style Google) → {paramètre: description}."""
    out: dict[str, str] = {}
    if not doc:
        return out
    lines = inspect.cleandoc(doc).splitlines()
    in_args, current, indent = False, None, None
    for line in lines:
        if re.match(r"^(Args|Arguments|Paramètres|Parameters)\s*:\s*$", line.strip()):
            in_args, current = True, None
            continue
        if in_args:
            if line and not line.startswith(" "):
                break  # section suivante
            m = re.match(r"^(\s+)(\w+)\s*(\([^)]*\))?\s*:\s*(.*)$", line)
            if m and (indent is None or len(m.group(1)) <= indent):
                indent = len(m.group(1))
                current = m.group(2)
                out[current] = m.group(4).strip()
            elif current and line.strip():
                out[current] = (out[current] + " " + line.strip()).strip()
    return out


def summary(doc: str | None) -> str:
    """Premier paragraphe de la docstring."""
    if not doc:
        return ""
    return inspect.cleandoc(doc).split("\n\n", 1)[0].replace("\n", " ").strip()


def infer_input_schema(func) -> dict:
    sig = inspect.signature(func)
    hints = typing.get_type_hints(func, include_extras=True)
    descriptions = parse_docstring_args(func.__doc__)
    params = list(sig.parameters.values())
    if not params:
        raise SchemaError(f"{func.__name__} : le premier paramètre doit être le contexte (ctx)")
    properties: dict[str, dict] = {}
    required: list[str] = []
    for p in params[1:]:  # le premier est ctx
        where = f"{func.__name__}({p.name})"
        if p.kind not in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY):
            raise SchemaError(f"{where} : *args / **kwargs non pris en charge")
        if p.name not in hints:
            raise SchemaError(f"{where} : annotation de type manquante")
        tp, optional = _unwrap_optional(hints[p.name])
        prop = _property(tp, where)
        if p.name in descriptions:
            prop.setdefault("description", descriptions[p.name])
        if p.default is not inspect.Parameter.empty:
            if p.default is not None:
                default = p.default.isoformat() if isinstance(p.default, datetime.date) else p.default
                try:
                    json.dumps(default)
                    prop["default"] = default
                except TypeError:
                    pass
        elif not optional:
            required.append(p.name)
        properties[p.name] = prop
    schema: dict = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema
