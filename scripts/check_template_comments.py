# Purpose: Fail the build when a template uses {# ... #} across more than one line.
# Used by: scripts/predeploy.sh (gate step), runnable standalone.
# Notes: Django's {# #} is SINGLE-LINE only. Spanning lines is not a comment — the text and the
#        braces render straight onto the page for users to read. Multi-line needs {% comment %}.

import re
import sys
from pathlib import Path

SKIP = ('/venv', 'staticroot/', 'node_modules', '/.git/')


def find_broken(root='.'):
    broken = []
    for path in Path(root).rglob('*.html'):
        if any(s in str(path) for s in SKIP):
            continue
        try:
            text = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for match in re.finditer(r'\{#', line):
                if '#}' not in line[match.end():]:
                    broken.append((path, lineno, line.strip()[:90]))
    return broken


def main():
    broken = find_broken()
    if not broken:
        print('Template comments OK — no multi-line {# #} found.')
        return 0
    print(f'{len(broken)} multi-line {{# #}} comment(s) — these RENDER AS VISIBLE TEXT:\n')
    for path, lineno, snippet in broken:
        print(f'  {path}:{lineno}\n      {snippet}')
    print('\nFix: put the comment on one line, or use {% comment %} ... {% endcomment %}.')
    return 1


if __name__ == '__main__':
    sys.exit(main())
