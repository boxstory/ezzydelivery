# Purpose: Scan the codebase for UI/CSS/a11y/security-hygiene debt and regenerate .claude/docs/12-testing-qa/qa_todos.md.
# Used by: `python scripts/qa_scan.py`, and `python manage.py qa_evaluate --update-todos`.
# Notes: READ-ONLY over the codebase — it only writes qa_todos.md + qa_scan.json. Findings are anchored to
#        FILE + COUNT, never line numbers, because line numbers were what rotted the previous hand-written
#        list. Human triage (`[x]`, `[~]` wontfix, trailing `— NOTE: ...`) is carried forward across runs
#        via the `<!-- id: ... -->` marker on each finding line. Never un-ticks a human decision.

import json
import re
import sys
from collections import OrderedDict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TODOS_PATH = ROOT / '.claude' / 'docs' / '12-testing-qa' / 'qa_todos.md'
JSON_PATH = ROOT / '.claude' / 'docs' / '12-testing-qa' / 'qa_scan.json'

# ---------------------------------------------------------------- exclusions

# Never scanned, in any check.
SKIP_ALL = (
    '/staticroot/', '/node_modules/', '/venv', '/.git/', '/.gemini/',
)

# Vendor CSS and the Brand Kit override layer. The Brand Kit files use !important
# BY DESIGN — they load after Bootstrap specifically to beat its utility classes.
# Counting them as debt is how the previous audit drowned in noise.
SKIP_CSS = SKIP_ALL + (
    'bootstrap-custom', '/brandkit.css', '/brandkit-overrides.css',
)

# Bootstrap ships visual-test HTML pages; they are not our templates.
SKIP_HTML = SKIP_ALL + (
    'bootstrap-custom',
)

# Build scripts, one-off maintenance scripts, tests and migrations are not shipped code.
SKIP_PY = SKIP_ALL + (
    '/migrations/', '/tests/', '/test_', '/management/commands/',
    '/scripts/', 'compile_bootstrap',
)


def _walk(suffix, skips):
    for path in sorted(ROOT.rglob(f'*{suffix}')):
        rel = '/' + str(path.relative_to(ROOT))
        if any(s in rel for s in skips):
            continue
        yield path, rel.lstrip('/')


def _read(path):
    try:
        return path.read_text(encoding='utf-8', errors='ignore')
    except OSError:
        return ''


def _lines_matching(text, pattern):
    """Return (count, [first few 1-indexed line numbers]) for a compiled pattern."""
    hits = []
    total = 0
    for n, line in enumerate(text.splitlines(), 1):
        found = len(pattern.findall(line))
        if found:
            total += found
            if len(hits) < 5:
                hits.append(n)
    return total, hits


# ------------------------------------------------------------------- checks
#
# Each check returns a dict:
#   key       stable slug, used to build finding ids
#   title     section heading
#   why       one line on why it matters (so nobody has to re-derive intent)
#   items     [{'file': relpath, 'count': int, 'detail': str, 'lines': [int]}]
#   closed_note  set when the category has zero findings

RE_IMPORTANT = re.compile(r'!important')
RE_FLOAT = re.compile(r'float:\s*(?:left|right)')
RE_HEX = re.compile(r'#[0-9a-fA-F]{3,8}\b')
RE_BRANDVAR = re.compile(r'var\(--')
RE_MEDIA = re.compile(r'@media')
RE_INLINE_STYLE = re.compile(r'\sstyle="')
RE_STYLE_TAG = re.compile(r'<style[\s>]')
RE_ONCLICK = re.compile(r'\sonclick=')
RE_IMG = re.compile(r'<img\b[^>]*>', re.S)
RE_ICON_BTN = re.compile(r'<button\b[^>]*>\s*<i\b[^>]*>\s*</i>\s*</button>', re.S)
RE_CLOSE_BTN = re.compile(r'<button\b[^>]*\bbtn-close\b[^>]*>', re.S)
RE_PRINT = re.compile(r'^\s*print\(')
RE_VIEW_DEF = re.compile(r'^def (\w+)\(request')


