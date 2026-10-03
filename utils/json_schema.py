"""Minimal JSON schema validation.

Replaces the bundled jsonschema package, whose attrs dependency clashes with
the copy Blender uses itself. Only the "type" and "properties" keywords are
supported, which is all the schemas in this add-on use.
"""

_TYPES = {
    "object": dict,
    "array": (list, tuple),
    "string": str,
    "boolean": bool,
    "number": (int, float),
    "integer": int,
    "null": type(None),
}


class ValidationError(Exception):
    pass


def validate(instance, schema: dict, path: str = "$"):
    """Raise ValidationError if instance doesn't match schema."""
    expected = schema.get("type")
    if expected is not None:
        types = _TYPES[expected]
        # bool is a subclass of int, but JSON treats them as different types.
        if (isinstance(instance, bool) and expected in {"number", "integer"}) or not isinstance(instance, types):
            raise ValidationError(f"{path}: expected {expected}, got {type(instance).__name__}")

    properties = schema.get("properties")
    if properties and isinstance(instance, dict):
        for key, subschema in properties.items():
            if key in instance:
                validate(instance[key], subschema, f"{path}.{key}")
