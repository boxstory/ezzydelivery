# Purpose: Resolve and discover dot/bracket paths inside a JSON order payload.
# Used by: ezzy_api/store_api.py (apply a saved mapping), workforce/views.py (detect
#          the paths in a pasted sample so staff can pick them from a dropdown).
# Notes: Pure functions, no models. Path syntax matches the Shopify virtual columns
#        already used by the mapping manager: "customer.name", "items[0].qty",
#        plus "items[].name" meaning every element of the list.

import re

# Sentinel for the "[]" segment — every element, rather than one index.
EVERY = object()

_TOKEN_RE = re.compile(r'\[(\d*)\]|([^.\[\]]+)')

# A pasted sample is untrusted input: a deeply nested or enormous document must
# not turn field detection into a hang.
MAX_DEPTH = 6
MAX_PATHS = 400
MAX_LIST_SAMPLE = 3


def tokenize(path):
    """'items[0].name' -> ['items', 0, 'name'];  'items[].name' -> ['items', EVERY, 'name']"""
    tokens = []
    for index, key in _TOKEN_RE.findall(str(path or '')):
        if key:
            tokens.append(key)
        elif index == '':
            tokens.append(EVERY)
        else:
            tokens.append(int(index))
    return tokens


def path_get(data, path, default=None):
    """Value at ``path``. A path containing '[]' always returns a list."""
    tokens = tokenize(path)
    if not tokens:
        return default

    current = [data]
    fanned = False
    for token in tokens:
        nxt = []
        for node in current:
            if token is EVERY:
                fanned = True
                if isinstance(node, list):
                    nxt.extend(node)
            elif isinstance(token, int):
                if isinstance(node, list) and -len(node) <= token < len(node):
                    nxt.append(node[token])
            elif isinstance(node, dict) and token in node:
                nxt.append(node[token])
        current = nxt
        if not current:
            return [] if fanned else default

    if fanned:
        return current
    return current[0] if current else default


def discover_paths(data, prefix='', found=None, depth=0):
    """Every leaf path in a sample payload, as pickable labels.

    A list yields both indexed paths for the first few elements
    ("items[0].name") and one collapsed path ("items[].name") that stands for
    all of them — so a sample carrying one line still offers the mapping needed
    for an order that carries five.
    """
    if found is None:
        found = []
    if depth > MAX_DEPTH or len(found) >= MAX_PATHS:
        return found

    if isinstance(data, dict):
        for key, value in data.items():
            child = f'{prefix}.{key}' if prefix else str(key)
            discover_paths(value, child, found, depth + 1)
    elif isinstance(data, list):
        if data and isinstance(data[0], (dict, list)):
            discover_paths(data[0], f'{prefix}[]', found, depth + 1)
            for index, item in enumerate(data[:MAX_LIST_SAMPLE]):
                discover_paths(item, f'{prefix}[{index}]', found, depth + 1)
        elif prefix and prefix not in found:
            found.append(prefix)
    elif prefix and prefix not in found:
        found.append(prefix)

    return found