def check_important():
    items = []
    for path, rel in _walk('.css', SKIP_CSS):
        text = _read(path)
        count, lines = _lines_matching(text, RE_IMPORTANT)
        if count:
            items.append({'file': rel, 'count': count,
                          'detail': f'{count} `!important` declarations', 'lines': lines})
    items.sort(key=lambda i: -i['count'])
    return {
        'key': 'important',
        'title': '`!important` in project CSS',
        'why': 'Each one raises the specificity floor for every later rule in that file. '
               'Vendor CSS and the Brand Kit override layer are excluded — theirs is intentional.',
        'items': [i for i in items if i['count'] >= 20],
    }


def check_hardcoded_hex():
    """Hardcoded colours where a Brand Kit token should be used (CLAUDE.md rule)."""
    items = []
    for path, rel in _walk('.css', SKIP_CSS):
        text = _read(path)
        hexes = len(RE_HEX.findall(text))
        tokens = len(RE_BRANDVAR.findall(text))
        if hexes >= 100:
            share = tokens / (tokens + hexes) * 100 if (tokens + hexes) else 0
            items.append({
                'file': rel, 'count': hexes,
                'detail': f'{hexes} hardcoded hex vs {tokens} `var(--…)` — {share:.0f}% tokenised',
                'lines': [],
            })
    items.sort(key=lambda i: -i['count'])
    return {
        'key': 'hex',
        'title': 'Hardcoded colours instead of Brand Kit tokens',
        'why': 'CLAUDE.md requires all styling to use Brand Kit variables. A hardcoded hex will not '
               'follow a palette change, so every one is a future inconsistency.',
        'items': items,
    }


def check_inline_styles():
    items = []
    for path, rel in _walk('.html', SKIP_HTML):
        text = _read(path)
        count, lines = _lines_matching(text, RE_INLINE_STYLE)
        if count >= 10:
            items.append({'file': rel, 'count': count,
                          'detail': f'{count} inline `style="` attributes', 'lines': lines})
    items.sort(key=lambda i: -i['count'])
    return {
        'key': 'inline-style',
        'title': 'Inline `style="` attributes in templates',
        'why': 'CLAUDE.md forbids inline styles. Extract to BEM classes per the `/css-fix` skill. '
               'Only files with 10+ are listed; the long tail is in the totals.',
        'items': items,
    }


def check_style_tags():
    items = []
    for path, rel in _walk('.html', SKIP_HTML):
        text = _read(path)
        count, lines = _lines_matching(text, RE_STYLE_TAG)
        if count:
            items.append({'file': rel, 'count': count,
                          'detail': f'{count} `<style>` block(s)', 'lines': lines})
    items.sort(key=lambda i: -i['count'])
    return {
        'key': 'style-tag',
        'title': '`<style>` blocks in templates',
        'why': 'CLAUDE.md forbids `<style>` tags in templates — CSS belongs in a linked file '
               'loaded from `{% block extra_css %}`.',
        'items': items,
    }


def check_onclick():
    items = []
    for path, rel in _walk('.html', SKIP_HTML):
        text = _read(path)
        count, lines = _lines_matching(text, RE_ONCLICK)
        if count >= 8:
            items.append({'file': rel, 'count': count,
                          'detail': f'{count} inline `onclick=` handlers', 'lines': lines})
    items.sort(key=lambda i: -i['count'])
    return {
        'key': 'onclick',
        'title': 'Inline `onclick=` handlers',
        'why': 'Inline handlers cannot be CSP-hardened, break under HTMX swaps, and hide behaviour '
               'from the JS file. Replace with `data-action` attributes + event delegation — the '
               'pattern already used in the DMS and document-list templates.',
        'items': items,
    }


def check_missing_alt():
    items = []
    for path, rel in _walk('.html', SKIP_HTML):
        text = _read(path)
        bad = [t for t in RE_IMG.findall(text) if 'alt=' not in t]
        if bad:
            items.append({'file': rel, 'count': len(bad),
                          'detail': f'{len(bad)} `<img>` without `alt`', 'lines': []})
    items.sort(key=lambda i: -i['count'])
    return {
        'key': 'img-alt',
        'title': '`<img>` missing `alt`',
        'why': 'Screen readers announce the filename instead. Decorative images need `alt=""`.',
        'items': items,
        'closed_note': 'Every `<img>` in the project carries an `alt`. The last one — a decorative '
                       'brand logo in the warehouse inventory modal — was given `alt=""` on 2026-08-02.',
    }


