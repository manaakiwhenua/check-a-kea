def normalise_key(key):
    """Convert a user-entered shortcut string to a QKeySequence-compatible form.

    Rules:
    - Bare lowercase letter "e"  → "E"        (Qt::Key_E, no modifiers)
    - Bare uppercase letter "E"  → "Shift+E"  (Shift + Qt::Key_E)
    - Modifier + lowercase "shift+e" → "shift+E"  (uppercases key part so Qt
      maps it to Qt::Key_E rather than Unicode 101)
    - Pure digit string "55"  → "5, 5"   (Qt multi-keystroke sequence)
    - Pure digit string "120" → "1, 2, 0"
    - Everything else (digits, named keys like F1/Return) is returned unchanged.
    """
    key = key.strip()
    if not key:
        return key

    # Pure digit run longer than 1: expand to comma-separated single-key sequence
    if key.isdigit() and len(key) > 1:
        return ", ".join(key)

    # Pure-alpha run longer than 1: expand each letter individually.
    # key.isalpha() excludes "F1", "1a" etc.
    # Lowercase ch → uppercase (no shift); uppercase ch → Shift+ch.
    # Note: Qt named keys like "Return"/"Escape" are also pure-alpha, but they
    # are unlikely validation shortcuts and users needing them can use modifier
    # combos instead.
    if key.isalpha() and len(key) > 1:
        return ", ".join(f"Shift+{ch}" if ch.isupper() else ch.upper() for ch in key)

    # Split off modifiers (everything before the last "+")
    parts = key.rsplit("+", 1)
    key_part = parts[-1].strip()

    if len(key_part) == 1 and key_part.isalpha():
        if key_part.isupper() and len(parts) == 1:
            # Bare uppercase letter → treat as Shift+letter
            return f"Shift+{key_part}"
        else:
            # Lowercase (with or without modifier) → uppercase the key part
            parts[-1] = key_part.upper()
            return "+".join(parts)

    return key


def shortcut_conflicts(keys):
    """Return the set of keys that conflict with at least one other key.

    A key conflicts if it is a duplicate of another key, or if it is a string
    prefix of another key (or vice versa).  Prefix conflicts matter because
    QKeySequence("1") and QKeySequence("1, 2") create ambiguity: Qt must wait
    after the first keystroke to decide which shortcut fired.

    Empty strings are ignored.
    """
    non_empty = [k for k in keys if k]
    conflicting = set()
    for k in non_empty:
        others = [o for o in non_empty if o != k]
        is_dup = non_empty.count(k) > 1
        is_prefix = any(k.startswith(o) or o.startswith(k) for o in others)
        if is_dup or is_prefix:
            conflicting.add(k)
    return conflicting
