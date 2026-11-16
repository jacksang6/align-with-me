# Artifact page standards validator: icons, dividers, dock, Title Case, motion.
"""validate_artifact.py - deterministic standards audit for a generated
artifact page (the pre-launch gate: the artifact server starts only after
this passes).

Interface:
    python validate_artifact.py --html <file> [--lang en|zh]
                                [--exempt <id,id,...>]
                                [--skip icons,dividers,dock,titles,motion,tokens,behaviour]
                                [--baseline <prev-snapshot>]
                                [--spec-data <decisions.json>
                                 --round-answers <answers.json>...
                                 --snapshots <dir>]
    python validate_artifact.py --url <deployed-url> [same options]

Checks:
    icons     every button and heading (h1-h6) carries an icon: the element
              itself, one of its children, or its immediately preceding
              sibling is an <svg>, a [data-icon] element or an icon class;
              emoji glyphs anywhere in the page text count as icon failures
              (zero allowed).
    dividers  hr and divider-class elements are zero, except inside a
              repeated entry list (parent ul/ol/dl or role=list - the case
              the divider provably serves) or an id listed in --exempt.
    dock      a dock element exists, is collapsed by default, and carries
              exactly four tabs (design preview, function spec, decision
              log, version ladder).
    titles    every heading and button renders Title Case (English copy
              only; --lang zh skips this check).
    motion    at least one transition or animation is declared, every
              duration stays inside 80-450 ms (micro to medium), and a
              prefers-reduced-motion rule is present. Static lower bound
              only: per-element coverage and easing quality are judged in
              the S5 sweep.
    tokens    identical element kinds carry identical tokens: one class
              declares exactly one background value, and interactive
              elements (button, btn* classes, role=button) take their
              colors from design tokens (var(--...)), never raw values.
    baseline  (with --baseline) append-only growth against the previous
              round's snapshot: the confirmed markup survives verbatim
              (substring or line-level subsequence) - only additions are
              legal; changed or removed confirmed lines are reported.
    behaviour a page carrying button controls declares behaviour (at
              least one script element); controls with no script are a
              drawn mockup and are refused - the static lower bound, the
              real proof is the deployed click-through (criteria pool 16).
    coverage  (with --spec-data/--round-answers/--snapshots) the
              round-close gate: every confirmed answer's qid exists as a
              decision seq in the spec data, and every answered round has
              its snapshot-r<N>.html ladder snapshot - aligned-but-
              unwritten decisions are refused (types spec / ladder).

Exit codes: 0 = all executed checks passed (stdout "[OK] artifact standards
passed (n checks)"); 2 = one or more checks failed or argument error (one
"[ERR] artifact standards failed" line, then a JSON object on stderr:
{"error": {"errors": [{"loc", "type", "msg", "fix"}, ...]}} listing every
failed element at once).

Stdlib only. Every path comes from the command line.
"""

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

EMOJI_RE = re.compile(
    '[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF'
    '\uFE00-\uFE0F\U0001F1E6-\U0001F1FF]')
DURATION_RE = re.compile(r'(\d*\.?\d+)\s*(ms|s)\b')
DECL_RE = re.compile(r'(?:transition|animation)\s*:', re.IGNORECASE)
MINOR_WORDS = {
    'a', 'an', 'the', 'and', 'but', 'or', 'nor', 'for', 'yet', 'so',
    'at', 'by', 'in', 'of', 'on', 'to', 'up', 'as', 'is', 'it', 'via',
    'with', 'from', 'into', 'onto', 'over', 'per', 'off',
}
VOID_TAGS = {
    'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link',
    'meta', 'param', 'source', 'track', 'wbr', 'path', 'circle', 'rect',
    'line', 'polyline', 'polygon', 'use', 'stop', 'ellipse',
}
LIST_PARENTS = {'ul', 'ol', 'dl'}
HEADING_TAGS = {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}


class Node:
    def __init__(self, tag, attrs, parent):
        self.tag = tag
        self.attrs = dict(attrs)
        self.parent = parent
        self.children = []
        self.text_parts = []

    def cls_tokens(self):
        return (self.attrs.get('class') or '').split()

    def text(self):
        parts = list(self.text_parts)
        for child in self.children:
            parts.append(child.text())
        return ''.join(parts)


class TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node('#root', [], None)
        self.stack = [self.root]

    def _node(self, tag, attrs):
        node = Node(tag, attrs, self.stack[-1])
        self.stack[-1].children.append(node)
        return node

    def handle_starttag(self, tag, attrs):
        node = self._node(tag, attrs)
        if tag not in VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self._node(tag, attrs)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1].text_parts.append(data)


def walk(node):
    for child in node.children:
        yield child
        yield from walk(child)


def prev_sibling(node):
    siblings = node.parent.children if node.parent else []
    index = siblings.index(node) if node in siblings else 0
    return siblings[index - 1] if index > 0 else None


def has_icon_marker(node):
    return (node.tag == 'svg' or 'data-icon' in node.attrs
            or any('icon' in token for token in node.cls_tokens()))


def _setup_streams():
    """Force UTF-8 on stdout/stderr (Windows consoles default to GBK)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError):
            pass


class _Parser(argparse.ArgumentParser):
    """Argparse failures follow the [ERR]+JSON contract like every other
    failure of this script, instead of bare usage text."""

    def error(self, message):
        _arg_error(message,
                   'run with --help to see the accepted flags')
        raise SystemExit(2)


def _emit_error(errors):
    sys.stderr.write('[ERR] artifact standards failed\n')
    sys.stderr.write(json.dumps({'error': {'errors': errors}},
                                ensure_ascii=False) + '\n')
    return 2


def _arg_error(msg, fix):
    return _emit_error([{'loc': 'argv', 'type': 'args', 'msg': msg,
                         'fix': fix}])


def _is_icon_carrier(node):
    return node is not None and has_icon_marker(node)


def _element_has_icon(node):
    """The icon rides the element itself, its first children, or the
    immediately preceding sibling."""
    if has_icon_marker(node):
        return True
    if any(has_icon_marker(child) for child in node.children):
        return True
    return _is_icon_carrier(prev_sibling(node))


def _check_icons(root, errors):
    targets = [n for n in walk(root) if n.tag == 'button'
               or (n.tag == 'input' and n.attrs.get('type')
                   in ('submit', 'button'))
               or n.tag in HEADING_TAGS]
    for node in targets:
        label = node.text().strip()[:40] or node.tag
        if _element_has_icon(node):
            continue
        errors.append({
            'loc': '%s "%s"' % (node.tag, label),
            'type': 'icon',
            'msg': 'interactive element carries no icon',
            'fix': 'add an svg icon from the declared icon set before the '
                   'element text (or as its first child)'})
    body_text = root.text()
    if EMOJI_RE.search(body_text):
        errors.append({
            'loc': 'page text', 'type': 'emoji',
            'msg': 'emoji glyph found in page text',
            'fix': 'replace emoji with an svg icon from the declared set '
                   '(emoji never serves as an icon)'})


def _check_dividers(root, exempt, errors):
    for node in walk(root):
        is_divider = (node.tag == 'hr'
                      or any(t in ('divider', 'separator')
                             for t in node.cls_tokens()))
        if not is_divider:
            continue
        node_id = node.attrs.get('id', '')
        parent = node.parent
        in_entry_list = (parent is not None
                         and (parent.tag in LIST_PARENTS
                              or parent.attrs.get('role') == 'list'))
        if in_entry_list or node_id in exempt:
            continue
        label = node_id or ' '.join(node.cls_tokens())[:40] or 'hr'
        errors.append({
            'loc': '%s "%s"' % (node.tag, label), 'type': 'divider',
            'msg': 'divider outside a repeated entry list',
            'fix': 'replace with whitespace, move it into the list '
                   'container it separates, or add its id to --exempt'})


def _find_dock(root):
    for node in walk(root):
        if (node.attrs.get('id') == 'dock' or 'dock' in node.cls_tokens()
                or 'data-dock' in node.attrs):
            return node
    return None


def _check_dock(root, errors):
    dock = _find_dock(root)
    if dock is None:
        errors.append({
            'loc': 'page', 'type': 'dock',
            'msg': 'no design-time dock found',
            'fix': 'add the corner dock element (id or class dock) with '
                   'the four design-time tabs'})
        return
    collapsed = ('collapsed' in dock.cls_tokens()
                 or 'hidden' in dock.cls_tokens()
                 or 'hidden' in dock.attrs
                 or dock.attrs.get('aria-expanded') == 'false'
                 or 'display:none' in (dock.attrs.get('style') or '').replace(
                     ' ', '')
                 or 'display: none' in (dock.attrs.get('style') or ''))
    if not collapsed:
        errors.append({
            'loc': 'dock', 'type': 'dock',
            'msg': 'dock is not collapsed by default',
            'fix': 'mark the dock collapsed (class collapsed, hidden, '
                   'aria-expanded=false, or display:none)'})
    tabs = [n for n in walk(dock)
            if 'tab' in n.cls_tokens() or 'data-tab' in n.attrs]
    if len(tabs) != 4:
        errors.append({
            'loc': 'dock', 'type': 'dock',
            'msg': 'dock carries %d tabs, expected 4 '
                   '(design preview, function spec, decision log, '
                   'version ladder)' % len(tabs),
            'fix': 'give the dock exactly the four design-time tabs'})


def _is_title_case(text):
    tokens = [t for t in re.split(r'\s+', text.strip()) if t]
    letters = [i for i, t in enumerate(tokens)
               if any(c.isascii() and c.isalpha() for c in t)]
    if not letters:
        return True
    first, last = letters[0], letters[-1]
    for i, token in enumerate(tokens):
        if not any(c.isascii() and c.isalpha() for c in token):
            continue
        bare = token.strip('\'"([{-')
        if bare[0].isupper():
            continue
        if i not in (first, last) and bare.lower() in MINOR_WORDS:
            continue
        return False
    return True


def _check_titles(root, errors):
    targets = [n for n in walk(root)
               if n.tag in HEADING_TAGS or n.tag == 'button'
               or (n.tag == 'input' and n.attrs.get('type')
                   in ('submit', 'button'))]
    for node in targets:
        text = node.text().strip()
        if not text:
            continue
        if not re.search(r'[A-Za-z]', text):
            continue
        if _is_title_case(text):
            continue
        errors.append({
            'loc': '%s "%s"' % (node.tag, text[:40]), 'type': 'title',
            'msg': 'copy is not Title Case',
            'fix': 'capitalize each principal word of the heading or '
                   'button (minor words mid-phrase stay lower)'})


MOTION_PROPS = ('transition', 'transition-duration',
                'animation', 'animation-duration')


def _check_motion(root, css_text, errors):
    """Durations are read from transition/animation declarations only:
    a comment like 'legacy 60ms' or a transition-delay never fails the
    check (comments are stripped, other properties are not durations)."""
    text = re.sub(r'/\*.*?\*/', '', css_text, flags=re.DOTALL)
    if not DECL_RE.search(text):
        errors.append({
            'loc': 'stylesheet', 'type': 'motion',
            'msg': 'no transition or animation declared',
            'fix': 'give the interactive elements a micro-to-medium '
                   'transition (a natural slide, fade or scale)'})
    for _selector, body in _css_rules(text):
        for declaration in body.split(';'):
            if ':' not in declaration:
                continue
            prop, value = declaration.split(':', 1)
            if prop.strip().lower() not in MOTION_PROPS:
                continue
            for match in DURATION_RE.finditer(value):
                duration = float(match.group(1))
                ms = duration if match.group(2) == 'ms' else duration * 1000
                if not 80 <= ms <= 450:
                    errors.append({
                        'loc': 'stylesheet', 'type': 'motion',
                        'msg': 'duration %gms outside the micro-to-medium '
                               'range (80-450 ms)' % ms,
                        'fix': 'keep every motion duration inside '
                               '80-450 ms'})
    if 'prefers-reduced-motion' not in text:
        errors.append({
            'loc': 'stylesheet', 'type': 'motion',
            'msg': 'no prefers-reduced-motion rule',
            'fix': 'add a @media (prefers-reduced-motion: reduce) rule '
                   'that disables every transition'})


def _css_rules(css_text):
    """Yield (selector, body) pairs from a stylesheet (naive, machine-
    written CSS; comments stripped first)."""
    text = re.sub(r'/\*.*?\*/', '', css_text, flags=re.DOTALL)
    for match in re.finditer(r'([^{}]+)\{([^{}]*)\}', text):
        selector = match.group(1).strip()
        body = match.group(2)
        if selector.startswith('@'):
            inner = re.finditer(r'([^{}]+)\{([^{}]*)\}', body)
            for sub in inner:
                yield sub.group(1).strip(), sub.group(2)
            continue
        yield selector, body


INTERACTIVE_VALUE_RE = re.compile(
    r'(button|\bbtn[\w-]*|\bbutton\b)', re.IGNORECASE)
RAW_COLOR_RE = re.compile(
    r'(#[0-9a-f]{3,8}\b|rgba?\([^)]*\)|hsla?\([^)]*\))', re.IGNORECASE)
COLOR_PROPS = ('background-color', 'background', 'color', 'border-color',
               'border')


def _check_tokens(root, css_text, errors):
    """Identical element kinds carry identical tokens: the same class
    declares one background value, and interactive elements take colors
    from tokens (var(--...)), never raw values."""
    backgrounds = {}
    for selector, body in _css_rules(css_text):
        classes = set(re.findall(r'\.([A-Za-z][\w-]*)', selector))
        interactive = (re.search(r'\bbutton\b', selector, re.IGNORECASE)
                       or any(c.lower() == 'btn' or c.lower().startswith(
                           'btn-') or c.lower() == 'button'
                           for c in classes)
                       or 'role=button' in selector)
        prop_values = {}
        for declaration in body.split(';'):
            if ':' not in declaration:
                continue
            prop, value = declaration.split(':', 1)
            prop_values[prop.strip().lower()] = value.strip()
        for prop in ('background-color', 'background'):
            if prop not in prop_values:
                continue
            value = prop_values[prop]
            for cls in sorted(classes):
                backgrounds.setdefault(cls, {})
                backgrounds[cls].setdefault(value, set()).add(selector)
        if not interactive:
            continue
        for prop in COLOR_PROPS:
            if prop not in prop_values:
                continue
            value = prop_values[prop]
            if value in ('inherit', 'transparent', 'currentcolor', 'none'):
                continue
            if value.startswith('var('):
                continue
            if RAW_COLOR_RE.search(value):
                errors.append({
                    'loc': 'css "%s"' % selector[:50], 'type': 'token',
                    'msg': 'interactive element sets %s to a raw value '
                           '(%s)' % (prop, value[:30]),
                    'fix': 'use a design token (var(--...)) so identical '
                           'element kinds share one value'})
    for cls, values in sorted(backgrounds.items()):
        if len(values) > 1:
            errors.append({
                'loc': 'css class "%s"' % cls, 'type': 'token',
                'msg': 'the same class declares %d different background '
                       'values (%s)' % (len(values),
                                        ', '.join(sorted(values))[:60]),
                'fix': 'identical element kinds carry identical tokens: '
                       'give the class one background token'})


def _collect_css(root):
    chunks = [n.text() for n in walk(root) if n.tag == 'style']
    for node in walk(root):
        style = node.attrs.get('style')
        if style:
            chunks.append(style)
    return '\n'.join(chunks)


def _check_baseline(source, baseline_path, errors):
    """Append-only growth against the previous round's snapshot: the
    confirmed markup must survive verbatim (substring, or line-level
    subsequence when the generator reformats) — only additions are legal."""
    try:
        with open(baseline_path, 'r', encoding='utf-8') as handle:
            base_text = handle.read()
    except OSError as exc:
        errors.append({
            'loc': '--baseline', 'type': 'baseline',
            'msg': 'cannot read the baseline snapshot: %s' % exc,
            'fix': "pass the previous round's snapshot file path"})
        return
    if base_text.strip() in source:
        return
    # Whitespace-collapsed character-level subsequence: tolerant of
    # reindentation and of minified single-line pages, strict about any
    # confirmed character vanishing or changing.
    base_c = ' '.join(base_text.split())
    src_c = ' '.join(source.split())
    cursor = 0
    diverged = None
    for i, ch in enumerate(base_c):
        while cursor < len(src_c) and src_c[cursor] != ch:
            cursor += 1
        if cursor == len(src_c):
            diverged = i
            break
        cursor += 1
    if diverged is None:
        return
    errors.append({
        'loc': '--baseline', 'type': 'baseline',
        'msg': 'append-only violation: confirmed markup changed or '
               'removed (diverges near: %r)'
               % base_c[max(0, diverged - 40):diverged + 40],
        'fix': 'confirmed regions are never regenerated: append the new '
               'element and restore the confirmed markup verbatim'})


def _check_coverage(spec_data_path, answers_paths, snapshots_dir, errors):
    """Deterministic round-close gate: every confirmed answer reached the
    function spec data, and every answered round has its ladder snapshot.
    Aligned-but-unwritten decisions are fake decisions — this refuses them."""
    decisions = {}
    if spec_data_path:
        try:
            with open(spec_data_path, 'r', encoding='utf-8-sig') as handle:
                data = json.load(handle)
        except (OSError, ValueError) as exc:
            errors.append({
                'loc': '--spec-data', 'type': 'spec',
                'msg': 'cannot read the spec data: %s' % exc,
                'fix': 'pass the function-spec decisions JSON'})
            data = {}
        entries = data.get('decisions', []) if isinstance(data, dict) else []
        base = Path(spec_data_path).parent
        for entry in entries:
            if isinstance(entry, dict) and entry.get('seq'):
                decisions[str(entry['seq'])] = entry
                probe = entry.get('probe')
                if probe and not (base / str(probe)).is_file():
                    errors.append({
                        'loc': 'decision %s' % entry['seq'], 'type': 'probe',
                        'msg': 'missing probe document: %s' % probe,
                        'fix': 'cite an existing support-probe document - '
                               'the evidence must be readable where the '
                               'spec points'})
    for path in answers_paths:
        try:
            with open(path, 'r', encoding='utf-8-sig') as handle:
                entries = json.load(handle)
        except (OSError, ValueError) as exc:
            errors.append({
                'loc': '--round-answers', 'type': 'answers',
                'msg': 'cannot read the answers file: %s' % exc,
                'fix': 'pass a console answers JSON path'})
            continue
        if not isinstance(entries, list):
            continue
        for entry in entries:
            qid = str(entry.get('qid', '')) if isinstance(entry, dict) else ''
            if qid and spec_data_path and qid not in decisions:
                errors.append({
                    'loc': 'answers %s' % Path(path).name, 'type': 'spec',
                    'msg': 'confirmed answer %r never reached the '
                           'function spec' % qid,
                    'fix': 'write every aligned answer into the function '
                           'spec decisions data (seq = answer qid)'})
        match = re.search(r'round(\d+)', Path(path).name)
        if snapshots_dir and match:
            snapshot = (Path(snapshots_dir)
                        / ('snapshot-r%s.html' % match.group(1)))
            if not snapshot.is_file():
                errors.append({
                    'loc': '--snapshots', 'type': 'ladder',
                    'msg': 'round %s has no version-ladder snapshot'
                           % match.group(1),
                    'fix': 'keep one snapshot-r<N>.html per answered '
                           'round in the snapshots folder'})


def _check_behaviour(root, errors):
    """A control without behaviour is a mockup: a page carrying buttons
    must declare behaviour (at least one script element) — the static
    lower bound; the real proof is the deployed click-through (pool 16)."""
    controls = [n for n in walk(root) if n.tag == 'button'
                or (n.tag == 'input' and n.attrs.get('type')
                    in ('submit', 'button'))]
    if not controls:
        return
    if any(n.tag == 'script' for n in walk(root)):
        return
    errors.append({
        'loc': 'page', 'type': 'behaviour',
        'msg': 'controls with no behaviour: %d button(s) and no script'
               % len(controls),
        'fix': 'wire every control to its real handler - a drawn-but-'
               'inert button is a mockup, and mockups are forbidden; '
               'drop or block the control until its behaviour exists'})


def _check_version(root, expected, errors):
    """Build version and prototype version are the same number: the dock
    trigger must carry exactly the expected version tag."""
    dock = _find_dock(root)
    if dock is None:
        errors.append({
            'loc': '--expect-version', 'type': 'version',
            'msg': 'no dock to carry the version tag',
            'fix': 'the dock trigger rides the newest version tag'})
        return
    if expected not in dock.text():
        errors.append({
            'loc': '--expect-version', 'type': 'version',
            'msg': 'the dock carries %r, expected %r - build version and '
                   'prototype version must be the same number'
                   % (dock.text().strip()[:30], expected),
            'fix': 'deploy the build of the tagged prototype version'})


def main(argv=None):
    _setup_streams()
    parser = _Parser(add_help=True)
    parser.add_argument('--html')
    parser.add_argument('--url')
    parser.add_argument('--lang', default='en')
    parser.add_argument('--exempt', default='')
    parser.add_argument('--skip', default='')
    parser.add_argument('--baseline', default='',
                        help="previous round's snapshot for the "
                             'append-only growth check')
    parser.add_argument('--spec-data', default='',
                        help='function-spec decisions JSON for the '
                             'round-close coverage gate')
    parser.add_argument('--round-answers', action='append', default=[],
                        help='console answers JSON of one round '
                             '(repeatable)')
    parser.add_argument('--snapshots', default='',
                        help='folder holding snapshot-r<N>.html ladder '
                             'snapshots')
    parser.add_argument('--expect-version', default='',
                        help='the version tag the dock trigger must carry '
                             '(build version == prototype version)')
    args = parser.parse_args(argv)
    skip = {s.strip() for s in args.skip.split(',') if s.strip()}
    if bool(args.html) == bool(args.url):
        return _arg_error('pass exactly one of --html or --url',
                          'audit a file with --html <file>, or a deployed '
                          'page with --url <deployed-url>')
    if args.html:
        try:
            with open(args.html, 'rb') as handle:
                raw = handle.read()
        except OSError as exc:
            return _arg_error('cannot read the html file: %s' % exc,
                              'pass an existing artifact html path')
        try:
            source = raw.decode('utf-8')
        except UnicodeDecodeError as exc:
            return _emit_error([{
                'loc': args.html, 'type': 'encoding',
                'msg': 'the artifact page is not valid UTF-8 (%s)' % exc,
                'fix': 're-save the page with UTF-8 encoding'}])
    else:
        try:
            request = Request(args.url, headers={'Accept': 'text/html'})
            with urlopen(request, timeout=10) as response:
                raw = response.read()
            source = raw.decode('utf-8', errors='replace')
        except OSError as exc:
            return _arg_error('cannot fetch the deployed page: %s' % exc,
                              'check the deployed url is reachable')

    builder = TreeBuilder()
    try:
        builder.feed(source)
    except Exception:  # a malformed page is still auditable text
        pass
    root = builder.root
    errors = []
    if 'icons' not in skip:
        _check_icons(root, errors)
    if 'dividers' not in skip:
        exempt = {e.strip() for e in args.exempt.split(',') if e.strip()}
        _check_dividers(root, exempt, errors)
    if 'dock' not in skip:
        _check_dock(root, errors)
    if 'titles' not in skip and not args.lang.lower().startswith('zh'):
        _check_titles(root, errors)
    if 'motion' not in skip or 'tokens' not in skip:
        css_text = _collect_css(root)
        if 'motion' not in skip:
            _check_motion(root, css_text, errors)
        if 'tokens' not in skip:
            _check_tokens(root, css_text, errors)

    total = 7 + (1 if args.baseline else 0) + (
        1 if (args.spec_data or args.round_answers or args.snapshots) else 0) \
        + (1 if args.expect_version else 0)
    if 'behaviour' not in skip:
        _check_behaviour(root, errors)
    if args.expect_version:
        _check_version(root, args.expect_version, errors)
    if args.baseline:
        _check_baseline(source, args.baseline, errors)
    if args.spec_data or args.round_answers or args.snapshots:
        _check_coverage(args.spec_data, args.round_answers, args.snapshots,
                        errors)

    skipped = set(skip)
    if args.lang.lower().startswith('zh'):
        skipped.add('titles')
    ran = total - len([s for s in ('icons', 'dividers', 'dock', 'titles',
                                   'motion', 'tokens', 'behaviour')
                       if s in skipped])
    if errors:
        return _emit_error(errors)
    sys.stdout.write('[OK] artifact standards passed (%d checks)\n' % ran)
    return 0


if __name__ == '__main__':
    sys.exit(main())