def check_aria_buttons():
    items = []
    for path, rel in _walk('.html', SKIP_HTML):
        text = _read(path)
        icon = [t for t in RE_ICON_BTN.findall(text) if 'aria-label' not in t]
        close = [t for t in RE_CLOSE_BTN.findall(text) if 'aria-label' not in t]
        total = len(icon) + len(close)
        if total:
            parts = []
            if icon:
                parts.append(f'{len(icon)} icon-only')
            if close:
                parts.append(f'{len(close)} `btn-close`')
            items.append({'file': rel, 'count': total,
                          'detail': f'{total} button(s) without `aria-label` ({", ".join(parts)})',
                          'lines': []})
    items.sort(key=lambda i: -i['count'])
    return {
        'key': 'aria-button',
        'title': 'Buttons with no accessible name',
        'why': 'An icon-only or `btn-close` button with no `aria-label` is announced as just "button".',
        'items': items,
    }


def check_media_queries():
    """Substantial stylesheets with little or no responsive handling."""
    items = []
    for path, rel in _walk('.css', SKIP_CSS):
        text = _read(path)
        lines = text.count('\n')
        mq = len(RE_MEDIA.findall(text))
        if lines >= 400 and mq <= 2:
            items.append({'file': rel, 'count': mq,
                          'detail': f'{lines} lines but only {mq} `@media` block(s)', 'lines': []})
    items.sort(key=lambda i: i['count'])
    return {
        'key': 'media-query',
        'title': 'Large stylesheets with almost no breakpoints',
        'why': 'A 400+ line stylesheet with 0-2 media queries is very likely desktop-only.',
        'items': items,
    }


def check_floats():
    items = []
    for path, rel in _walk('.css', SKIP_CSS):
        text = _read(path)
        count, lines = _lines_matching(text, RE_FLOAT)
        if count:
            items.append({'file': rel, 'count': count,
                          'detail': f'{count} `float: left/right`', 'lines': lines})
    items.sort(key=lambda i: -i['count'])
    return {
        'key': 'float',
        'title': 'Float-based layout',
        'why': 'Legacy layout technique; use flexbox/grid.',
        'items': items,
        'closed_note': 'No float-based layout left in project CSS. The bulk went with the BEM restructure '
                       'and the deletion of `volte.css` (a 26-instance vendor bundle); the last two — '
                       '`zone-group-card` in fleet-mobile.css and the FAQ `summary::after` marker in '
                       'llm-knowledge-panel.css — were converted to flex on 2026-08-02.',
    }


def check_print():
    items = []
    for path, rel in _walk('.py', SKIP_PY):
        text = _read(path)
        count, lines = _lines_matching(text, RE_PRINT)
        if count:
            items.append({'file': rel, 'count': count,
                          'detail': f'{count} `print()` call(s)', 'lines': lines})
    items.sort(key=lambda i: -i['count'])
    return {
        'key': 'print',
        'title': '`print()` in shipped application code',
        'why': 'Writes to the Gunicorn stdout with no level or context. Use `logger.debug()`.',
        'items': items,
        'closed_note': 'No `print()` left in shipped app code — completed 2026-01-14. Remaining hits live '
                       'in build scripts, tests and management commands, which are excluded by design.',
    }


def _routed_view_names():
    """Every function name referenced from any urls.py — i.e. actually reachable over HTTP.

    Without this, the check drowns in private helpers (`_get_per_page`, `paginate_queryset`)
    that merely happen to take `request` as their first argument.
    """
    names = set()
    for path, rel in _walk('urls.py', SKIP_ALL):
        text = _read(path)
        names.update(re.findall(r'views\.(\w+)', text))
        names.update(re.findall(r'\bviews_\w+\.(\w+)', text))
        for block in re.findall(r'from [.\w]*views\w* import \(([^)]*)\)', text):
            names.update(n.strip() for n in block.replace('\n', '').split(','))
        for block in re.findall(r'from [.\w]*views\w* import ([^\n(]+)', text):
            names.update(n.strip() for n in block.split(','))
    return {n for n in names if n and n.isidentifier()}


