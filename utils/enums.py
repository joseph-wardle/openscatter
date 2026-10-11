"""Keep the items that dynamic EnumProperty callbacks return alive.

Blender doesn't copy the strings in the items a callback returns, so Python
has to keep them, or dropdowns can show garbled names and Blender can crash.
"""

_kept = {}  # (callback name, owner pointer) -> the items it last returned


def keep(name: str, owner, items: list) -> list:
    """Return items, holding on to them until the callback named name returns
    different ones for owner. Unchanged items are returned as the same list,
    so strings Blender still points to stay valid."""
    key = (name, owner.as_pointer())
    kept = _kept.get(key)
    if kept != items:
        _kept[key] = kept = items
    return kept