def check_undecorated_views():
    """URL-routed `def name(request…)` with no decorator above it.

    Restricted to functions actually wired into a urls.py, so private helpers drop out.
    Still needs human triage: webhook receivers, public marketing pages, customer tracking
    and the driver signup flow are all correctly undecorated. That is what `[~]` is for.
    """
    routed = _routed_view_names()
    items = []
    for path, rel in _walk('.py', SKIP_PY):
        if not (path.name.startswith('views') or path.parent.name == 'views'):
            continue
        src = _read(path).split('\n')
        for i, line in enumerate(src):
            m = RE_VIEW_DEF.match(line)
            if not m:
                continue
            name = m.group(1)
            if name.startswith('_') or name not in routed:
                continue
            j = i - 1
            while j >= 0 and not src[j].strip():
                j -= 1
            if j < 0 or not src[j].lstrip().startswith('@'):
                # One finding per view, not per file: a single module routinely mixes
                # deliberately-public endpoints with genuinely unguarded ones, and a
                # file-level checkbox cannot express that split.
                items.append({
                    'file': rel, 'count': 1, 'lines': [],
                    'id': f'{rel}::{name}',
                    'label': f'`{rel}` → `{name}()`',
                    'detail': 'no decorator',
                })
    items.sort(key=lambda i: i['id'])
    return {
        'key': 'undecorated-view',
        'title': 'URL-routed views with no decorator (needs human triage)',
        'why': 'Restricted to functions wired into a `urls.py`; private helpers are filtered out. '
               'Some entries are correctly public (marketing pages, customer tracking, driver signup); '
               'others are a missing `@login_required` / `@staff_required`. Triage each, then tick or `[~]`.',
        'items': items,
    }


CHECKS = [
    check_inline_styles,
    check_onclick,
    check_hardcoded_hex,
    check_important,
    check_undecorated_views,
    check_aria_buttons,
    check_style_tags,
    check_media_queries,
    check_missing_alt,
    check_print,
    check_floats,
]


# ------------------------------------------------------- triage preservation

ID_RE = re.compile(r'^- \[(.)\] (.*?)\s*<!-- id: ([^\s]+) -->\s*(?:—\s*(NOTE: .*))?$')
MANUAL_START = '<!-- QA-SCAN:MANUAL-START -->'
MANUAL_END = '<!-- QA-SCAN:MANUAL-END -->'


def load_previous(path):
    """Return ({finding_id: (mark, note)}, [manual blocks]) from an existing generated file."""
    triage = {}
    manual = []
    if not path.exists():
        return triage, manual
    text = path.read_text(encoding='utf-8')

    for raw in text.splitlines():
        m = ID_RE.match(raw.strip())
        if m:
            mark, _label, fid, note = m.group(1), m.group(2), m.group(3), m.group(4)
            triage[fid] = (mark, note or '')

    depth = None
    for line in text.splitlines():
        if line.strip() == MANUAL_START:
            depth = []
        elif line.strip() == MANUAL_END and depth is not None:
            manual.append('\n'.join(depth))
            depth = None
        elif depth is not None:
            depth.append(line)
    return triage, manual


# -------------------------------------------------------------------- render

HEADER = """# QA Audit — EzzyDelivery

> **This file is generated.** Regenerate with `python scripts/qa_scan.py`
> (or `python manage.py qa_evaluate --update-todos`). Do not hand-edit the finding
> counts — they are overwritten on every run.
>
> **Your triage IS preserved.** The checkbox mark and any `— NOTE: …` you add to a
> finding line survive regeneration, keyed off the `<!-- id: … -->` marker. The scanner
> will never un-tick a decision you made.

## Marks

| Mark | Meaning |
|------|---------|
| `[ ]` | Open — not yet looked at |
| `[x]` | Done, or verified a non-issue |
| `[~]` | Won't fix / intentional — **add a `— NOTE:` saying why** |
| `[!]` | Confirmed and urgent |

Anything with a `[~]` needs a note. A bare `[~]` is indistinguishable from giving up.
"""

FOOTER_NOTE = """
---

## How to work this list

1. **Triage before fixing.** Several categories are raw counts a scanner cannot judge —
   `undecorated-view` especially. Mark the false positives `[~]` with a note first, so the
   next run reports a real number instead of a scary one.
2. **Use the existing skills.** `/css-fix` (`.claude/skills/css-fix.md`) already encodes the
   Bootstrap-first BEM pattern for the inline-style and `!important` work. `.claude/skills/brandkit.md`
   is the token table for the hardcoded-colour work.
3. **Re-run the scanner after a batch** so the counts move and the progress is visible.
"""


def render(sections, previous_triage, manual_blocks):
    out = [HEADER]
    out.append(f'\nLast scanned: {date.today().isoformat()}\n')

    open_total = 0
    urgent_total = 0
    triaged_total = 0
    summary_rows = []

    body = []
    closed = []

    for sec in sections:
        items = sec['items']
        if not items:
            closed.append(sec)
            continue

        rendered = []
        sec_open = 0
        sec_urgent = 0
        sec_count = 0
        for item in items:
            fid = f"{sec['key']}:{item.get('id', item['file'])}"
            mark, note = previous_triage.get(fid, (' ', ''))
            # `[!]` is confirmed AND urgent — still open work, and the thing most worth
            # surfacing in the summary. Only `[x]` and `[~]` retire a finding.
            if mark in (' ', '!'):
                sec_open += 1
                open_total += 1
                sec_count += item['count']
                if mark == '!':
                    sec_urgent += 1
                    urgent_total += 1
            else:
                triaged_total += 1
            suffix = f' — {note}' if note else ''
            label = item.get('label', f"`{item['file']}`")
            line = (f"- [{mark}] {label} — {item['detail']} "
                    f"<!-- id: {fid} -->{suffix}")
            rendered.append(line)

        summary_rows.append((sec['title'], sec_open, sec_urgent, len(items), sec_count))

        body.append(f"\n### {sec['title']}\n")
        body.append(f"_{sec['why']}_\n")
        headline = f"**{sec_open} open / {len(items)} findings**"
        if sec_urgent:
            headline += f" · **{sec_urgent} marked `[!]` urgent**"
        if sec_count:
            headline += f" · {sec_count} occurrences outstanding"
        body.append(headline + '\n')
        body.extend(rendered)

        detailed = [i for i in items if i['lines']]
        if detailed:
            body.append('\n<details><summary>Sample line numbers (regenerated each run — do not cite these elsewhere)</summary>\n')
            for item in detailed[:15]:
                body.append(f"- `{item['file']}` → lines {', '.join(str(n) for n in item['lines'])}")
            body.append('\n</details>')

    out.append('\n---\n\n## Summary\n')
    out.append('| Category | Open | `[!]` | Total | Occurrences |')
    out.append('|---|---:|---:|---:|---:|')
    for title, sec_open, sec_urgent, total, count in summary_rows:
        out.append(f'| {title} | {sec_open} | {sec_urgent or "—"} | {total} | {count or "—"} |')
    out.append(f'\n**{open_total} open findings ({urgent_total} marked `[!]` urgent), '
               f'{triaged_total} triaged and retired.**')

    out.append('\n---\n\n## Findings')
    out.extend(body)

    if closed:
        out.append('\n---\n\n## Closed categories\n')
        out.append('_Zero findings. The note records **why**, so these do not get re-opened by a future audit._\n')
        for sec in closed:
            note = sec.get('closed_note', 'No findings.')
            out.append(f"- **{sec['title']}** — {note}")

    if manual_blocks:
        out.append('\n---\n')
        for block in manual_blocks:
            out.append(MANUAL_START)
            out.append(block)
            out.append(MANUAL_END)

    out.append(FOOTER_NOTE)
    return '\n'.join(out).rstrip() + '\n'


# ---------------------------------------------------------------------- main

def main():
    sections = [check() for check in CHECKS]
    triage, manual = load_previous(TODOS_PATH)

    TODOS_PATH.parent.mkdir(parents=True, exist_ok=True)
    TODOS_PATH.write_text(render(sections, triage, manual), encoding='utf-8')

    payload = OrderedDict()
    payload['scanned'] = date.today().isoformat()
    payload['categories'] = [
        OrderedDict([
            ('key', s['key']),
            ('title', s['title']),
            ('findings', len(s['items'])),
            ('occurrences', sum(i['count'] for i in s['items'])),
            ('items', [{'id': i.get('id', i['file']), 'file': i['file'], 'count': i['count']}
                       for i in s['items']]),
        ])
        for s in sections
    ]
    JSON_PATH.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')

    total = sum(len(s['items']) for s in sections)
    print(f'QA scan complete — {total} findings across {len(sections)} categories.')
    print(f'  {TODOS_PATH.relative_to(ROOT)}')
    print(f'  {JSON_PATH.relative_to(ROOT)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
