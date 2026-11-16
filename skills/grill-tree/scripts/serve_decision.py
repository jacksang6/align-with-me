# Local decision console: serves a multi-card decision page, records batch answers, watches for completion.
"""serve_decision.py - local decision console + submit round-trip.

Single file, standard library only, three modes. The full behaviour
contract - page structure, keys, auto-advance, images, live views, the
evidence gate, the write-in option, the self-exit round-trip, the watcher
fallback - lives in scripts/manifest.json (the invocation contract). This
header keeps usage and the error shape only.

Mode A1 - batch server (--spec, one page = one round, several decision cards):
    python serve_decision.py --spec <spec.json> [--round <N>] [--port 8765]
        [--answers <file>] [--static-root <dir>]
    Spec shape: {"title", "round", "lang", "topic", "alignment",
    "questions": [{"qid", "title", "context", "evidence", "prob_label",
    "options": [{"label", "image", "url", "delta", "why", "example",
    "pros", "cons", "recommended", "probability"}]}]}; every option field
    except "label" is optional, 2-3 options per card. Serves one UTF-8
    stepper page; ONE Submit posts the whole batch.

Mode A2 - single-card server (simple legacy mode):
    python serve_decision.py --round <N> [--options "a,b,c"] [--links ...]
        [--title <str>] [--port 8765] [--answers <file>]

Mode B - watcher (fallback only when the server task cannot be watched):
    python serve_decision.py --watch <answers-file> --session <token>
        [--timeout <sec>]

On a valid POST /answer: the answers file is written atomically (utf-8),
the browser gets a confirmation page, then the server prints
"[OK] answers ready: <path>" plus the file content to stdout and exits 0.

Fatal errors print one "[ERR] <title>" line, then a JSON object, to
stderr. stdout/stderr are UTF-8; status markers are ASCII only
([OK] / [WARN] / [ERR]). Exit codes: 0 success; 2 argument, spec or
server error; 3 watcher timeout (only with --timeout).
"""

import argparse
import io
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ANSWERS_DIR = Path(tempfile.gettempdir()) / 'opencode'
MAX_PORT = 65535
REQUIRED_KEYS = ('qid', 'choice', 'note', 'ts')
POLL_INTERVAL = 0.5
IMAGE_TYPES = {
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.gif': 'image/gif',
    '.webp': 'image/webp',
    '.bmp': 'image/bmp',
    # Annotated evidence arrives as SVG from scripts/annotate_image.py. The
    # endpoint serves it into <img>/lightbox contexts, where SVG scripts never
    # execute; navigating to /img directly is the local user's own action.
    '.svg': 'image/svg+xml',
}


def _setup_streams():
    """Force UTF-8 on stdout/stderr (Windows consoles default to GBK)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError):
            pass


def _emit_error(error_type, title, detail, suggested_fix, errors=None):
    """Write an [ERR] marker line + JSON error object to stderr; exit code 2.

    errors (optional) is the pydantic-style list of every collected spec
    issue, so the orchestrating model repairs the whole spec in one pass.
    """
    error = {
        'type': error_type,
        'title': title,
        'detail': detail,
        'suggested_fix': suggested_fix,
    }
    if errors:
        error['errors'] = errors
    payload = {'ok': False, 'error': error}
    sys.stderr.write('[ERR] %s\n' % title)
    sys.stderr.write(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    return 2


def _esc(text):
    """Minimal HTML attribute/text escaping for page fragments."""
    return (str(text).replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;').replace('"', '&quot;'))


def _answers_path(round_no):
    return ANSWERS_DIR / ('answers-round%d.json' % round_no)


def _is_web_url(url):
    """A web URL goes to an external artifact server the console cannot
    inject into; relative urls are served from /static/ and can."""
    return '://' in str(url).lower()


def _parse_options(raw):
    if not raw:
        return []
    return [part.strip() for part in raw.split(',') if part.strip()]


def _parse_links(raw):
    if not raw:
        return []
    links = []
    for part in raw.split(','):
        part = part.strip()
        if not part:
            continue
        if '|' in part:
            name, url = part.split('|', 1)
            name, url = name.strip(), url.strip()
        else:
            name = url = part
        if url:
            links.append((name or url, url))
    return links


class _SpecError(ValueError):
    """Raised when the --spec JSON file fails structural validation.

    .issues carries every collected issue as a pydantic-style list of
    {loc, type, msg, fix} objects (empty for file-level failures that
    happen before field validation could run).
    """

    def __init__(self, message, issues=None):
        super().__init__(message)
        self.issues = issues or []


def _render_alignment(topic, rows, lang='en'):
    """Alignment table shown at the top of the console page: one row per
    question asked so far in this round, with its decision or Pending."""
    if not rows:
        return ''
    heading = ('<h3 class="aligntitle">%s %s</h3>'
               % (_esc(topic), _t(lang, 'design_tree'))
               if topic else '')
    body = []
    for row in rows:
        if row['decision']:
            cell = ('<span class="chip ok">%s%s</span> %s'
                    % (_icon('check', 'ic ic-xs'), _t(lang, 'align_decided'),
                       _esc(row['decision'])))
        else:
            cell = ('<span class="chip pend">%s%s</span>'
                    % (_icon('clock', 'ic ic-xs'), _t(lang, 'align_pending')))
        attr = (' data-qid="%s"' % _esc(row['qid'])) if row.get('qid') else ''
        body.append('<tr%s><td>%s</td><td>%s</td><td class="alcell">%s</td></tr>'
                    % (attr, _esc(row['seq']), _esc(row['question']), cell))
    return ('<section class="alignwrap" id="alignwrap">'
            '<div class="alignstrip">%s'
            '<span class="alignhint">%s</span></div>'
            '<div class="alignfold"><div class="align">'
            '<table id="aligntable"><thead><tr>'
            '<th>%s</th><th>%s</th><th>%s</th></tr></thead>'
            '<tbody>%s</tbody></table></div></div></section>'
            % (heading, _t(lang, 'align_hint'), _t(lang, 'align_seq'),
               _t(lang, 'align_question'), _t(lang, 'align_decision'),
               ''.join(body)))


def _load_spec(path_str, static_root=None):
    """Read and structurally validate a --spec JSON file.

    static_root is the folder the --static-root flag serves at /static/.
    Relative option "url" values validate against it: the console adds
    the /static/ prefix itself (a leading prefix doubles and 403s), and
    the target file must exist under the root. Callers that never serve
    /static/ still pass a folder so the existence check has a root.

    Validation is pydantic-style: every issue is collected with a JSON
    loc path, a machine kind, a message and a fix, and ALL of them are
    reported at once as an "errors" array on the [ERR] payload - the
    orchestrating model gets the whole repair list in one round-trip.
    """
    spec_path = Path(path_str).resolve()
    spec_dir = spec_path.parent
    issues = []

    def bad(loc, kind, msg, fix):
        issues.append({'loc': loc, 'type': kind, 'msg': msg, 'fix': fix})

    def fatal(message):
        raise _SpecError(message, issues)

    try:
        raw = spec_path.read_text(encoding='utf-8-sig')
    except OSError as exc:
        fatal('cannot read spec file: %s' % exc)
    except UnicodeDecodeError as exc:
        fatal('spec file is not valid UTF-8: %s' % exc)
    try:
        data = json.loads(raw)
    except ValueError as exc:
        fatal('spec file is not valid JSON: %s' % exc)
    if not isinstance(data, dict):
        fatal('spec root must be a JSON object')
    title = data.get('title', '')
    if not isinstance(title, str):
        bad(['title'], 'type', 'spec "title" must be a string',
            'set "title" to a string')
        title = ''
    round_no = data.get('round')
    if round_no is not None and (isinstance(round_no, bool)
                                 or not isinstance(round_no, int)
                                 or round_no < 1):
        bad(['round'], 'type', 'spec "round" must be a positive integer',
            'set "round" to a positive integer, or omit it')
        round_no = None
    questions = data.get('questions')
    if not isinstance(questions, list) or not questions:
        bad(['questions'], 'missing',
            'spec "questions" must be a non-empty array',
            'add a non-empty "questions" array of question objects')
        fatal('%d spec issue(s)' % len(issues))
    seen = set()
    normalized = []
    for qidx, question in enumerate(questions):
        qloc = ['questions', qidx]
        if not isinstance(question, dict):
            bad(qloc, 'type', 'question #%d is not a JSON object' % qidx,
                'make questions[%d] an object' % qidx)
            continue
        qid = question.get('qid')
        if not isinstance(qid, str) or not qid.strip():
            bad(qloc + ['qid'], 'missing',
                'question #%d needs a non-empty string "qid"' % qidx,
                'set questions[%d].qid to a unique string' % qidx)
            continue
        if qid in seen:
            bad(qloc + ['qid'], 'duplicate',
                'duplicate qid %r in spec questions' % qid,
                'give every question a unique qid')
            continue
        seen.add(qid)
        qtitle = question.get('title')
        if not isinstance(qtitle, str) or not qtitle.strip():
            bad(qloc + ['title'], 'missing',
                'question %r needs a non-empty string "title"' % qid,
                'set "title" to the card heading')
            qtitle = ''
        context = question.get('context', '')
        if isinstance(context, list):
            # Authors naturally write one-bullet-per-line context as a JSON
            # array; join it instead of rejecting the spec.
            if not all(isinstance(item, str) for item in context):
                bad(qloc + ['context'], 'type',
                    'question %r "context" must be a string or an array of '
                    'strings' % qid,
                    'make every "context" item a string')
                context = ''
            else:
                context = '\n'.join(context)
        elif not isinstance(context, str):
            bad(qloc + ['context'], 'type',
                'question %r "context" must be a string or an array of '
                'strings' % qid,
                'set "context" to a string or an array of strings')
            context = ''
        options = question.get('options')
        if not isinstance(options, list) or len(options) < 2:
            bad(qloc + ['options'], 'missing',
                'question %r needs at least 2 options (expected 2-3 per '
                'card)' % qid,
                'add 2-3 option objects to "options"')
            continue
        # Evidence mode decides the gate: rendered (default, capture + live
        # url both required, boxes on any screenshot), wireframe (S1
        # skeleton variants, image or url, boxes optional - the wireframe
        # self-annotates), degraded (declared, badged).
        evidence = question.get('evidence', 'rendered')
        if not isinstance(evidence, str) or evidence not in ('rendered',
                                                             'wireframe',
                                                             'degraded'):
            bad(qloc + ['evidence'], 'type',
                'question %r field "evidence" must be "rendered", '
                '"wireframe" or "degraded"' % qid,
                'set "evidence" to "rendered", "wireframe" or "degraded"')
            evidence = 'rendered'
        norm_opts = []
        for oidx, option in enumerate(options):
            oloc = qloc + ['options', oidx]
            if not isinstance(option, dict):
                bad(oloc, 'type',
                    'question %r option #%d is not a JSON object'
                    % (qid, oidx),
                    'make options[%d] an object' % oidx)
                continue
            label = option.get('label')
            if not isinstance(label, str) or not label.strip():
                bad(oloc + ['label'], 'missing',
                    'question %r option #%d needs a non-empty string '
                    '"label"' % (qid, oidx),
                    'set "label" to the option text shown on the card')
                continue
            entry = {'label': label}
            for key in ('image', 'url', 'delta', 'why', 'example'):
                value = option.get(key, '')
                if isinstance(value, list) and key != 'image' and key != 'url':
                    # Multi-line fields accept one-line-per-array-item and
                    # join with newlines (same leniency as "context").
                    if not all(isinstance(item, str) for item in value):
                        bad(oloc + [key], 'type',
                            'question %r option #%d field "%s" must be a '
                            'string or an array of strings' % (qid, oidx, key),
                            'make every "%s" item a string' % key)
                        value = ''
                    else:
                        value = '\n'.join(value)
                elif not isinstance(value, str):
                    bad(oloc + [key], 'type',
                        'question %r option #%d field "%s" must be a string '
                        'or an array of strings' % (qid, oidx, key),
                        'set "%s" to a string' % key)
                    value = ''
                entry[key] = value
            # Capture annotations: the page draws the circles and red labels
            # itself, so the region the user is deciding on is marked even
            # when the author shipped a raw screenshot.
            boxes = option.get('boxes', [])
            if not isinstance(boxes, list):
                bad(oloc + ['boxes'], 'type',
                    'question %r option #%d field "boxes" must be an array'
                    % (qid, oidx),
                    'set "boxes" to an array of {x,y,w,h,label} objects')
                boxes = []
            norm_boxes = []
            for bidx, box in enumerate(boxes):
                bloc = oloc + ['boxes', bidx]
                if not isinstance(box, dict):
                    bad(bloc, 'type',
                        'question %r option #%d box #%d is not a JSON '
                        'object' % (qid, oidx, bidx),
                        'make boxes[%d] an object with x,y,w,h' % bidx)
                    continue
                bkind = box.get('kind', 'box')
                if bkind not in ('box', 'move', 'icon', 'color'):
                    bad(bloc + ['kind'], 'value',
                        'question %r option #%d box #%d has an unknown '
                        'annotation kind %r' % (qid, oidx, bidx, bkind),
                        'set "kind" to box, move, icon or color')
                    continue
                blabel = box.get('label', '')
                if not isinstance(blabel, str):
                    bad(bloc + ['label'], 'type',
                        'question %r option #%d box #%d field "label" must '
                        'be a string' % (qid, oidx, bidx),
                        'set box "label" to a string or omit it')
                    blabel = ''

                def _pixel(obj, keys, why):
                    """Collect integer image pixels; report, never raise."""
                    out = {}
                    for k in keys:
                        v = obj.get(k) if isinstance(obj, dict) else None
                        if isinstance(v, bool) or not isinstance(v, int):
                            bad(bloc + [k], 'type',
                                'question %r option #%d box #%d (%s) field '
                                '"%s" must be an integer (image pixels)'
                                % (qid, oidx, bidx, why, k),
                                'set "%s" to an integer in image pixels' % k)
                            out[k] = 0
                        else:
                            out[k] = v
                    return out

                if bkind == 'move':
                    # A positional suggestion needs both ends: the current
                    # spot and the target spot, in capture pixels.
                    ends = {}
                    for k in ('from', 'to'):
                        pt = box.get(k)
                        if not isinstance(pt, dict):
                            bad(bloc + [k], 'type',
                                'question %r option #%d box #%d (move) field '
                                '"%s" must be an object with x,y'
                                % (qid, oidx, bidx, k),
                                'set "%s" to {"x": <int>, "y": <int>} in '
                                'image pixels' % k)
                            pt = {'x': 0, 'y': 0}
                        ends[k] = _pixel(pt, ('x', 'y'), 'move')
                    norm_boxes.append({'kind': 'move',
                                       'from': ends['from'], 'to': ends['to'],
                                       'label': blabel})
                    continue
                if bkind == 'icon':
                    coords = _pixel(box, ('x', 'y', 'w', 'h'), 'icon')
                    if coords['w'] <= 0 or coords['h'] <= 0 or coords['x'] < 0 \
                            or coords['y'] < 0:
                        bad(bloc, 'range',
                            'question %r option #%d box #%d (icon) needs '
                            'w,h > 0 and x,y >= 0' % (qid, oidx, bidx),
                            'give the icon a positive size inside the capture')
                        continue
                    icon = box.get('icon')
                    if not isinstance(icon, str) or not icon.strip():
                        bad(bloc + ['icon'], 'missing',
                            'question %r option #%d box #%d (icon) needs an '
                            '"icon" SVG fragment so the suggested icon '
                            'renders as a real element'
                            % (qid, oidx, bidx),
                            'set "icon" to inline SVG markup such as '
                            '\'<path d="M12 20h9"/>\'')
                        icon = ''
                    norm_boxes.append({'kind': 'icon', 'x': coords['x'],
                                       'y': coords['y'], 'w': coords['w'],
                                       'h': coords['h'], 'icon': icon,
                                       'label': blabel})
                    continue
                if bkind == 'color':
                    coords = _pixel(box, ('x', 'y'), 'color')
                    if coords['x'] < 0 or coords['y'] < 0:
                        bad(bloc, 'range',
                            'question %r option #%d box #%d (color) needs '
                            'x,y >= 0' % (qid, oidx, bidx),
                            'anchor the swatches inside the capture')
                        continue
                    cols = {}
                    for k in ('current', 'suggested'):
                        v = box.get(k)
                        if not isinstance(v, str) or not v.strip():
                            bad(bloc + [k], 'missing',
                                'question %r option #%d box #%d (color) '
                                'field "%s" must be a color value so the '
                                'swatches render'
                                % (qid, oidx, bidx, k),
                                'set "%s" to the color code used for '
                                'implementation' % k)
                            v = ''
                        cols[k] = v
                    norm_boxes.append({'kind': 'color', 'x': coords['x'],
                                       'y': coords['y'],
                                       'current': cols['current'],
                                       'suggested': cols['suggested'],
                                       'label': blabel})
                    continue
                coords = {}
                for k in ('x', 'y', 'w', 'h'):
                    v = box.get(k)
                    if isinstance(v, bool) or not isinstance(v, int):
                        bad(bloc + [k], 'type',
                            'question %r option #%d box #%d field "%s" '
                            'must be an integer (image pixels)'
                            % (qid, oidx, bidx, k),
                            'set "%s" to an integer in image pixels' % k)
                        coords[k] = 0
                    else:
                        coords[k] = v
                if coords['w'] <= 0 or coords['h'] <= 0 or coords['x'] < 0 \
                        or coords['y'] < 0:
                    bad(bloc, 'range',
                        'question %r option #%d box #%d needs w,h > 0 and '
                        'x,y >= 0' % (qid, oidx, bidx),
                        'give the box a positive size inside the capture')
                    continue
                norm_boxes.append({'kind': 'box', 'x': coords['x'],
                                   'y': coords['y'], 'w': coords['w'],
                                   'h': coords['h'], 'label': blabel})
            if evidence == 'rendered' and entry['image'] and not norm_boxes:
                bad(oloc + ['boxes'], 'missing',
                    'question %r option #%d carries a screenshot without '
                    '"boxes": state the region to circle (x,y,w,h in image '
                    'pixels, optional label) so the page can mark what the '
                    'user decides' % (qid, oidx),
                    'add a "boxes" array with at least one {x,y,w,h} region')
            entry['boxes'] = norm_boxes
            if entry['image']:
                raw_img = str(entry['image'])
                if '://' in raw_img.lower():
                    bad(oloc + ['image'], 'web_route',
                        'question %r option #%d image takes a file location '
                        'on disk, not a web URL: %s (an http link belongs in '
                        'the option "url" field, which renders the '
                        'open-in-tab link)' % (qid, oidx, raw_img),
                        'move the http link to "url" and put a file path in '
                        '"image"')
                else:
                    img_path = Path(entry['image'])
                    if not img_path.is_absolute():
                        # Relative image paths resolve against the spec
                        # file's folder, never the working directory.
                        img_path = (spec_dir / img_path).resolve()
                        entry['image'] = str(img_path)
                    if not img_path.is_file():
                        hint = ('; a web route such as /static/... belongs '
                                'in the option "url" field, not image'
                                if raw_img.startswith('/') else '')
                        bad(oloc + ['image'], 'not_found',
                            'question %r option #%d image not found: %s '
                            '(image is a file location, absolute or '
                            'relative to the spec file%s)'
                            % (qid, oidx, entry['image'], hint),
                            'point "image" at an existing capture file')
            url_raw = str(entry.get('url') or '')
            if url_raw and not _is_web_url(url_raw):
                # Relative urls are served under /static/ from
                # --static-root: the console adds the prefix itself, so a
                # leading /static/ doubles (/static//static/...) and the
                # page 403s; a url outside the root or pointing at a
                # missing file 404s. All three fail at load time with a
                # corrective fix, never as a broken live link.
                if url_raw.startswith('/static/'):
                    bad(oloc + ['url'], 'value',
                        'question %r option #%d "url" carries the /static/ '
                        'prefix: %s (the console adds /static/ itself - '
                        'the link would double to /static//static/ and '
                        'the page 403s)' % (qid, oidx, url_raw),
                        'write the bare relative path under '
                        '--static-root, e.g. "variant-a.html" instead of '
                        '"/static/variant-a.html"')
                elif static_root is None:
                    bad(oloc + ['url'], 'missing',
                        'question %r option #%d carries a relative "url" '
                        '(%s) but no --static-root was given: the live '
                        'link would 404' % (qid, oidx, url_raw),
                        'launch with --static-root <dir> and keep the '
                        'page under it')
                else:
                    page_rel = url_raw.split('?', 1)[0].split('#', 1)[0]
                    page_path = (Path(static_root) / page_rel).resolve()
                    if Path(static_root).resolve() \
                            not in page_path.parents \
                            or not page_path.is_file():
                        bad(oloc + ['url'], 'not_found',
                            'question %r option #%d url not found under '
                            '--static-root: %s' % (qid, oidx, page_path),
                            'point "url" at a file that exists under '
                            '--static-root')
            for key in ('pros', 'cons'):
                value = option.get(key, [])
                if isinstance(value, str):
                    value = [value]
                if not isinstance(value, list) or not all(
                        isinstance(item, str) for item in value):
                    bad(oloc + [key], 'type',
                        'question %r option #%d field "%s" must be a string '
                        'or an array of strings' % (qid, oidx, key),
                        'set "%s" to a string or a string array' % key)
                    value = []
                entry[key] = value
            entry['recommended'] = bool(option.get('recommended', False))
            prob = option.get('probability')
            if prob is not None:
                if isinstance(prob, bool) or not isinstance(prob, (int, float)):
                    bad(oloc + ['probability'], 'type',
                        'question %r option #%d field "probability" must be '
                        'a number' % (qid, oidx),
                        'set "probability" to a number (percent, e.g. 80)')
                    prob = None
                else:
                    if 0 < prob <= 1:
                        # A fraction (0.8 = 80%): authors slip into fraction
                        # notation, the console renders percent.
                        prob = prob * 100
                    if not 0 <= prob <= 100:
                        bad(oloc + ['probability'], 'range',
                            'question %r option #%d field "probability" '
                            'must be within 0-100 (percent, e.g. 80 - or a '
                            'fraction like 0.8, which reads as 80)'
                            % (qid, oidx),
                            'set "probability" within 0-100')
                        prob = None
            entry['probability'] = prob
            norm_opts.append(entry)
        # Evidence guard: options of one card must not share one image. A
        # shared image cannot tell the options apart, so it is not evidence.
        imgs = [o['image'] or o['url'] for o in norm_opts
                if o['image'] or o['url']]
        if len(imgs) != len(set(imgs)):
            bad(qloc + ['options'], 'duplicate',
                'question %r: two options use the same image; each option '
                'needs its own rendered result (build variants with '
                '/prototype first)' % qid,
                'give every option its own capture and variant page')
        # Evidence gate: a card either carries a rendered artifact per
        # option (image or url) or declares itself degraded. Silent
        # evidence loss is a load-time error, never a rendering-time
        # surprise.
        if evidence in ('rendered', 'wireframe'):
            bare = [o['label'] for o in norm_opts
                    if not (o['image'] or o['url'])]
            if bare:
                mode = ('rendered-evidence mode' if evidence == 'rendered'
                        else 'wireframe-evidence mode')
                hint = ('annotate a screenshot of the post-change state '
                        '(scripts/annotate_image.py)'
                        if evidence == 'rendered'
                        else 'build switchable skeleton variants first '
                             '(/prototype UI branch)')
                bad(qloc + ['options'], 'missing',
                    'question %r is in %s: option(s) %s carry neither '
                    '"image" nor "url"; %s or declare "evidence": '
                    '"degraded" for a labelled structural comparison'
                    % (qid, mode, '; '.join(repr(b) for b in bare), hint),
                    'add an "image" and a "url" per option, or declare '
                    '"evidence": "degraded"')
        if evidence == 'rendered':
            # Rendered evidence needs BOTH halves: the boxed capture is the
            # evidence, the url is the live view (the annotate entry). A
            # capture without a live view hides the annotate entry; a url
            # without a capture has no evidence. Either gap fails startup,
            # never surfaces as a broken page.
            no_url = [o['label'] for o in norm_opts if not o['url']]
            no_cap = [o['label'] for o in norm_opts if not o['image']]
            if no_url:
                bad(qloc + ['options'], 'missing',
                    'question %r is in rendered-evidence mode: option(s) %s '
                    'carry a capture but no "url": the live view must stay '
                    'one click away (serve the variant page under '
                    '--static-root and put its path in "url")'
                    % (qid, '; '.join(repr(b) for b in no_url)),
                    'add a "url" per option (the variant page path)')
            if no_cap:
                bad(qloc + ['options'], 'missing',
                    'question %r is in rendered-evidence mode: option(s) %s '
                    'carry a url but no "image" capture: every rendered '
                    'option needs its own boxed capture next to the live '
                    'link' % (qid, '; '.join(repr(b) for b in no_cap)),
                    'add an "image" capture with "boxes" per option')
        prob_label = question.get('prob_label', '')
        if not isinstance(prob_label, str):
            bad(qloc + ['prob_label'], 'type',
                'question %r field "prob_label" must be a string' % qid,
                'set "prob_label" to a string or omit it')
            prob_label = ''
        normalized.append({'qid': qid, 'title': qtitle, 'context': context,
                           'options': norm_opts, 'prob_label': prob_label,
                           'evidence': evidence})
    alignment = []
    card_qids = {q['qid'] for q in normalized}
    rows = data.get('alignment', [])
    if not isinstance(rows, list):
        bad(['alignment'], 'type', 'spec "alignment" must be an array',
            'set "alignment" to an array of row objects')
        rows = []
    for ridx, row in enumerate(rows):
        rloc = ['alignment', ridx]
        if not isinstance(row, dict) or not isinstance(row.get('question'),
                                                       str):
            bad(rloc, 'type',
                'alignment row #%d needs a "question" string' % ridx,
                'make every row an object with a "question" string')
            continue
        decision = row.get('decision')
        if decision is not None and not isinstance(decision, str):
            bad(rloc + ['decision'], 'type',
                'alignment row #%d "decision" must be a string or null'
                % ridx,
                'set "decision" to the chosen option text or null')
            decision = None
        qid = row.get('qid')
        if qid is not None:
            if not isinstance(qid, str) or qid not in card_qids:
                bad(rloc + ['qid'], 'unknown',
                    'alignment row #%d "qid" must name a question on this '
                    'page' % ridx,
                    'set "qid" to one of the page qids, or omit it')
                qid = None
            elif decision is not None:
                bad(rloc + ['decision'], 'conflict',
                    'alignment row #%d is linked to a card, so its '
                    '"decision" must be null: the page fills it in' % ridx,
                    'set "decision" to null for linked rows')
                decision = None
        alignment.append({'seq': str(row.get('seq', 'Q%d' % (ridx + 1))),
                          'question': row['question'], 'decision': decision,
                          'qid': qid})
    topic = data.get('topic', '')
    if not isinstance(topic, str):
        bad(['topic'], 'type', 'spec "topic" must be a string',
            'set "topic" to a string or omit it')
        topic = ''
    lang = data.get('lang', 'en')
    if not isinstance(lang, str) or not lang.strip():
        bad(['lang'], 'type', 'spec "lang" must be a non-empty string',
            'set "lang" to a language code like en or zh')
        lang = 'en'
    if issues:
        fatal('%d spec issue(s)' % len(issues))
    return {'title': title, 'round': round_no, 'questions': normalized,
            'lang': lang, 'alignment': alignment, 'topic': topic}


# Inline SVG icon set (Lucide-style line icons, one consistent stroke
# style: 2px, round caps). Every icon on the console page comes from this
# set -- emoji are never used as UI icons; they would clash with the
# design system (the chat-side round template still uses its own glyphs).
_ICONS = {
    'help': ('<circle cx="12" cy="12" r="10"/>'
             '<path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/>'
             '<path d="M12 17h.01"/>'),
    'doc': ('<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/>'
            '<path d="M14 2v4a2 2 0 0 0 2 2h4"/>'
            '<path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/>'),
    'list': ('<path d="m3 17 2 2 4-4"/><path d="m3 7 2 2 4-4"/>'
             '<path d="M13 6h8"/><path d="M13 12h8"/><path d="M13 18h8"/>'),
    'spark': ('<path d="M12 3l1.9 5.1a2 2 0 0 0 1.2 1.2L20 11l-4.9 1.7'
              'a2 2 0 0 0-1.2 1.2L12 19l-1.9-5.1a2 2 0 0 0-1.2-1.2L4 11'
              'l4.9-1.7a2 2 0 0 0 1.2-1.2z"/>'
              '<path d="M19 17v4"/><path d="M21 19h-4"/>'),
    'pencil': ('<path d="M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174'
               'a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32'
               'a2 2 0 0 0 .83-.497z"/><path d="m15 5 4 4"/>'),
    'arrow': '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
    'check': '<path d="M20 6 9 17l-5-5"/>',
    'circle_check': ('<circle cx="12" cy="12" r="10"/>'
                     '<path d="m9 12 2 2 4-4"/>'),
    'clock': ('<circle cx="12" cy="12" r="10"/>'
              '<polyline points="12 6 12 12 16 14"/>'),
    'clip': ('<rect width="8" height="4" x="8" y="2" rx="1"/>'
             '<path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6'
             'a2 2 0 0 1 2-2h2"/><path d="m9 14 2 2 4-4"/>'),
    'box': '<rect x="4" y="5" width="16" height="14" rx="2"/>',
    'eraser': ('<path d="m7 21-4.3-4.3c-1-1-1-2.5 0-3.4l9.6-9.6c1-1 2.5-1 3.4 0'
               'l5.6 5.6c1 1 1 2.5 0 3.4L13 21"/>'
               '<path d="M22 21H7"/><path d="m5 11 9 9"/>'),
    'undo': ('<path d="M3 7v6h6"/>'
             '<path d="M21 17a9 9 0 0 0-9-9 9 9 0 0 0-6 2.3L3 13"/>'),
    'redo': ('<path d="M21 7v6h-6"/>'
             '<path d="M3 17a9 9 0 0 1 9-9 9 9 0 0 1 6 2.3l3 2.7"/>'),
}


def _icon(name, cls='ic'):
    """One inline SVG from the icon set; cls sets the size variant."""
    return ('<svg class="%s" viewBox="0 0 24 24" aria-hidden="true">%s</svg>'
            % (cls, _ICONS[name]))


# Console chrome copy, keyed by page language. Every fixed string the page
# shows (hints, labels, chips, aria text, page shells) comes from this
# table, selected by the spec "lang" field; spec data (labels, titles,
# context) is never touched. zh entries are written as \uXXXX escapes so
# the skill file itself stays ASCII-only while the page renders real
# Chinese (skill language rule).
_CHROME = {
    'en': {
        'subtitle': 'One card at a time: pick an option and the next card '
                    'appears; the Submit button shows up after the last card.',
        'kpi_cards': 'Cards',
        'kpi_decided': 'Decided',
        'kpi_pending': 'Pending',
        'review_head': 'Review &amp; submit',
        'submit': 'Submit',
        'submit_hint': 'One Submit for the whole round; submitting writes '
                       "this round's answers to the local answers file, "
                       'then this page closes.',
        'keys_switch': 'switch card',
        'keys_browse': 'browse options',
        'keys_pick': 'pick option',
        'keys_confirm': 'confirm focused',
        'keys_submit': 'submit round',
        'keys_back': 'back to cards',
        'align_hint': 'hover to expand',
        'align_seq': 'Seq',
        'align_question': 'Question',
        'align_decision': 'Decision',
        'align_decided': 'Decided',
        'align_pending': 'Pending',
        'design_tree': 'Design Tree',
        'kicker': 'Decision needed',
        'explanation': 'Explanation',
        'options_head': 'Options',
        'options_sorted': ' (sorted by probability)',
        'recommended': 'RECOMMENDED',
        'prob_title': 'Prior probability of this option being adopted',
        'delta_lead': 'Delta:',
        'reason_lead': 'Reason:',
        'example_lead': 'Example:',
        'pros_lead': 'Pros:',
        'cons_lead': 'Cons:',
        'open_tab': 'View and annotate in the interactive interface',
        'next_card': 'Next card',
        'review_answers': 'Review answers',
        'own_label': 'None of these - write my own answer',
        'own_placeholder': 'Your own answer (required when this option is '
                           'picked)',
        'paste_aria': 'Paste or drop a screenshot (optional)',
        'paste_hint': 'Paste or drop a screenshot (optional - it travels '
                      'with this answer)',
        'own_missing': '(own answer not written)',
        'not_decided': '(not decided)',
        'own_answer': 'Own answer',
        'edit': 'Edit',
        'decide_first': 'Decide this card first: pick an option.',
        'fmt_count_card': 'Card %d / %d \u00b7 %d decided',
        'fmt_count_review': 'Review \u00b7 %d / %d decided',
        'fmt_live_card': 'Card %d of %d',
        'fmt_live_review': 'Review: %d of %d answers decided',
        'fmt_attached': '%d attached image(s)',
        'fmt_write_missing': 'Write your own answer for: %s (the box inside '
                             'the last option - the note field is not the '
                             'answer)',
        'fmt_answer_missing': 'Answer every card before submitting. '
                              'Missing: %s',
        'paste_image_err': 'Paste an image (png / jpg / gif / webp)',
        'fmt_img_too_large': 'Image too large (max 8 MB): %s',
        'img_limit': 'Up to 4 images per card',
        'lightbox_aria': 'Enlarged diagram; click or press Escape to close',
        'fmt_remove_img': 'Remove %s',
        'prev_card_aria': 'Previous card',
        'next_card_aria': 'Next card or review',
        'option_image_alt': 'Option image',
        'click_enlarge': 'Click to enlarge',
        'evbadge': 'Structural comparison - not rendered evidence; '
                   'backfill rules apply',
        'confirm_title': 'Submitted successfully',
        'fmt_confirm_saved': 'Saved to %s',
        'confirm_closing': 'Closing automatically ...',
        'fmt_confirm_countdown': 'Closing automatically in %d second(s) ...',
        'confirm_fallback': 'Round complete - the orchestrator picked up '
                            'your answers. You can close this tab.',
        'error_title': 'Submission error',
        'rejected_guidance': 'Nothing was written. Press the browser Back '
                             'button to fix the answers.',
        'images_guidance': 'Nothing was written. Press the browser Back '
                           'button to fix the images.',
        'retry_guidance': 'Nothing was written. Press the browser Back '
                          'button to retry.',
        'internal_guidance': 'Nothing was written. Check the server console '
                             'output.',
        'subtitle_single': 'Pick one option, add a note, then submit; the '
                           'page confirms and closes by itself.',
        'note_head': 'Note',
        'note_placeholder': 'Reasons, constraints, concerns (optional)',
        'select_first': 'Select an option first',
        'attachments': 'Attachments',
        'links_hint': 'If the browser blocks file:// links, copy the path '
                      'and open it in File Explorer.',
        'no_options': '(no --options provided)',
        'fmt_ann_count': '%d annotations',
        'ann_toggle': 'Annotate',
        'ann_undo': 'Undo',
        'ann_redo': 'Redo',
        'ann_stop': 'Annotating - click to stop',
        'ann_save': 'Save and replace',
        'ann_save_title': 'Capture this annotated page, replace the '
                          "option's evidence, ride the answer",
        'ann_return': 'Back to console',
        'ann_return_title': 'Close this tab without saving; back to the '
                            'console',
        'fmt_ai_count': '%d AI marks',
        'ai_clear': 'Clear AI marks',
        'ai_restore': 'Restore AI',
        'ai_remove': 'Remove AI mark',
        'tool_box': 'Box',
        'tool_arrow': 'Arrow',
        'tool_eraser': 'Eraser',
        'proto_gen': 'Generate prototype',
        'proto_gen_title': 'Cannot say the change in words? Save the marks '
                           'and ask for a generated prototype of this '
                           'option',
        'proto_requested': 'prototype requested',
        'proto_badge': 'Prototype requested - click to move to the next '
                       'question',
        'ann_capture_fail': 'Page capture failed: notes sent without the '
                            'image',
        'fmt_ann_save_fail': 'Saving the server record failed: %s',
        'saved_badge': 'Your annotation is saved',
        'badge_next_card': 'Click for the next card',
        'badge_review': 'Click to review and submit',
        'ann_unlinked': 'No console option is linked to this page',
        'fmt_ann_cap': '%d: what is this about?',
        'fmt_ann_remove': 'Remove annotation %d',
        'ann_open_first': 'Open this page from a console option first.',
        'ann_draw_first': 'Draw at least one annotation first.',
    },
    'zh': {
        'subtitle': '\u4e00\u6b21\u4e00\u5f20\u5361\uff1a\u9009\u4e2d\u4e00'
                    '\u4e2a\u9009\u9879\u540e\uff0c\u4e0b\u4e00\u5f20\u5361'
                    '\u81ea\u52a8\u51fa\u73b0\uff1b\u5168\u90e8\u7b54\u5b8c'
                    '\u540e\u51fa\u73b0\u63d0\u4ea4\u6309\u94ae\u3002',
        'kpi_cards': '\u5361\u7247',
        'kpi_decided': '\u5df2\u51b3\u5b9a',
        'kpi_pending': '\u5f85\u51b3\u5b9a',
        'review_head': '\u590d\u67e5\u5e76\u63d0\u4ea4',
        'submit': '\u63d0\u4ea4',
        'submit_hint': '\u6574\u8f6e\u53ea\u63d0\u4ea4\u4e00\u6b21\uff1a'
                       '\u63d0\u4ea4\u540e\u672c\u8f6e\u7b54\u6848\u5199'
                       '\u5165\u672c\u5730\u7b54\u6848\u6587\u4ef6\uff0c'
                       '\u9875\u9762\u968f\u540e\u81ea\u52a8\u5173\u95ed\u3002',
        'keys_switch': '\u5207\u6362\u5361\u7247',
        'keys_browse': '\u6d4f\u89c8\u9009\u9879',
        'keys_pick': '\u9009\u62e9\u9009\u9879',
        'keys_confirm': '\u786e\u8ba4\u9009\u4e2d\u9879',
        'keys_submit': '\u63d0\u4ea4\u672c\u8f6e',
        'keys_back': '\u8fd4\u56de\u5361\u7247',
        'align_hint': '\u60ac\u505c\u5c55\u5f00',
        'align_seq': '\u5e8f\u53f7',
        'align_question': '\u95ee\u9898',
        'align_decision': '\u51b3\u5b9a',
        'align_decided': '\u5df2\u51b3\u5b9a',
        'align_pending': '\u5f85\u51b3\u5b9a',
        'design_tree': '\u51b3\u7b56\u6811',
        'kicker': '\u9700\u8981\u51b3\u5b9a',
        'explanation': '\u8bf4\u660e',
        'options_head': '\u9009\u9879',
        'options_sorted': '\uff08\u6309\u6982\u7387\u6392\u5e8f\uff09',
        'recommended': '\u63a8\u8350\u9879',
        'prob_title': '\u8be5\u9009\u9879\u88ab\u91c7\u7eb3\u7684\u5148'
                      '\u9a8c\u6982\u7387',
        'delta_lead': '\u53d8\u5316:',
        'reason_lead': '\u539f\u56e0:',
        'example_lead': '\u4f8b\u5982:',
        'pros_lead': '\u4f18\u70b9:',
        'cons_lead': '\u7f3a\u70b9:',
        'open_tab': '\u5728\u53ef\u4ea4\u4e92\u754c\u9762\u67e5\u770b\u5e76\u6279\u6ce8',
        'next_card': '\u4e0b\u4e00\u5361',
        'review_answers': '\u590d\u67e5\u7b54\u6848',
        'own_label': '\u90fd\u4e0d\u9009\u2014\u2014\u81ea\u5df1\u5199'
                     '\u7b54\u6848',
        'own_placeholder': '\u5199\u51fa\u4f60\u81ea\u5df1\u7684\u7b54'
                           '\u6848\uff08\u9009\u6b64\u9879\u65f6\u5fc5'
                           '\u586b\uff09',
        'paste_aria': '\u7c98\u8d34\u6216\u62d6\u5165\u622a\u56fe\uff08'
                      '\u53ef\u9009\uff09',
        'paste_hint': '\u7c98\u8d34\u6216\u62d6\u5165\u622a\u56fe\uff08'
                      '\u53ef\u9009\u2014\u2014\u968f\u8fd9\u6761\u7b54'
                      '\u6848\u4e00\u8d77\u63d0\u4ea4\uff09',
        'own_missing': '\uff08\u81ea\u5199\u7b54\u6848\u672a\u586b\u5199'
                       '\uff09',
        'not_decided': '\uff08\u5c1a\u672a\u51b3\u5b9a\uff09',
        'own_answer': '\u81ea\u5199\u7b54\u6848',
        'edit': '\u4fee\u6539',
        'decide_first': '\u8bf7\u5148\u51b3\u5b9a\u8fd9\u5f20\u5361\uff1a'
                        '\u9009\u4e00\u4e2a\u9009\u9879\u3002',
        'fmt_count_card': '\u5361 %d / %d \u00b7 \u5df2\u51b3\u5b9a %d',
        'fmt_count_review': '\u590d\u67e5 \u00b7 \u5df2\u51b3\u5b9a %d / %d',
        'fmt_live_card': '\u7b2c %d \u5361\uff0c\u5171 %d \u5361',
        'fmt_live_review': '\u590d\u67e5\uff1a%d / %d \u9879\u5df2\u51b3'
                           '\u5b9a',
        'fmt_attached': '\u9644 %d \u5f20\u622a\u56fe',
        'fmt_write_missing': '\u8bf7\u4e3a\u8fd9\u4e9b\u5361\u5199\u51fa'
                             '\u81ea\u5199\u7b54\u6848\uff1a%s\uff08'
                             '\u6700\u540e\u4e00\u4e2a\u9009\u9879\u91cc'
                             '\u7684\u8f93\u5165\u6846\u2014\u2014\u5907'
                             '\u6ce8\u680f\u4e0d\u662f\u7b54\u6848\uff09',
        'fmt_answer_missing': '\u8fd8\u6709\u5361\u6ca1\u4f5c\u7b54\uff0c'
                              '\u4e0d\u80fd\u63d0\u4ea4\uff1a%s',
        'paste_image_err': '\u8bf7\u7c98\u8d34\u56fe\u7247\uff08png / '
                           'jpg / gif / webp\uff09',
        'fmt_img_too_large': '\u56fe\u7247\u592a\u5927\uff08\u4e0a\u9650 '
                             '8 MB\uff09\uff1a%s',
        'img_limit': '\u6bcf\u5f20\u5361\u6700\u591a 4 \u5f20\u56fe\u7247',
        'lightbox_aria': '\u653e\u5927\u56fe\uff1b\u70b9\u51fb\u6216\u6309 '
                         'Esc \u5173\u95ed',
        'fmt_remove_img': '\u79fb\u9664 %s',
        'prev_card_aria': '\u4e0a\u4e00\u5361',
        'next_card_aria': '\u4e0b\u4e00\u5361\u6216\u590d\u67e5',
        'option_image_alt': '\u9009\u9879\u622a\u56fe',
        'click_enlarge': '\u70b9\u51fb\u653e\u5927',
        'evbadge': '\u7ed3\u6784\u5bf9\u6bd4\u2014\u2014\u975e\u6e32\u67d3'
                   '\u8bc1\u636e\uff1b\u9002\u7528\u56de\u586b\u89c4\u5219',
        'confirm_title': '\u63d0\u4ea4\u6210\u529f',
        'fmt_confirm_saved': '\u5df2\u4fdd\u5b58\u5230 %s',
        'confirm_closing': '\u5373\u5c06\u81ea\u52a8\u5173\u95ed ...',
        'fmt_confirm_countdown': '\u5c06\u5728 %d \u79d2\u540e\u81ea\u52a8'
                                 '\u5173\u95ed ...',
        'confirm_fallback': '\u672c\u8f6e\u5b8c\u6210\u2014\u2014\u7b54'
                            '\u6848\u5df2\u4ea4\u7ed9\u7f16\u6392\u65b9'
                            '\u3002\u4f60\u53ef\u4ee5\u5173\u95ed\u6b64'
                            '\u6807\u7b7e\u9875\u3002',
        'error_title': '\u63d0\u4ea4\u51fa\u9519',
        'rejected_guidance': '\u4ec0\u4e48\u90fd\u6ca1\u5199\u5165\u3002'
                             '\u6309\u6d4f\u89c8\u5668\u540e\u9000\u952e'
                             '\u56de\u53bb\u4fee\u6539\u7b54\u6848\u3002',
        'images_guidance': '\u4ec0\u4e48\u90fd\u6ca1\u5199\u5165\u3002'
                           '\u6309\u6d4f\u89c8\u5668\u540e\u9000\u952e'
                           '\u56de\u53bb\u4fee\u6539\u56fe\u7247\u3002',
        'retry_guidance': '\u4ec0\u4e48\u90fd\u6ca1\u5199\u5165\u3002'
                          '\u6309\u6d4f\u89c8\u5668\u540e\u9000\u952e'
                          '\u91cd\u8bd5\u3002',
        'internal_guidance': '\u4ec0\u4e48\u90fd\u6ca1\u5199\u5165\u3002'
                             '\u67e5\u770b\u670d\u52a1\u5668\u7684\u63a7'
                             '\u5236\u53f0\u8f93\u51fa\u3002',
        'subtitle_single': '\u9009\u4e00\u4e2a\u9009\u9879\u3001\u586b'
                           '\u4e00\u53e5\u5907\u6ce8\uff0c\u7136\u540e'
                           '\u63d0\u4ea4\uff1b\u9875\u9762\u4f1a\u81ea'
                           '\u884c\u786e\u8ba4\u5e76\u5173\u95ed\u3002',
        'note_head': '\u5907\u6ce8',
        'note_placeholder': '\u7406\u7531\u3001\u7ea6\u675f\u3001\u987e'
                            '\u8651\uff08\u53ef\u9009\uff09',
        'select_first': '\u8bf7\u5148\u9009\u4e00\u4e2a\u9009\u9879',
        'attachments': '\u9644\u4ef6',
        'links_hint': '\u5982\u679c\u6d4f\u89c8\u5668\u62e6\u4e0b file:// '
                      '\u94fe\u63a5\uff0c\u590d\u5236\u8def\u5f84\u5230'
                      '\u6587\u4ef6\u8d44\u6e90\u7ba1\u7406\u5668\u6253'
                      '\u5f00\u3002',
        'no_options': '\uff08\u672a\u63d0\u4f9b --options\uff09',
        'fmt_ann_count': '%d \u6761\u6807\u6ce8',
        'ann_toggle': '\u5907\u6ce8',
        'ann_undo': '\u64a4\u9500',
        'ann_redo': '\u6062\u590d',
        'ann_stop': '\u5907\u6ce8\u4e2d\u2014\u2014\u70b9\u51fb\u505c'
                    '\u6b62',
        'ann_save': '\u4fdd\u5b58\u5e76\u66ff\u6362',
        'ann_save_title': '\u622a\u56fe\u4e0e\u5907\u6ce8\u66ff\u6362\u8be5'
                          '\u9009\u9879\u8bc1\u636e\uff0c\u968f\u7b54'
                          '\u6848\u53d1\u9001',
        'ann_return': '\u8fd4\u56de\u51b3\u7b56\u53f0',
        'ann_return_title': '\u4e0d\u4fdd\u5b58\uff0c\u5173\u95ed\u6b64'
                            '\u9875\u56de\u5230\u51b3\u7b56\u53f0',
        'fmt_ai_count': 'AI \u6807\u6ce8 %d \u5904',
        'ai_clear': '\u6e05\u9664\u5168\u90e8 AI',
        'ai_restore': '\u6062\u590d AI',
        'ai_remove': '\u79fb\u9664 AI \u6807\u6ce8',
        'tool_box': '\u6846',
        'tool_arrow': '\u7bad\u5934',
        'tool_eraser': '\u6a61\u76ae\u64e6',
        'proto_gen': '\u751f\u6210\u539f\u578b',
        'proto_gen_title': '\u8bf4\u4e0d\u6e05\u8981\u6539\u6210\u4ec0\u4e48'
                           '\uff1f\u4fdd\u5b58\u6279\u6ce8\uff0c\u8bf7 AI '
                           '\u4e3a\u8be5\u9009\u9879\u751f\u6210\u4e00\u4e2a'
                           '\u539f\u578b',
        'proto_requested': '\u5df2\u8bf7\u6c42\u539f\u578b',
        'proto_badge': '\u5df2\u8bf7\u6c42\u751f\u6210\u539f\u578b\u00b7'
                       '\u70b9\u51fb\u8fdb\u5165\u4e0b\u4e00\u4e2a\u95ee'
                       '\u9898',
        'ann_capture_fail': '\u9875\u9762\u622a\u56fe\u5931\u8d25\uff1a'
                            '\u5df2\u6539\u4e3a\u53ea\u53d1\u9001\u5907'
                            '\u6ce8',
        'fmt_ann_save_fail': '\u4fdd\u5b58\u670d\u52a1\u7aef\u8bb0\u5f55'
                             '\u5931\u8d25\uff1a%s',
        'saved_badge': '\u5df2\u7ecf\u4fdd\u5b58\u4f60\u7684\u6279\u6ce8',
        'badge_next_card': '\u70b9\u51fb\u8fdb\u5165\u4e0b\u4e00\u4e2a\u95ee'
                           '\u9898',
        'badge_review': '\u70b9\u51fb\u590d\u67e5\u5e76\u63d0\u4ea4',
        'ann_unlinked': '\u672c\u9875\u672a\u5173\u8054\u51b3\u7b56\u53f0'
                        '\u7684\u9009\u9879',
        'fmt_ann_cap': '%d\uff1a\u8fd9\u91cc\u6307\u4ec0\u4e48\uff1f',
        'fmt_ann_remove': '\u5220\u9664\u6807\u6ce8 %d',
        'ann_open_first': '\u8bf7\u5148\u4ece\u51b3\u7b56\u53f0\u9009'
                          '\u9879\u6253\u5f00\u672c\u9875\u3002',
        'ann_draw_first': '\u8bf7\u5148\u753b\u81f3\u5c11\u4e00\u4e2a'
                          '\u6807\u6ce8\u3002',
    },
}


def _chrome_lang(lang):
    """The chrome table for a spec lang: zh* -> zh, anything else -> en."""
    return 'zh' if str(lang or '').lower().startswith('zh') else 'en'


def _t(lang, key):
    """One chrome string for the page language (falls back to English)."""
    return _CHROME[_chrome_lang(lang)].get(key) or _CHROME['en'][key]


# Stylesheet for the decision cards:
# gradient page background, white top bar, per-card header band, gradient
# question block with blue left edge, purple RECOMMENDED tag, option cards,
# bold key content. Option rows follow the decision-option anatomy:
# slim rows (radio dot + bold numbered title + tags) with details ALWAYS
# expanded (no hover motion). Template contract classes
# (prob/bl/exp/opshead/delta/why/rec/opt/card/qid) are unchanged; motion is
# disabled globally under prefers-reduced-motion via the media query at the
# end of this stylesheet.
_CSS = """
:root { color-scheme: light;
  --card: #fff;
  --accent: #3167ff; --ai: #8751f5; --border: #d4e3f6;
  --text: #0f172a; --soft: #475569; --faint: #64748b;
  --ok: #16a34a; --okbg: #dcfce7;
  --icon-size-sm: 12px; --icon-size-m: 15px; --icon-size-lg: 20px; --icon-size-btn: 14px;
  --icon-stroke: 2px;
  --icon-dim: var(--ws-palette-fg-muted, #64748b);
  --icon-soft: var(--ws-palette-fg-muted, #475569);
  --icon-accent: var(--ws-palette-primary, #3167ff);
  --icon-ai: var(--ai);
  /* palette tokens (console-confirmed, round 3): ink / line /
     tint / accent; near shades merged (delta RGB <= 5) */
  --ink-strong: #173d79; --ink-head: #334155; --ink-link: #2563eb;
  --ink-kicker: #4f5890; --ink-sub: #234568; --ink-brand: #2553a2;
  --ink-ai: #7740d0; --ink-ok: #166534; --ink-warn: #92400e;
  --ink-err: #b91c1c; --ink-mute: #94a3b8; --ink-label: #1f4e79;
  --line-strong: #b9d2f3; --line: #d4e4fb; --line-soft: #e2e8f0;
  --line-mute: #cbd5e1; --line-err: #fca5a5; --line-ai: #e0ccff;
  --tint-blue: #eef4fd; --tint-blue-chip: #e8f0ff;
  --tint-blue-deep: #edf5ff; --tint-ai: #efe5ff; --tint-gray: #f1f5f9;
  --tint-err: #fef2f2; --tint-warn: #fef3c7; --tint-radio: #e9eef6;
  --accent-grad: #4d7bff; --accent-grad-hover: #3d6ef5;
  --accent-hover-text: #2559d6; --accent-light: #5b86ff;
  --accent-ring: #dfeaff; --accent-border-hover: #94b7ff; }
* { box-sizing: border-box; }
body { font-family: system-ui, "PingFang SC", "Microsoft YaHei", sans-serif;
       font-size: 13.5px; line-height: 1.5; color: var(--text); margin: 0;
       background: radial-gradient(ellipse at 8% 0%, var(--tint-blue) 0, transparent 42%),
                   radial-gradient(ellipse at 96% 4%, #f0e8ff 0, transparent 42%),
                   linear-gradient(135deg, #f6fbff, #f3f6fd 55%, #f9f7ff);
       background-attachment: fixed; }
body > header { background: #fff; border-bottom: 1px solid var(--line);
                box-shadow: 0 2px 15px rgba(60, 107, 202, .06);
                padding: 14px 24px; }
body > header h1 { margin: 0 0 2px; font-size: 16px; font-weight: 700;
                   letter-spacing: -0.02em; color: var(--ink-brand); }
body > header p { margin: 0; color: var(--faint); font-size: 12px; }
main { max-width: 1080px; margin: 18px auto 28px; padding: 0 24px; }
section { background: #fff; border: 1px solid var(--line-strong); border-radius: 14px;
          box-shadow: 0 1px 2px rgba(15, 23, 42, .04),
                      0 12px 32px -14px rgba(56, 99, 179, .14);
          padding: 18px 22px; margin: 0 0 18px; }
section.card { padding: 0; overflow: hidden; }
h2 { margin: 0 0 10px; font-size: 14px; color: var(--ink-head); }
.chead { display: flex; align-items: center; gap: 8px; padding: 12px 24px;
         border-bottom: 1px solid var(--line);
         background: var(--card);
         box-shadow: none; }
.cbody { padding: 20px 28px 24px; }
.qid { background: var(--tint-blue-chip); color: var(--ink-link); border: 1px solid var(--line);
       text-transform: capitalize;
       border-radius: 99px; padding: 1px 10px; font-size: 11px;
       font-weight: 700; }
.ctype { font-size: 11px; color: var(--faint); letter-spacing: .04em;
         text-transform: uppercase; font-weight: 700; }
.dq { display: flex; gap: 12px; align-items: center;
      background: none;
      color: var(--ink-strong); border: 1px solid var(--line);
      border-left: 4px solid var(--accent); border-radius: 10px;
      padding: 14px 18px; margin: 0 0 16px; }
.qmark { width: 38px; height: 38px; border-radius: 12px;
         background: linear-gradient(135deg, var(--accent), var(--accent-light)); color: #fff;
         display: grid; place-items: center; font-size: 20px; flex: none;
         box-shadow: 0 4px 12px rgba(49, 103, 255, .22); }
.kicker { font-size: 11px; color: var(--ink-kicker); font-weight: 700;
          letter-spacing: .05em; text-transform: uppercase; }
.card h2 { margin: 3px 0 0; font-size: 20px; line-height: 1.45;
           letter-spacing: -0.015em; color: var(--ink-strong); font-weight: 700; }
.exp { background: transparent; border: 0; border-radius: 0;
       box-shadow: none; padding: 0; margin: 0 0 14px; }
.exphead, .opshead { display: flex; align-items: center; gap: 5px;
                     font-size: 13px; font-weight: 700; color: var(--ink-head); }
.exphead { margin: 0 0 6px; }
.opshead { margin: 0 0 10px; }
.bl { display: block; position: relative; padding-left: 18px;
      font-size: 13px; line-height: 1.8; color: var(--soft); }
.bl::before { content: "\\2022"; position: absolute; left: 6px;
              color: var(--ink-mute); }
.olist { display: flex; flex-direction: column; gap: 10px; }
.opt { display: block; margin: 0; cursor: pointer; position: relative; }
.opt input[type=radio] { position: absolute; opacity: 0;
                         width: 1px; height: 1px; }
.optcard { display: flex; gap: 12px; align-items: flex-start;
           border: 1px solid var(--line); border-radius: 10px;
           padding: 13px 18px; background: var(--tint-gray); font-size: 13.5px;
           transition: border-color .18s, background .18s, box-shadow .22s; }
.opt:hover .optcard { border-color: var(--accent-border-hover); }
.opt input:checked + .optcard { border-color: var(--accent);
          background: var(--tint-blue-deep); box-shadow: 0 0 0 2px var(--accent-ring); }
.opt input:focus-visible + .optcard { outline: 2px solid var(--accent);
          outline-offset: 2px; }
.oradio { width: 22px; height: 22px; border-radius: 50%; flex: none;
          background: var(--tint-radio); border: 2px solid var(--line-mute); margin-top: 1px;
          display: grid; place-items: center; color: #fff; font-size: 12px;
          font-weight: 700; line-height: 1;
          transition: background .18s, border-color .18s; }
.oradio::after { content: "\\2713"; opacity: 0; }
.opt input:checked + .optcard .oradio { border-color: var(--accent);
          background: var(--accent); }
.opt input:checked + .optcard .oradio::after { opacity: 1; }
.omain { display: flex; flex-direction: column; min-width: 0; flex: 1; }
.otitle { display: flex; align-items: center; flex-wrap: wrap; gap: 8px;
          min-height: 24px; }
.otitle b { color: var(--ink-strong); font-size: 14.5px; }
.oreveal { display: block; margin-top: 8px; }
svg.ic { width: var(--icon-size-m); height: var(--icon-size-m);
          fill: none; stroke: currentColor;
          stroke-width: var(--icon-stroke); stroke-linecap: round;
          stroke-linejoin: round;
          vertical-align: -2px; margin-right: 6px; flex: none; }
svg.ic-lg { width: var(--icon-size-lg); height: var(--icon-size-lg);
            margin-right: 0; }
svg.ic-sm { width: var(--icon-size-sm); height: var(--icon-size-sm);
            vertical-align: -1px; margin-right: 4px; }
svg.ic-xs { width: 11px; height: 11px; vertical-align: -1px;
            margin-right: 3px; }
.linkrow { display: flex; justify-content: flex-end; margin: 10px 0 0; }
.openlink { display: inline-flex; align-items: center; gap: 5px;
           margin: 10px 0 0; color: var(--ink-link); font-weight: 700;
           font-size: 12.5px; text-decoration: none;
           border: 1px solid var(--line); border-radius: 8px;
           padding: 4px 10px; background: var(--tint-blue); }
.openlink:hover { border-color: var(--accent); }
.optimg { display: block; width: auto; max-width: 100%; height: auto;
          border: 1px solid var(--line); border-radius: 8px;
          background: var(--tint-gray); margin: 8px 0; cursor: zoom-in; }
.shotwrap { position: relative; display: inline-block; max-width: 100%; }
.shotbox { position: absolute; border: 3px solid #d92d20; border-radius: 12px;
           box-shadow: 0 0 0 2px rgba(255, 255, 255, .75);
           pointer-events: none; }
.shotnum { position: absolute; top: -12px; left: -12px; min-width: 24px;
           height: 24px; border-radius: 50%; background: #d92d20; color: #fff;
           font-size: 13px; font-weight: 700; display: grid;
           place-items: center; padding: 0 5px; }
.shotlabel { position: absolute; top: 100%; left: -3px; margin-top: 5px;
             white-space: nowrap; background: #d92d20; color: #fff;
             font-size: 12px; font-weight: 700; border-radius: 6px;
             padding: 2px 8px; }
.delta { display: block; color: var(--soft); font-size: 13px;
         margin: 0 0 4px; }
.delta b, .why b { color: var(--ink-sub); }
.prob { display: inline-block; background: var(--tint-gray); color: var(--soft);
        border: 1px solid var(--line-soft); font-size: 11px; font-weight: 700;
        border-radius: 99px; padding: 1px 9px; margin-right: 2px; }
.problegend { font-size: 11px; color: var(--faint); font-weight: 700;
              margin-left: 8px; letter-spacing: .02em; }
.rec { display: inline-block; background: var(--tint-ai); color: var(--ink-ai);
       border: 1px solid var(--line-ai); font-size: 11px; font-weight: 700;
       letter-spacing: .4px; border-radius: 99px; padding: 2px 10px; }
.why { display: block; color: var(--soft); font-size: 13px;
       margin: 0; }
textarea { width: 100%; border: 1px solid var(--line-mute); border-radius: 10px;
           padding: 9px 12px; font: inherit; resize: vertical;
           background: #fff; }
textarea:focus { outline: 2px solid var(--accent); outline-offset: 1px; }
.owntext { width: 100%; margin-top: 10px; border: 1.5px solid var(--line-mute);
           border-radius: 8px; padding: 10px 12px; font: inherit;
           font-size: 13.5px; background: #fff; }
.owntext:focus { outline: 2px solid var(--accent); outline-offset: 1px; }
.opt input:checked + .optcard .owntext { border-color: var(--accent);
           box-shadow: 0 0 0 2px var(--accent-ring); }
.pastezone { display: flex; align-items: center; gap: 8px; margin-top: 8px;
             border: 1.5px dashed var(--line-mute); border-radius: 8px;
             padding: 9px 12px; font-size: 13px; color: var(--muted, #6b7280);
             cursor: pointer; }
.pastezone:hover, .pastezone:focus { border-color: var(--accent);
             color: var(--ink-head); outline: none; }
.pastelist { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
.pastechip { position: relative; display: inline-block; }
.pastechip img { width: 56px; height: 56px; object-fit: cover;
             border: 1px solid var(--line); border-radius: 8px; display: block; }
.pastex { position: absolute; top: -7px; right: -7px; width: 20px; height: 20px;
             border-radius: 50%; border: 1px solid var(--line);
             background: #fff; color: var(--ink-head); cursor: pointer;
             font-size: 13px; line-height: 1; display: grid;
             place-items: center; padding: 0; }
section.actions { display: flex; align-items: center; gap: 14px;
                  background: var(--tint-gray); border: 1px solid var(--line);
                  border-radius: 12px; }
button { display: inline-flex; align-items: center; gap: 7px;
         background: linear-gradient(135deg, var(--accent), var(--accent-grad)); color: #fff;
         border: 0; border-radius: 99px;
         padding: 10px 24px; font: inherit; font-weight: 700; cursor: pointer;
         min-height: 40px; letter-spacing: .01em;
         box-shadow: 0 6px 16px -6px rgba(49, 103, 255, .45);
         transition: background .18s, transform .18s, box-shadow .18s; }
button:hover { background: linear-gradient(135deg, var(--accent-hover-text), var(--accent-grad-hover));
               transform: translateY(-1px);
               box-shadow: 0 8px 20px -6px rgba(49, 103, 255, .5); }
button:active { transform: translateY(0); }
button:disabled { opacity: .4; cursor: default; }
button svg.ic { margin-right: 0; width: var(--icon-size-btn); height: var(--icon-size-btn); }
.links li { margin: 6px 0; }
.links a { color: var(--accent); font-weight: 600; }
.links code { background: var(--tint-gray); padding: 2px 6px; border-radius: 6px;
              font-size: 12px; color: var(--soft); }
.hidden { display: none; }
.errbox { position: static; margin: 0 auto 14px; border: 1px solid var(--line-err);
          background: var(--tint-err); color: var(--ink-err); font-weight: 700;
          padding: 12px 16px; border-radius: 10px; max-width: min(100%, 640px);
          box-shadow: 0 8px 24px rgba(15, 23, 42, .12); }
/* --- stepper mode: one card at a time (body.stepper on the --spec page) --- */
body.stepper { min-height: 100vh; display: flex; flex-direction: column; }
body.stepper > header { position: sticky; top: 0; z-index: 10; flex: none; }
.pbar { display: flex; gap: 3px; height: 6px; margin-top: 10px;
        position: relative; }
.pseg { flex: 1; height: 6px; border-radius: 99px;
        background: var(--line-mute); transition: background .25s ease;
        cursor: pointer; }
.pseg:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.pseg.on { background: linear-gradient(90deg, var(--accent), var(--ai)); }
.pbaltip { position: absolute; bottom: 14px; transform: translateX(-50%);
           background: #111827; color: #fff; border-radius: 8px;
           padding: 5px 10px; font-size: 12px; white-space: nowrap;
           max-width: 420px; overflow: hidden; text-overflow: ellipsis;
           pointer-events: none; display: none; z-index: 8; }
.pbaltip.show { display: block; }
.kpi { position: relative; }
.kic { position: absolute; right: 12px; top: 50%; transform: translateY(-50%);
       width: 18px; height: 18px; color: var(--kc, var(--accent));
       opacity: .75; }
.pcount { position: absolute; right: 24px; top: 16px; margin: 0;
          font-size: 13px; font-weight: 700;
          color: var(--ink-strong); letter-spacing: .04em; }
.kpirow { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px;
          margin: 12px auto 18px; width: 100%; }
.kpi { text-align: left; border: 1px solid var(--line); border-top: 3px solid
       var(--kc, var(--accent)); border-radius: 10px; padding: 4px 14px;
       height: 52px; box-sizing: border-box;
       background: var(--card); cursor: pointer; font: inherit;
       transition: background .15s, border-color .15s, box-shadow .22s,
                   transform .15s; }
.kpi:hover { background: var(--tint-blue); transform: translateY(-1px);
             box-shadow: 0 4px 14px rgba(15, 23, 42, .10); }
.kpi small { display: block; color: var(--faint); font-size: 11px;
             line-height: 1.2; text-transform: uppercase; letter-spacing: .05em; }
.kpi b { font-size: 22px; line-height: 1.15; color: var(--kc, var(--accent)); }
.kpi[data-kpi="total"] { --kc: var(--accent); }
.kpi[data-kpi="decided"] { --kc: var(--ok); }
.kpi[data-kpi="pend"] { --kc: #d97706; }
body.stepper main { flex: 1; display: flex;
                    flex-direction: column; margin: 12px auto 0;
                    padding-bottom: 52px; }
.stage { flex: 1; display: flex; flex-direction: column;
         justify-content: center; }
.qcard { display: none; margin: 0; }
.qcard.active { display: block; }
.qreview { display: none; margin: 0 auto; max-width: 720px; width: 100%; }
.qreview.active { display: block; }
.qstep { margin-left: auto; background: var(--tint-blue); color: var(--soft);
         border: 1px solid var(--line); border-radius: 99px; padding: 1px 10px;
         font-size: 11px; font-weight: 700; }
.nextbtn { display: none; margin-top: 14px; width: 100%;
           justify-content: center; background: #fff;
           color: var(--ink-head); border: 1px solid var(--line);
           box-shadow: none; }
.nextbtn:hover { background: var(--tint-blue); transform: none;
                 box-shadow: none; }
.qcard.decided .nextbtn { display: inline-flex; }
.rrow { display: flex; align-items: flex-start; gap: 10px;
        padding: 10px 2px; border-bottom: 1px solid var(--line-soft);
        font-size: 13px; }
.rrow:last-child { border-bottom: 0; }
.rrow b { color: var(--ink-strong); }
.rmain { display: flex; flex-direction: column; gap: 2px; flex: 1;
         min-width: 0; }
.rchoice { color: var(--soft); overflow: hidden; display: -webkit-box;
           -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.rrow.rmiss .rchoice { color: var(--ink-err); font-weight: 700; }
.rnote { color: var(--faint); font-size: 12px; overflow: hidden;
         display: -webkit-box; -webkit-line-clamp: 2;
         -webkit-box-orient: vertical; }
.rrow .qid { flex: none; margin-top: 1px; }
.rlink { border: 1px solid var(--border); background: #fff;
         border-radius: 7px; padding: 3px 10px; font: inherit; font-size: 12px;
         color: var(--ink-link); cursor: pointer; flex: none; }
.rlink:hover { background: var(--tint-blue); }
.keysbar { position: sticky; bottom: 0; z-index: 5; flex: none;
           display: flex; gap: 16px; justify-content: center;
           padding: 8px 16px 10px; color: var(--faint); font-size: 12px;
           flex-wrap: wrap; background: rgba(247, 250, 254, .88);
           backdrop-filter: blur(6px); border-top: 1px solid var(--line-soft); }
.keysbar .k { display: inline-block; background: var(--tint-blue);
              border: 1px solid var(--border); border-bottom-width: 2px;
              border-radius: 5px; padding: 0 6px; font-size: 11px;
              color: var(--ink-head); margin-right: 3px; }
/* Green saved-annotation badge beside the picked option (the palette's ok
   family - loud "saved, click to continue"): the save lands on this card,
   never auto-advances, and the badge is the explicit way forward. */
.savebadge { display: inline-flex; align-items: center; gap: 6px;
             margin-left: 8px; min-height: 0;
             background: var(--okbg); color: var(--ink-ok);
             border: 1.5px solid var(--ok); border-radius: 99px;
             padding: 3px 12px; font: inherit; font-size: 12px;
             font-weight: 700; cursor: pointer;
             box-shadow: 0 0 0 3px rgba(22, 163, 74, .18);
             animation: savebadge-in .25s ease; }
.savebadge:hover { background: var(--okbg); border-color: var(--ink-ok);
                   transform: none; box-shadow: 0 0 0 4px rgba(22, 163, 74, .25); }
.savebadge b { color: var(--ink-ok); }
.savebadge svg.ic { width: 12px; height: 12px; margin-right: 0; }
@keyframes savebadge-in { from { opacity: 0; transform: scale(.92); }
                          to { opacity: 1; transform: none; } }
.protochip { display: inline-flex; align-items: center;
             margin-left: 8px; background: #eef2ff; color: #4338ca;
             border: 1.5px solid #a5b4fc; border-radius: 99px;
             padding: 3px 10px; font-size: 12px; font-weight: 700; }
.bl b { color: var(--ink-label); }
.dqask { margin: 8px 0 0; font-size: 16px; color: var(--ink-strong);
         font-weight: 700; line-height: 1.55;
         background: none; border-left: 3px solid var(--accent);
         border-radius: 0 8px 8px 0; padding: 8px 12px; }
.dqask b { color: var(--ink-link); }
.bl-example { background: var(--tint-gray); border: 1px solid var(--line-soft);
              border-left: 3px solid var(--ink-mute); border-radius: 0 8px 8px 0;
              padding: 7px 12px 7px 14px; margin: 4px 0;
              color: var(--soft); }
.bl-example b { color: var(--soft); }
.bl-example::before { display: none; }
.bl code { background: var(--tint-gray); border: 1px solid var(--line-soft); border-radius: 5px;
           padding: 0 5px; font-family: Consolas, "Courier New", monospace;
           font-size: 12px; color: var(--ink-head); }
.bl.sub { margin-left: 24px; }
.bl.sub::before { display: none; }
.bl.num::before { display: none; }
.cbar { margin-left: auto; display: flex; gap: 6px; }
.cnav { width: 30px; height: 30px; border-radius: 8px;
        border: 1px solid var(--line); background: #fff;
        color: var(--ink-head); cursor: pointer; font-size: 17px;
        line-height: 1; display: grid; place-items: center; padding: 0;
        transition: background .15s, border-color .15s, transform .15s; }
.cnav:hover:not(:disabled) { background: var(--tint-blue);
                             border-color: var(--accent); transform: translateY(-1px); }
.cnav:disabled { opacity: .3; cursor: not-allowed; }
@keyframes card-enter { from { opacity: 0; transform: translateY(8px); }
                        to { opacity: 1; transform: none; } }
.qcard.active { animation: card-enter .35s ease; }
.evbadge { display: flex; align-items: center; gap: 7px;
           border: 1px solid var(--line-mute); background: var(--tint-warn);
           color: var(--ink-warn); font-weight: 700; font-size: 12.5px;
           border-radius: 10px; padding: 9px 14px; margin: 0 0 14px; }
.lightbox { position: fixed; inset: 0; z-index: 30;
            background: rgba(15, 23, 42, .55); display: grid;
            place-items: center; padding: 32px; cursor: zoom-out; }
.lightbox img { max-width: 100%; max-height: 100%; width: auto; height: auto;
                border-radius: 10px; background: #fff;
                box-shadow: 0 24px 64px rgba(15, 23, 42, .35); }
#live { position: absolute; width: 1px; height: 1px; overflow: hidden;
        clip: rect(0 0 0 0); white-space: nowrap; }
.hint { color: var(--faint); font-size: 12px; }
.empty { color: var(--ink-mute); }
.alignwrap { margin: 0 0 10px; padding: 0; background: none;
             border: 0; box-shadow: none; border-radius: 0; }
.alignfold { display: grid; grid-template-rows:0fr;
             transition: grid-template-rows .32s cubic-bezier(.2,1.2,.4,1),
                         opacity .2s; opacity: .8; }
.alignwrap:hover .alignfold, .alignwrap:focus-within .alignfold {
  grid-template-rows: 1fr; opacity: 1; }
.alignfold .align { overflow: hidden; min-height: 0; margin: 0; }
.alignstrip { display: flex; width: 100%; align-items: center; gap: 10px;
              padding: 0 14px; height: 52px; box-sizing: border-box;
              border: 1px solid var(--line); border-radius: 10px;
              background: var(--card); cursor: default;
              transition: border-radius .2s; }
.alignwrap:hover .alignstrip, .alignwrap:focus-within .alignstrip {
  border-radius: 10px 10px 0 0; border-bottom: 0; }
.alignstrip .aligntitle { margin: 0; font-size: 13px;
                          color: var(--ink-strong); font-weight: 700;
                          text-transform: capitalize; }
.alignhint { color: var(--faint); font-size: 11px; margin-left: auto; }
.align { width: 0; min-width: 100%; margin: 4px 0 18px; padding: 0; background: none;
         border: 0; box-shadow: none; border-radius: 0; }
.aligntitle { margin: 0 0 8px; font-size: 14px; color: var(--ink-strong); font-weight: 700; }
/* The frame lives on the table INSIDE the overflow-hidden clipper, so a
   collapsed fold hides it completely (a frame on the clipper itself would
   paint its own border even at zero height). Joined to the strip: the
   strip drops its bottom border and rounds only the top on hover. */
.align table { width: 100%; border-collapse: collapse; background: var(--card);
               border: 1px solid var(--line); border-top: 0;
               border-radius: 0 0 10px 10px; overflow: hidden;
               font-size: 13px; }
.align th, .align td { text-align: left; padding: 8px 12px;
                       border-bottom: 1px solid var(--line-soft); }
.align th { background: var(--tint-blue); color: var(--ink-strong); font-size: 12px;
            letter-spacing: .03em; text-transform: uppercase; }
.align tr:last-child td { border-bottom: 0; }
.chip { display: inline-block; font-size: 11px; font-weight: 700;
        border-radius: 99px; padding: 1px 9px; margin-right: 4px; }
.chip.ok { background: var(--okbg); color: var(--ink-ok); }
.chip.pend { background: var(--tint-warn); color: var(--ink-warn); }
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { transition: none !important;
                           animation: none !important; }
}
"""

# JS for the batch page (--spec): stepper mode — one card visible at a time.
# Selecting an option auto-advances to the next card (650 ms, cancelled by any
# pointerdown inside the card, note focus, a card switch, or opening the
# image lightbox; a "Next card" button appears once a card is decided so
# mouse users get the same explicit advance as keyboard users); Arrow keys
# slide between cards, ArrowUp/Down move option focus, digits 1-9 pick an
# option, Enter confirms the focused option. show() resets scroll to the top
# and focuses the active card (screen-reader announcement via the aria-live
# region), and the keys hint bar swaps to submit-oriented hints on the review
# panel. After the last card a review panel shows every decision plus the
# single Submit button. The submit handler builds one array with one entry
# per card and hands it to the hidden "payload" field; the native form POST
# goes to /answer and the server replies with the confirmation page.
_JS_SPEC = """
const form = document.getElementById('panel');
const errbox = document.getElementById('errorbox');
const cards = Array.from(document.querySelectorAll('.qcard'));
const review = document.getElementById('reviewcard');
const total = cards.length;
let cur = 0;
let advTimer = null;
let suppressAdvanceOnce = false;  // a save-pick lands without auto-advance
form.addEventListener('submit', onSubmit);

function fail(msg) {
  errbox.textContent = msg;
  errbox.classList.remove('hidden');
}
function nudge(msg) {
  fail(msg);
  setTimeout(function () { errbox.classList.add('hidden'); }, 1800);
}
function motionOK() {
  return !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}
function cancelAdvance() {
  if (advTimer) { clearTimeout(advTimer); advTimer = null; }
}
function answered(i) {
  return !!document.querySelector('input[name="q' + i + '"]:checked');
}
function annTip(seg) {
  const tip = document.getElementById('pbaltip');
  if (!tip || !seg) { return; }
  tip.textContent = seg.title;
  const pr = seg.parentElement.getBoundingClientRect();
  const sr = seg.getBoundingClientRect();
  tip.style.left = Math.round(sr.left - pr.left + sr.width / 2) + 'px';
  tip.classList.add('show');
}
function hideTip() {
  const tip = document.getElementById('pbaltip');
  if (tip) { tip.classList.remove('show'); }
}
function updateProgress() {
  let done = 0;
  for (let i = 0; i < total; i += 1) { if (answered(i)) done += 1; }
  if (typeof updateKpis === 'function') { updateKpis(); }
  // Segmented bar: one equal segment per card, separators between them,
  // filled up to the card the user is on - "which step am I on" is legible.
  const pbar = document.getElementById('pbar');
  if (pbar && pbar.children.length !== total) {
    pbar.innerHTML = '';
    for (let i = 0; i < total; i += 1) {
      const seg = document.createElement('span');
      seg.className = 'pseg';
      seg.setAttribute('role', 'button');
      seg.tabIndex = 0;
      seg.title = QIDS[i] + ' ' + QTITLES[i];
      seg.addEventListener('click', function () { show(i); });
      seg.addEventListener('keydown', function (ev) {
        if (ev.key === 'Enter' || ev.key === ' ') {
          ev.preventDefault(); show(i);
        }
      });
      seg.addEventListener('mouseenter', function () { annTip(seg); });
      seg.addEventListener('mouseleave', hideTip);
      seg.addEventListener('focus', function () { annTip(seg); });
      seg.addEventListener('blur', hideTip);
      pbar.appendChild(seg);
    }
    const tip = document.createElement('div');
    tip.className = 'pbaltip';
    tip.id = 'pbaltip';
    pbar.appendChild(tip);
  }
  if (pbar) {
    const atReview = cur >= total;
    for (let i = 0; i < pbar.children.length; i += 1) {
      const seg = pbar.children[i];
      seg.classList.toggle('on', atReview || i <= cur);
      seg.classList.toggle('here', i === cur && !atReview);
    }
  }
  const label = document.getElementById('pcount');
  if (cur < total) {
    label.textContent = CHROME.fmt_count_card
      .replace('%d', cur + 1).replace('%d', total).replace('%d', done);
  } else {
    label.textContent = CHROME.fmt_count_review
      .replace('%d', done).replace('%d', total);
  }
  const live = document.getElementById('live');
  if (live) {
    live.textContent = cur < total
      ? CHROME.fmt_live_card.replace('%d', cur + 1).replace('%d', total)
      : CHROME.fmt_live_review.replace('%d', done).replace('%d', total);
  }
  cards.forEach(function (card, i) {
    const nb = card.querySelector('.nextbtn');
    if (!nb) { return; }
    const txt = advanceTarget(i) === total
      ? CHROME.review_answers : CHROME.next_card;
    const node = nb.childNodes[nb.childNodes.length - 1];
    if (node.nodeType === 3 && node.textContent !== txt) {
      node.textContent = txt;
    }
  });
  syncAlignment();
}
function syncAlignment() {
  document.querySelectorAll('#aligntable tr[data-qid]').forEach(function (tr) {
    const i = QIDS.indexOf(tr.getAttribute('data-qid'));
    if (i < 0) { return; }
    const sel = document.querySelector('input[name="q' + i + '"]:checked');
    const cell = tr.querySelector('.alcell');
    cell.textContent = '';
    const chip = document.createElement('span');
    chip.className = sel ? 'chip ok' : 'chip pend';
    // The JS-synced chip carries the same icon as the server-rendered one:
    // a text-only rebuild would drop the clock/check mark on load.
    chip.innerHTML = sel ? ICONS.check : ICONS.clock;
    chip.appendChild(document.createTextNode(
        sel ? CHROME.align_decided : CHROME.align_pending));
    cell.appendChild(chip);
    if (sel) {
      let val = sel.value;
      if (sel.hasAttribute('data-own')) {
        const ownEl = document.getElementById('own' + i);
        val = ownEl && ownEl.value.trim() ? ownEl.value : CHROME.own_answer;
      }
      cell.appendChild(document.createTextNode(' ' + val));
    }
  });
}
function updateKeysbar() {
  const bar = document.getElementById('keysbar');
  if (!bar) { return; }
  if (cur === total) {
    bar.innerHTML = '<span><span class="k">Enter</span> '
      + CHROME.keys_submit + '</span>'
      + '<span><span class="k">&#8592;</span> ' + CHROME.keys_back + '</span>';
  } else {
    bar.innerHTML = '<span><span class="k">&#8592;</span>'
      + '<span class="k">&#8594;</span> ' + CHROME.keys_switch + '</span>'
      + '<span><span class="k">&#8593;</span>'
      + '<span class="k">&#8595;</span> ' + CHROME.keys_browse + '</span>'
      + '<span><span class="k">1-9</span> ' + CHROME.keys_pick + '</span>'
      + '<span><span class="k">Enter</span> ' + CHROME.keys_confirm + '</span>';
  }
}
function show(k) {
  cancelAdvance();  // a stale timer must never fire on the new card
  cur = Math.max(0, Math.min(k, total));
  cards.forEach(function (c, i) { c.classList.toggle('active', i === cur); });
  review.classList.toggle('active', cur === total);
  if (cur === total) { renderReview(); }
  updateProgress();
  updateKeysbar();
  updateNav();
  updateKpis();
  if (cur < total) {
    const act = cards[cur];
    act.style.animation = 'none';
    void act.offsetWidth;  // restart the card-enter animation
    act.style.animation = '';
  }
  if (cur < total) {
    cards[cur].querySelectorAll('img[data-shot]').forEach(placeBoxes);
  }
  const act = cur < total ? cards[cur] : review;
  if (act) {
    act.tabIndex = -1;
    act.focus({ preventScroll: true });
  }
  window.scrollTo({ top: 0, behavior: motionOK() ? 'smooth' : 'auto' });
}
function advanceTarget(i) {
  // console-confirmed round 7: advance to the next UNDECIDED card; when
  // every card is decided, go straight to the review panel
  for (let k = i; k < total; k += 1) {
    if (!answered(k)) { return k; }
  }
  return total;
}
function scheduleAdvance() {
  cancelAdvance();
  const target = advanceTarget(cur);  // captured at schedule time
  advTimer = setTimeout(function () { advTimer = null; show(target); }, 650);
}
cards.forEach(function (card, i) {
  card.addEventListener('change', function (ev) {
    if (!ev.target.matches('input[type="radio"]')) { return; }
    const wasSuppressed = suppressAdvanceOnce;
    suppressAdvanceOnce = false;
    card.classList.add('decided');
    updateProgress();
    syncSaveBadges(i);
    if (ev.target.hasAttribute('data-own')) {
      const own = document.getElementById('own' + i);
      if (own) {
        own.focus({ preventScroll: true });
        own.scrollIntoView({ block: 'center',
                             behavior: motionOK() ? 'smooth' : 'auto' });
      }
      return;  // picking the write-in never auto-advances
    }
    if (i === cur && !wasSuppressed) { scheduleAdvance(); }
  });
  card.addEventListener('pointerdown', cancelAdvance);
  card.querySelectorAll('.cnav').forEach(function (btn) {
    btn.addEventListener('click', function () {
      // in-bar arrows: left = previous card, right = next or review
      show(btn.dataset.cnav === 'prev' ? i - 1 : i + 1);
    });
  });
  card.addEventListener('paste', function (ev) {
    // A pasted screenshot travels with the write-in answer; plain text
    // paste keeps its default behaviour inside the text input.
    const items = ev.clipboardData && ev.clipboardData.items;
    if (!items) { return; }
    let grabbed = false;
    for (const it of items) {
      if (it.kind === 'file' && /^image\\//.test(it.type)) {
        addPasteImage(i, it.getAsFile());
        grabbed = true;
      }
    }
    if (grabbed) { ev.preventDefault(); }
  });
  const zone = card.querySelector('.pastezone');
  const pastefile = card.querySelector('.pastefile');
  if (zone && pastefile) {
    zone.addEventListener('click', function () { pastefile.click(); });
    zone.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); pastefile.click(); }
    });
    zone.addEventListener('dragover', function (ev) { ev.preventDefault(); });
    zone.addEventListener('drop', function (ev) {
      ev.preventDefault();
      const files = ev.dataTransfer && ev.dataTransfer.files;
      if (!files) { return; }
      for (const f of files) { addPasteImage(i, f); }
    });
    pastefile.addEventListener('change', function () {
      for (const f of pastefile.files) { addPasteImage(i, f); }
      pastefile.value = '';
    });
  }
  const nb = card.querySelector('.nextbtn');
  if (nb) { nb.addEventListener('click', function () { show(advanceTarget(i)); }); }
  const own = document.getElementById('own' + i);
  if (own) {
    own.addEventListener('focus', cancelAdvance);
    own.addEventListener('input', function () {
      cancelAdvance();  // typing an own answer must not slide the card away
      const radio = card.querySelector('input[data-own]');
      if (radio && !radio.checked) {
        radio.checked = true;
        card.classList.add('decided');
      }
      updateProgress();  // keeps the alignment row in sync while typing
      if (own.tagName === 'TEXTAREA') {
        own.style.height = 'auto';  // grow with the answer, never scroll
        own.style.height = own.scrollHeight + 'px';
      }
    });
  }
});
// Spec "boxes" overlay: place each red box over the capture once the image
// has layout (hidden cards have no clientWidth, so show() re-places them).
function placeBoxes(img) {
  const wrap = img.parentElement;
  if (!wrap || !wrap.classList || !wrap.classList.contains('shotwrap')) { return; }
  if (!img.naturalWidth || !img.clientWidth) { return; }
  const scale = img.clientWidth / img.naturalWidth;
  const iw = img.clientWidth, ih = img.clientHeight;
  // The overlay coordinate origin is the capture's content box (the img
  // carries its own margin and border inside the wrap), never the wrap.
  const ox = img.offsetLeft + img.clientLeft;
  const oy = img.offsetTop + img.clientTop;
  // The frame sits a little OUTSIDE the marked region so its border and
  // badge never cover the content it marks; every overlay piece is clamped
  // back inside the capture so nothing dangles over the edge.
  const PAD = 8;
  wrap.querySelectorAll('.shotbox').forEach(function (b) {
    const x = Number(b.dataset.x) * scale;
    const y = Number(b.dataset.y) * scale;
    const w = Number(b.dataset.w) * scale;
    const h = Number(b.dataset.h) * scale;
    const l = Math.max(0, Math.min(x - PAD, iw - 4));
    const t = Math.max(0, Math.min(y - PAD, ih - 4));
    const r = Math.min(iw, x + w + PAD);
    const bo = Math.min(ih, y + h + PAD);
    b.style.left = (l + ox) + 'px';
    b.style.top = (t + oy) + 'px';
    b.style.width = Math.max(4, r - l) + 'px';
    b.style.height = Math.max(4, bo - t) + 'px';
    const num = b.querySelector('.shotnum');
    if (num) {
      num.style.left = ((l < 16) ? (4 - l) : -12) + 'px';
      num.style.top = ((t < 16) ? (4 - t) : -12) + 'px';
    }
    const lab = b.querySelector('.shotlabel');
    if (lab) {
      const lw = lab.offsetWidth, lh = lab.offsetHeight;
      const lx = Math.max(4, Math.min(l, iw - lw - 4)) - l;
      let ly = (bo - t) + 5;                  // prefer the label below
      if (bo + 5 + lh > ih) { ly = (t - 5 - lh >= 0) ? -5 - lh : 4; }
      lab.style.left = lx + 'px';
      lab.style.top = ly + 'px';
    }
  });
}
document.querySelectorAll('img[data-shot]').forEach(function (img) {
  if (img.complete && img.naturalWidth) { placeBoxes(img); }
  else { img.addEventListener('load', function () { placeBoxes(img); }); }
});
window.addEventListener('resize', function () {
  document.querySelectorAll('img[data-shot]').forEach(placeBoxes);
});
document.addEventListener('click', function (ev) {
  const img = ev.target.closest ? ev.target.closest('img[data-zoom]') : null;
  if (!img) { return; }
  cancelAdvance();  // studying the diagram must not race the auto-advance
  const lb = document.createElement('div');
  lb.className = 'lightbox';
  lb.setAttribute('role', 'dialog');
  lb.setAttribute('aria-label', CHROME.lightbox_aria);
  const big = document.createElement('img');
  big.src = img.src;
  big.alt = img.alt;
  lb.appendChild(big);
  lb.addEventListener('click', function () {
    document.body.removeChild(lb);
  });
  document.body.appendChild(lb);
});
function renderReview() {
  const box = document.getElementById('reviewrows');
  box.innerHTML = '';
  for (let i = 0; i < total; i += 1) {
    const sel = document.querySelector('input[name="q' + i + '"]:checked');
    const note = document.getElementById('note' + i);
    const row = document.createElement('div');
    row.className = 'rrow' + (sel ? '' : ' rmiss');
    const q = document.createElement('span');
    q.className = 'qid';
    q.textContent = QIDS[i];
    row.appendChild(q);
    const main = document.createElement('span');
    main.className = 'rmain';
    const t = document.createElement('b');
    t.textContent = QTITLES[i];
    main.appendChild(t);
    const label = document.createElement('span');
    label.className = 'rchoice';
    let chosen = null;
    if (sel && sel.hasAttribute('data-own')) {
      const ownEl = document.getElementById('own' + i);
      chosen = ownEl ? ownEl.value.trim() : '';
      if (!chosen && cardImages[i].length > 0) {
        chosen = '(image answer)';
      }
      if (!chosen) { chosen = CHROME.own_missing; }
    } else if (sel) {
      chosen = sel.value;
    }
    label.textContent = chosen || CHROME.not_decided;
    main.appendChild(label);
    if (cardImages[i].length > 0) {
      const n = cardImages[i].length;
      const im = document.createElement('span');
      im.className = 'rnote';
      im.textContent = CHROME.fmt_attached.replace('%d', n);
      main.appendChild(im);
    }
    if (note && note.value) {
      const n = document.createElement('span');
      n.className = 'rnote';
      n.textContent = note.value;
      n.title = note.value;
      main.appendChild(n);
    }
    row.appendChild(main);
    const edit = document.createElement('button');
    edit.type = 'button';
    edit.className = 'rlink';
    edit.innerHTML = PENCIL + CHROME.edit;
    edit.addEventListener('click', function () { show(i); });
    row.appendChild(edit);
    box.appendChild(row);
  }
}
document.addEventListener('keydown', function (ev) {
  if (ev.target && ev.target.tagName === 'TEXTAREA') {
    // The write-in textarea: Enter confirms the card and advances (never
    // an implicit form submit, never a newline); Shift+Enter breaks the
    // line for longer custom answers.
    if (ev.target.classList.contains('owntext')
        && ev.key === 'Enter' && !ev.shiftKey) {
      ev.preventDefault();
      const card = ev.target.closest('.qcard');
      const i = cards.indexOf(card);
      if (i > -1) {
        card.classList.add('decided');
        updateProgress();
        show(advanceTarget(i));
      }
    }
    return;
  }
  if (ev.target && ev.target.tagName === 'INPUT'
      && ev.target.type === 'text') {
    // Enter inside the write-in input must never trigger the browser's
    // implicit form submit: it confirms the card and advances instead.
    if (ev.key === 'Enter') {
      ev.preventDefault();
      const card = ev.target.closest('.qcard');
      const i = cards.indexOf(card);
      if (i > -1) {
        card.classList.add('decided');
        updateProgress();
        show(advanceTarget(i));
      }
    }
    return;
  }
  const lb = document.querySelector('.lightbox');
  if (lb) {
    // the overlay owns the keyboard: Escape closes it, everything else inert
    if (ev.key === 'Escape') { lb.click(); }
    return;
  }
  if (ev.key === 'ArrowRight') {
    ev.preventDefault();
    if (cur < total) {
      if (answered(cur)) { show(cur + 1); }
      else { nudge(CHROME.decide_first); }
    }
  } else if (ev.key === 'ArrowLeft') {
    ev.preventDefault();
    show(cur - 1);
  } else if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
    if (cur >= total) { return; }
    ev.preventDefault();
    const opts = Array.from(cards[cur].querySelectorAll('input[type="radio"]'));
    if (!opts.length) { return; }
    const at = opts.indexOf(document.activeElement);
    let next;
    if (ev.key === 'ArrowDown') {
      next = at < 0 ? 0 : Math.min(at + 1, opts.length - 1);
    } else {
      next = at < 0 ? opts.length - 1 : Math.max(at - 1, 0);
    }
    opts[next].focus();
  } else if (ev.key === 'Enter') {
    if (document.activeElement && document.activeElement.tagName === 'BUTTON') {
      return;  // let the native click happen
    }
    if (cur < total) {
      const focused = document.activeElement;
      if (focused && focused.type === 'radio' && cards[cur].contains(focused)) {
        ev.preventDefault();
        focused.checked = true;
        focused.dispatchEvent(new Event('change', { bubbles: true }));
      }
    } else {
      ev.preventDefault();
      if (form.requestSubmit) { form.requestSubmit(); } else { form.submit(); }
    }
  } else if (/^[1-9]$/.test(ev.key)) {
    if (cur >= total) { return; }
    const opts = cards[cur].querySelectorAll('input[type="radio"]');
    const k = parseInt(ev.key, 10) - 1;
    if (k < opts.length) {
      ev.preventDefault();
      opts[k].checked = true;
      opts[k].dispatchEvent(new Event('change', { bubbles: true }));
    }
  }
});
const navprev = null;  // edge arrows removed: navigation lives in each
const navnext = null;  // card's cbar and in the KPI cards
function updateNav() {
  cards.forEach(function (card, i) {
    card.querySelectorAll('.cnav').forEach(function (btn) {
      btn.disabled = (btn.dataset.cnav === 'prev' && i === 0)
                  || (btn.dataset.cnav === 'next' && i >= total);
    });
  });
}
function updateKpis() {
  let done = 0;
  for (let i = 0; i < total; i += 1) { if (answered(i)) { done += 1; } }
  const set = function (id, v) {
    const el = document.getElementById(id);
    if (el) { el.querySelector('b').textContent = String(v); }
  };
  set('kpi-total', total);
  set('kpi-decided', done);
  set('kpi-pend', total - done);
}
['total', 'decided', 'pend'].forEach(function (kind) {
  const el = document.getElementById('kpi-' + kind);
  if (el) {
    el.addEventListener('click', function () {
      // Jump to the first card of that kind: total -> card 1, decided ->
      // first decided, pending -> first pending (review if none).
      if (kind === 'total') { show(0); return; }
      for (let i = 0; i < total; i += 1) {
        if ((kind === 'decided') === answered(i)) { show(i); return; }
      }
      show(total);
    });
  }
});
show(0);  // open on the first card
// Saved annotator captures, keyed by card index: {o, image, notes}.
// The capture replaces that option's evidence image; the capture and the
// notes ride the submitted answer (images + note fields).
const optCaptures = {};
const protoReqs = {};  // card index -> option index flagged for a prototype
// The amber badge beside the picked option: the save lands on this card
// (no auto-advance), and the badge is the explicit way forward. It lives
// only on the option that currently carries the saved capture.
function syncSaveBadges(i) {
  var card = cards[i];
  if (!card) { return; }
  card.querySelectorAll('.savebadge').forEach(function (b) { b.remove(); });
  var cap = optCaptures[i];
  if (!cap) { return; }
  var radios = card.querySelectorAll('input[type="radio"]');
  var sel = radios[cap.o];
  if (!sel || !sel.checked) { return; }
  var label = sel.closest('label.opt');
  var title = label ? label.querySelector('.otitle') : null;
  if (!title) { return; }
  var badge = document.createElement('button');
  badge.type = 'button';
  badge.className = 'savebadge';
  var next = advanceTarget(i) === total
    ? CHROME.badge_review : CHROME.badge_next_card;
  if (cap.proto) {
    // A prototype request lands like a save: same badge shape, its own
    // message - the option asked for a generated prototype.
    badge.innerHTML = ICONS.circle_check + '<b>' + CHROME.proto_badge
      + '</b>';
  } else {
    badge.innerHTML = ICONS.circle_check + '<b>' + CHROME.saved_badge
      + '</b>' + '<span aria-hidden="true">&middot;</span>' + next;
  }
  badge.addEventListener('click', function (ev) {
    ev.preventDefault();
    ev.stopPropagation();  // the badge is a button inside the option label
    show(advanceTarget(i));
  });
  title.appendChild(badge);
}
window.addEventListener('message', function (ev) {
  // An annotate page opened from an option sends its saved capture back:
  // return to that card, swap the option's evidence for the annotated
  // capture (the old red evidence boxes go with it), pick that option
  // WITHOUT auto-advancing (the amber badge beside it is the way
  // forward), and hold the capture + notes for the submit.
  var save = ev.data && ev.data.grillSave;
  if (!save || typeof save.q !== 'number' || typeof save.o !== 'number') {
    return;
  }
  optCaptures[save.q] = save;
  if (save.proto) { protoReqs[save.q] = save.o; }
  var card = cards[save.q];
  var label = card ? card.querySelectorAll('label.opt')[save.o] : null;
  if (card) { show(save.q); }  // the save lands where the question lives
  if (label) {
    if (save.proto && !label.querySelector('.protochip')) {
      var chip = document.createElement('span');
      chip.className = 'protochip';
      chip.textContent = CHROME.proto_requested;
      label.appendChild(chip);
    }
    var im = label.querySelector('img[data-shot]');
    if (im && save.image) {
      im.src = save.image;
      var wrap = im.parentElement;
      if (wrap) {
        wrap.querySelectorAll('.shotbox').forEach(function (b) { b.remove(); });
      }
    }
    var radio = label.querySelector('input[type="radio"]');
    if (radio && !radio.checked) {
      suppressAdvanceOnce = true;
      radio.checked = true;
      radio.dispatchEvent(new Event('change', { bubbles: true }));
    } else {
      syncSaveBadges(save.q);
    }
  }
});
const cardImages = QIDS.map(function () { return []; });
function addPasteImage(i, file) {
  if (!file || !/^image\\//.test(file.type)) {
    fail(CHROME.paste_image_err);
    return;
  }
  if (file.size > 8 * 1024 * 1024) {
    fail(CHROME.fmt_img_too_large.replace('%s', file.name));
    return;
  }
  if (cardImages[i].length >= 4) {
    fail(CHROME.img_limit);
    return;
  }
  const reader = new FileReader();
  reader.onload = function () {
    cardImages[i].push({ name: file.name || 'pasted image',
                         data: reader.result });
    renderPasteList(i);
    // A pasted screenshot is almost always a custom answer: pick the
    // write-in option for the user.
    const ownRadio = document.querySelector(
      'input[name="q' + i + '"][data-own]');
    if (ownRadio && !ownRadio.checked) {
      ownRadio.checked = true;
      ownRadio.dispatchEvent(new Event('change', { bubbles: true }));
    }
  };
  reader.readAsDataURL(file);
}
function renderPasteList(i) {
  const host = document.getElementById('pastelist' + i);
  if (!host) { return; }
  host.innerHTML = '';
  cardImages[i].forEach(function (im, k) {
    const chip = document.createElement('span');
    chip.className = 'pastechip';
    const img = document.createElement('img');
    img.src = im.data;
    img.alt = im.name;
    const x = document.createElement('button');
    x.type = 'button';
    x.className = 'pastex';
    x.textContent = '\\u00d7';
    x.setAttribute('aria-label', CHROME.fmt_remove_img.replace('%s', im.name));
    x.addEventListener('click', function () {
      cardImages[i].splice(k, 1);
      renderPasteList(i);
    });
    chip.appendChild(img);
    chip.appendChild(x);
    host.appendChild(chip);
  });
}
function onSubmit(ev) {
  errbox.classList.add('hidden');
  const answers = [];
  const missing = [];
  const now = Date.now();
  const emptyOwn = [];
  for (let i = 0; i < QIDS.length; i += 1) {
    const sel = document.querySelector('input[name="q' + i + '"]:checked');
    if (!sel) { missing.push(QIDS[i]); continue; }
    const noteEl = document.getElementById('note' + i);
    let choice = sel.value;
    let custom = false;
    if (sel.hasAttribute('data-own')) {
      const ownEl = document.getElementById('own' + i);
      choice = ownEl ? ownEl.value.trim() : '';
      custom = true;
      if (!choice && cardImages[i].length > 0) {
        choice = '(image answer)';  // a pasted screenshot alone is a valid answer
      }
      if (!choice) { emptyOwn.push(QIDS[i]); continue; }
    }
    const entry = { qid: QIDS[i], choice: choice,
                    note: noteEl ? noteEl.value : '', ts: now };
    if (custom) { entry.custom = true; }
    if (cardImages[i].length > 0) { entry.images = cardImages[i]; }
    const radios = document.querySelectorAll('input[name="q' + i + '"]');
    const cap = optCaptures[i];
    // A saved annotator capture rides the answer when its option is the
    // chosen one: the capture takes priority over pasted images, capped
    // at the schema's 4-image limit.
    if (cap && !custom && radios[cap.o] === sel) {
      if (cap.notes && cap.notes.length) {
        entry.note = cap.notes.join('; ');
      }
      if (cap.image) {
        entry.images = [{ name: 'annotated-capture.png', data: cap.image }]
          .concat(entry.images || []).slice(0, 4);
      }
    }
    // A prototype request rides the answer of the option it was asked
    // for: the agent answers with a generated prototype round.
    if (protoReqs[i] !== undefined && radios[protoReqs[i]] === sel) {
      entry.prototypeRequest = true;
    }
    answers.push(entry);
  }
  if (emptyOwn.length > 0) {
    // Jump to the offending card and focus its write-in input, so "you did
    // not write it" can only mean one visible field.
    const i = QIDS.indexOf(emptyOwn[0]);
    if (i > -1) {
      show(i);
      const ownEl = document.getElementById('own' + i);
      if (ownEl) {
        ownEl.focus({ preventScroll: true });
        ownEl.scrollIntoView({ block: 'center' });
      }
    }
    fail(CHROME.fmt_write_missing.replace('%s', emptyOwn.join(', ')));
    ev.preventDefault();
    return;
  }
  if (missing.length > 0) {
    const j = QIDS.indexOf(missing[0]);
    if (j > -1) { show(j); }
    fail(CHROME.fmt_answer_missing.replace('%s', missing.join(', ')));
    ev.preventDefault();
    return;
  }
  document.getElementById('payload').value = JSON.stringify(answers);
  // native form POST continues; the server replies with the
  // "Submitted successfully" page that counts down and closes the tab
}
"""

# JS for the single-card legacy page (--options): same round-trip, one entry.
_JS_SINGLE = """
const form = document.getElementById('panel');
const errbox = document.getElementById('errorbox');
form.addEventListener('submit', onSubmit);
function fail(msg) {
  errbox.textContent = msg;
  errbox.classList.remove('hidden');
}
function onSubmit(ev) {
  errbox.classList.add('hidden');
  const sel = document.querySelector('input[name="choice"]:checked');
  if (!sel) { fail(CHROME.select_first); ev.preventDefault(); return; }
  document.getElementById('payload').value = JSON.stringify(
    [{ qid: QID, choice: sel.value,
       note: document.getElementById('note').value, ts: Date.now() }]);
  // native form POST continues; the server replies with the confirmation page
}
"""

# Annotation overlay injected into /static HTML pages served with
# ?annotate=1: the user draws amber boxes on the live artifact, numbering
# and captions are automatic, and "Send annotations" POSTs the boxes to
# the console server, which saves them beside the answers file. Amber
# marks the user; the console's evidence boxes are red - never confounded.
# Chrome copy (buttons, toasts, alerts) follows the page language through
# the %(...)s substitution in _serve_static.
_ANNOTATOR_ASSET = """
<style>
#grill-ann-toolbar { position: fixed; right: 16px; bottom: 16px; z-index: 2147483000;
  display: flex; align-items: center; gap: 10px; background: #fff;
  border: 1px solid #e5e7eb; border-radius: 12px; padding: 10px 14px;
  box-shadow: 0 8px 30px rgba(15,23,42,.18); font: 13px/1.4 system-ui, sans-serif; }
#grill-ann-toolbar button { border: 0; border-radius: 8px; padding: 8px 14px;
  font: inherit; font-weight: 700; cursor: pointer; }
/* The top tools bar buttons follow the console's button family: the icon
   rides the m size class (15px), the button is a compact square, the real
   disabled state dims, and keyboard focus stays visible. */
#grill-ann-toolbar-top button { border: 0; border-radius: 8px; padding: 0;
  width: 32px; height: 32px; display: inline-flex; align-items: center;
  justify-content: center; font: inherit; cursor: pointer; }
#grill-ann-toolbar-top button:disabled { opacity: .35; cursor: default; }
#grill-ann-toolbar button:focus-visible,
#grill-ann-toolbar-top button:focus-visible { outline: 2px solid #6366f1;
  outline-offset: 1px; }
#grill-ann-toggle.off { background: #e5e7eb; color: #374151; }
#grill-ann-toggle { background: #f59e0b; color: #fff; }
#grill-ann-send { background: #111827; color: #fff; }
#grill-ann-return { background: #e5e7eb; color: #374151; }
#grill-ann-return:hover { background: #d1d5db; }
#grill-ann-count { color: #6b7280; }
body.grill-ann-on { cursor: crosshair; user-select: none; }
.grill-ann-box { position: absolute; border: 2px dashed #b45309;
  border-radius: 6px; }
.grill-ann-num { position: absolute; width: 22px; height: 22px; border-radius: 50%%;
  background: #f59e0b; color: #fff; font: 700 12px/22px system-ui, sans-serif;
  text-align: center; top: -11px; left: -11px; pointer-events: none; }
.grill-ann-cap { position: absolute; top: 100%%; margin-top: 4px; left: 0;
  border: 1px solid #b45309; border-radius: 6px; padding: 3px 6px;
  font: 12px/1.5 system-ui, sans-serif; color: #7c2d12; background: #fffbeb;
  min-width: 140px; max-width: 480px; width: 260px;
  resize: both; overflow: auto; white-space: pre-wrap;
  box-sizing: border-box; }
.grill-ann-x { position: absolute; top: -11px; right: -11px; width: 20px; height: 20px;
  border-radius: 50%%; border: 1px solid #b45309; background: #fff; color: #b45309;
  font: 700 12px/18px system-ui, sans-serif; text-align: center; cursor: pointer; }
.tool-ic { width: 15px; height: 15px; display: block; fill: none;
  stroke: currentColor; stroke-width: 2; stroke-linecap: round;
  stroke-linejoin: round; }
/* The annotation tools live in their own bar at the top of the page,
   shown only while Annotate is on: idle pages keep the full canvas
   visible, and the tool buttons never cover page content. */
#grill-ann-toolbar-top { position: fixed; top: 16px; left: 50%%;
  transform: translateX(-50%%); z-index: 2147483000; display: none;
  align-items: center; gap: 10px; background: #fff;
  border: 1px solid #e5e7eb; border-radius: 12px; padding: 10px 14px;
  box-shadow: 0 8px 30px rgba(15,23,42,.18); font: 13px/1.4 system-ui, sans-serif; }
#grill-tool-group { display: inline-flex; gap: 6px; }
body.grill-ann-on #grill-ann-toolbar-top { display: flex; }
/* A drawn box carries a corner resize grip while Annotate is on:
   dragging the grip resizes the box in place. */
.grill-ann-grip { display: none; position: absolute; right: -6px;
  bottom: -6px; width: 12px; height: 12px; background: #f59e0b;
  border: 2px solid #fff; border-radius: 3px; cursor: nwse-resize; }
body.grill-ann-on .grill-ann-grip { display: block; }
.tool { background: #e5e7eb; color: #374151; }
.tool:hover { background: #d1d5db; }
.tool.on { background: #f59e0b; color: #fff; }
.grill-ann-arrow { position: absolute; overflow: visible;
  pointer-events: none; z-index: 2147482999; }
.grill-ann-arrow line.hit { pointer-events: stroke; }
.aihr { width: 1px; align-self: stretch; background: #e5e7eb; margin: 0 2px; }
#grill-ai-clear, #grill-ai-restore { background: #fee2e2; color: #b91c1c; }
#grill-ai-clear:hover, #grill-ai-restore:hover { background: #fecaca; }
.grill-ai-box { position: absolute; border: 3px solid #d92d20; border-radius: 10px;
  pointer-events: none; z-index: 2147482000; }
.grill-ai-num { position: absolute; top: -11px; left: -11px; min-width: 22px;
  height: 22px; border-radius: 50%%; background: #d92d20; color: #fff;
  font: 700 12px/22px system-ui, sans-serif; text-align: center; }
.grill-ai-label { position: absolute; top: 100%%; left: 0; margin-top: 4px;
  background: #d92d20; color: #fff; font: 700 12px system-ui, sans-serif;
  border-radius: 6px; padding: 2px 8px; white-space: nowrap; }
.grill-ai-x { position: absolute; top: -11px; right: -11px; width: 20px; height: 20px;
  border-radius: 50%%; border: 1px solid #d92d20; background: #fff; color: #d92d20;
  font: 700 12px/18px system-ui, sans-serif; text-align: center; cursor: pointer;
  pointer-events: auto; }
/* Visual kinds: the move arrow, the suggested icon, the color swatches.
   The mark data never reaches the user as a word or a bare code - the
   page draws the thing itself. */
.grill-ai-move { border: none; }
.grill-ai-move svg { position: absolute; overflow: visible; pointer-events: none; }
.grill-ai-icon { border: none; background: #fff; border-radius: 8px;
  box-shadow: 0 2px 10px rgba(15,23,42,.3); display: flex;
  align-items: center; justify-content: center; }
.grill-ai-icon svg { width: 68%%; height: 68%%; stroke: #d92d20; fill: none;
  stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
.grill-ai-color { border: none; background: #fff; border-radius: 8px;
  box-shadow: 0 2px 10px rgba(15,23,42,.3); display: flex;
  align-items: flex-start; gap: 4px; padding: 5px 7px 4px; }
.grill-ai-swcol { display: inline-flex; flex-direction: column;
  align-items: center; gap: 1px; }
.grill-ai-swatch { width: 20px; height: 20px; border-radius: 5px;
  border: 1px solid rgba(15,23,42,.3); }
.grill-ai-hex { color: #94a3b8; font: 400 10px/1.2 system-ui, sans-serif;
  max-width: 64px; overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap; }
.grill-ai-arrowmini { color: #475569; font: 700 13px/1 system-ui, sans-serif;
  align-self: flex-start; margin-top: 8px; }
#grill-ann-proto { background: #eef2ff; color: #4338ca; }
#grill-ann-proto:hover { background: #e0e7ff; }
/* The eraser must reach the AI marks: while it is the active tool the
   marks take the pointer, and the marks' x buttons keep their own path. */
.eraser-on .grill-ai-box { pointer-events: auto; cursor: crosshair; }
.eraser-on .grill-ai-move svg { pointer-events: stroke; }
</style>
<div id="grill-ann-toolbar-top">
  <span id="grill-tool-group">
    <button type="button" id="grill-tool-box" class="tool on" title="%(tool_box)s" aria-label="%(tool_box)s">%(tool_box_ic)s</button>
    <button type="button" id="grill-tool-arrow" class="tool" title="%(tool_arrow)s" aria-label="%(tool_arrow)s">%(tool_arrow_ic)s</button>
    <button type="button" id="grill-tool-eraser" class="tool" title="%(tool_eraser)s" aria-label="%(tool_eraser)s">%(tool_eraser_ic)s</button>
  </span>
  <span class="aihr"></span>
  <button type="button" id="grill-ann-undo" class="tool" title="%(undo_title)s" aria-label="%(undo_label)s">%(undo_ic)s</button>
  <button type="button" id="grill-ann-redo" class="tool" title="%(redo_title)s" aria-label="%(redo_label)s">%(redo_ic)s</button>
</div>
<div id="grill-ann-toolbar">
  <span id="grill-ai-group">
    <span id="grill-ai-count">%(ai_count_init)s</span>
    <button type="button" id="grill-ai-clear" title="%(ai_clear_t)s">%(ai_clear)s</button>
    <button type="button" id="grill-ai-restore" title="%(ai_restore_t)s">%(ai_restore)s</button>
  </span>
  <span class="aihr"></span>
  <span id="grill-ann-count">%(count_init)s</span>
  <button type="button" id="grill-ann-toggle" class="off" title="%(toggle_title)s">
    <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>
    %(toggle_label)s</button>
  <button type="button" id="grill-ann-save" title="%(save_title)s">
    <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/></svg>
    %(save_label)s</button>
  <button type="button" id="grill-ann-return" title="%(return_title)s">
    <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m12 19-7-7 7-7"/><path d="M19 12H5"/></svg>
    %(return_label)s</button>
  <button type="button" id="grill-ann-proto" title="%(proto_gen_title)s">
    <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m3 21 9-9"/><path d="M15 4V2"/><path d="M15 16v-2"/><path d="M8 9h2"/><path d="M20 9h2"/><path d="m17.8 11.8 1.2 1.2"/><path d="m17.8 6.2 1.2-1.2"/><path d="m12.2 6.2 1.2-1.2"/></svg>
    %(proto_gen)s</button>
</div>
<script>const ANN = %(ann)s;
const AI = %(ai_boxes)s;
var aiOriginal = (AI && AI.boxes) ? AI.boxes.slice() : [];
var aiBoxes = aiOriginal.slice();</script>
<script>
(function () {
  var on = false, boxes = [], arrows = [], drawing = null, seq = 0;
  var undoStack = [], redoStack = [];
  var AP = new URLSearchParams(location.search);
  var cardIdx = AP.get('q'), optIdx = AP.get('o');
  var toggle = document.getElementById('grill-ann-toggle');
  var undoBtn = document.getElementById('grill-ann-undo');
  var redoBtn = document.getElementById('grill-ann-redo');
  var saveBtn = document.getElementById('grill-ann-save');
  var returnBtn = document.getElementById('grill-ann-return');
  var count = document.getElementById('grill-ann-count');
  if (saveBtn && (cardIdx === null || optIdx === null)) {
    saveBtn.disabled = true;
    saveBtn.title = ANN.ann_unlinked;
  }
  if (returnBtn) {
    // The quiet exit: browsing without annotating still lands the user
    // back on the console - focus it, then close this script-opened tab.
    returnBtn.addEventListener('click', function () {
      try { if (window.opener) { window.opener.focus(); } } catch (e) {}
      try {
        var nm = window.opener && window.opener.name;
        if (nm) { window.open('', nm); }
      } catch (e) {}
      window.close();
    });
  }
  // AI evidence boxes: the option's spec boxes ride along as a red layer
  // (numbered + labelled), scaled to the page width. The user can erase
  // one (the box's x), clear them all, or restore the original set; the
  // remaining boxes are baked into the saved capture.
  var aiGroup = document.getElementById('grill-ai-group');
  var aiCount = document.getElementById('grill-ai-count');
  function aiBadge(el, i, label) {
    var num = document.createElement('span');
    num.className = 'grill-ai-num';
    num.textContent = String(i + 1);
    el.appendChild(num);
    if (label) {
      var lab = document.createElement('span');
      lab.className = 'grill-ai-label';
      lab.textContent = label;
      el.appendChild(lab);
    }
    var x = document.createElement('button');
    x.type = 'button';
    x.className = 'grill-ai-x';
    x.textContent = '\\u00d7';
    x.setAttribute('aria-label', ANN.ai_remove);
    x.addEventListener('click', function (ev) {
      ev.stopPropagation();
      aiBoxes.splice(i, 1);
      renderAi();
      refreshAi();
    });
    el.appendChild(x);
  }
  function renderAi() {
    document.querySelectorAll('.grill-ai-box').forEach(function (b) {
      b.remove();
    });
    var sc = window.innerWidth / ((AI && AI.captureWidth) || 1000);
    aiBoxes.forEach(function (b, i) {
      var kind = b.kind || 'box';
      if (kind === 'move') {
        // Positional suggestion as a picture: a dashed arrow from the
        // current spot to the target spot, badge on the "from" end,
        // caption riding the midpoint.
        var dx = (b.to.x - b.from.x) * sc;
        var dy = (b.to.y - b.from.y) * sc;
        var vx = Math.max(1, Math.abs(dx));
        var vy = Math.max(1, Math.abs(dy));
        var el = document.createElement('div');
        el.className = 'grill-ai-box grill-ai-move';
        el.setAttribute('data-idx', String(i));
        el.style.left = b.from.x * sc + 'px';
        el.style.top = b.from.y * sc + 'px';
        el.style.width = '0px';
        el.style.height = '0px';
        var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('width', String(vx));
        svg.setAttribute('height', String(vy));
        svg.setAttribute('viewBox',
          Math.min(0, dx) + ' ' + Math.min(0, dy) + ' ' + vx + ' ' + vy);
        svg.style.left = Math.min(0, dx) + 'px';
        svg.style.top = Math.min(0, dy) + 'px';
        var mid = 'grill-ai-arrow-' + i;
        var defs = document.createElementNS('http://www.w3.org/2000/svg',
                                            'defs');
        defs.innerHTML = '<marker id="' + mid + '" viewBox="0 0 10 10" '
          + 'refX="9" refY="5" markerWidth="7" markerHeight="7" '
          + 'orient="auto-start-reverse"><path d="M0 0 10 5 0 10z" '
          + 'fill="#d92d20"/></marker>';
        svg.appendChild(defs);
        var ln = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        ln.setAttribute('x1', '0');
        ln.setAttribute('y1', '0');
        ln.setAttribute('x2', String(dx));
        ln.setAttribute('y2', String(dy));
        ln.setAttribute('stroke', '#d92d20');
        ln.setAttribute('stroke-width', '2.5');
        ln.setAttribute('stroke-dasharray', '7 5');
        ln.setAttribute('marker-end', 'url(#' + mid + ')');
        svg.appendChild(ln);
        var dot = document.createElementNS('http://www.w3.org/2000/svg',
                                           'circle');
        dot.setAttribute('cx', '0');
        dot.setAttribute('cy', '0');
        dot.setAttribute('r', '4.5');
        dot.setAttribute('fill', '#fff');
        dot.setAttribute('stroke', '#d92d20');
        dot.setAttribute('stroke-width', '2');
        svg.appendChild(dot);
        el.appendChild(svg);
        if (b.label) {
          var ml = document.createElement('span');
          ml.className = 'grill-ai-label';
          ml.style.left = (dx / 2) + 'px';
          ml.style.top = (dy / 2) + 'px';
          ml.style.transform = 'translate(-50%%, -50%%)';
          ml.style.marginTop = '0';
          ml.textContent = b.label;
          el.appendChild(ml);
        }
        aiBadge(el, i, null);
        document.body.appendChild(el);
        return;
      }
      if (kind === 'icon') {
        // Icon suggestion as a picture: the suggested icon rendered as a
        // real element on a small card at the target spot.
        var el = document.createElement('div');
        el.className = 'grill-ai-box grill-ai-icon';
        el.setAttribute('data-idx', String(i));
        el.style.left = b.x * sc + 'px';
        el.style.top = b.y * sc + 'px';
        el.style.width = Math.max(28, b.w * sc) + 'px';
        el.style.height = Math.max(28, b.h * sc) + 'px';
        var ic = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        ic.setAttribute('viewBox', '0 0 24 24');
        ic.innerHTML = b.icon || '';
        el.appendChild(ic);
        aiBadge(el, i, b.label);
        document.body.appendChild(el);
        return;
      }
      if (kind === 'color') {
        // Color suggestion as a picture: the current and the suggested
        // swatch side by side, the hex line small and grey under each.
        function swcol(name) {
          var col = document.createElement('span');
          col.className = 'grill-ai-swcol';
          var sw = document.createElement('span');
          sw.className = 'grill-ai-swatch';
          sw.style.background = b[name] || 'transparent';
          var hx = document.createElement('span');
          hx.className = 'grill-ai-hex';
          hx.textContent = b[name] || '';
          col.appendChild(sw);
          col.appendChild(hx);
          return col;
        }
        var el = document.createElement('div');
        el.className = 'grill-ai-box grill-ai-color';
        el.setAttribute('data-idx', String(i));
        el.style.left = b.x * sc + 'px';
        el.style.top = b.y * sc + 'px';
        el.appendChild(swcol('current'));
        var ar = document.createElement('span');
        ar.className = 'grill-ai-arrowmini';
        ar.textContent = '\\u2192';
        el.appendChild(ar);
        el.appendChild(swcol('suggested'));
        aiBadge(el, i, b.label);
        document.body.appendChild(el);
        return;
      }
      var el = document.createElement('div');
      el.className = 'grill-ai-box';
      el.setAttribute('data-idx', String(i));
      el.style.left = b.x * sc + 'px';
      el.style.top = b.y * sc + 'px';
      el.style.width = b.w * sc + 'px';
      el.style.height = b.h * sc + 'px';
      aiBadge(el, i, b.label);
      document.body.appendChild(el);
    });
  }
  function refreshAi() {
    if (aiGroup) {
      aiGroup.style.display = aiOriginal.length ? '' : 'none';
    }
    if (aiCount) {
      aiCount.textContent = ANN.fmt_ai_count.replace('%%d', aiBoxes.length);
    }
  }
  var aiClearBtn = document.getElementById('grill-ai-clear');
  var aiRestoreBtn = document.getElementById('grill-ai-restore');
  if (aiClearBtn) {
    aiClearBtn.addEventListener('click', function () {
      aiBoxes = [];
      renderAi();
      refreshAi();
    });
  }
  if (aiRestoreBtn) {
    aiRestoreBtn.addEventListener('click', function () {
      aiBoxes = aiOriginal.slice();
      renderAi();
      refreshAi();
    });
  }
  window.addEventListener('resize', renderAi);
  renderAi();
  refreshAi();
  function refresh() {
    count.textContent = ANN.fmt_ann_count.replace('%%d', boxes.length);
    toggle.className = on ? '' : 'off';
    toggle.textContent = on ? ANN.ann_stop : ANN.ann_toggle;
    document.body.classList.toggle('grill-ann-on', on);
    if (undoBtn) { undoBtn.disabled = !undoStack.length; }
    if (redoBtn) { redoBtn.disabled = !redoStack.length; }
  }
  // Undo and redo over the structural annotation steps (add, erase,
  // resize): data-only snapshots, the marks redraw from state on restore.
  function snap() {
    return JSON.stringify({
      b: boxes.map(function (b) { return { x: b.x, y: b.y, w: b.w, h: b.h,
          n: b.n, caption: b.caption }; }),
      a: arrows.map(function (a) { return { sx: a.sx, sy: a.sy, x: a.x,
          y: a.y, n: a.n, caption: a.caption }; }),
      s: seq
    });
  }
  function snapshot() {
    undoStack.push(snap());
    if (undoStack.length > 100) { undoStack.shift(); }
    redoStack.length = 0;
    refresh();
  }
  function restore(json) {
    var st = JSON.parse(json);
    document.querySelectorAll('.grill-ann-box, .grill-ann-arrow, '
      + '.grill-ann-cap').forEach(function (el) { el.remove(); });
    boxes = st.b;
    arrows = st.a;
    seq = st.s;
    boxes.forEach(function (b) { draw(b); });
    arrows.forEach(function (a) { finishArrow(a); });
    refresh();
  }
  function undo() {
    if (!undoStack.length) { return; }
    redoStack.push(snap());
    restore(undoStack.pop());
  }
  function redo() {
    if (!redoStack.length) { return; }
    undoStack.push(snap());
    restore(redoStack.pop());
  }
  if (undoBtn) { undoBtn.addEventListener('click', undo); }
  if (redoBtn) { redoBtn.addEventListener('click', redo); }
  document.addEventListener('keydown', function (ev) {
    var t = ev.target;
    if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA'
              || t.isContentEditable)) { return; }
    if (!(ev.ctrlKey || ev.metaKey)) { return; }
    var k = (ev.key || '').toLowerCase();
    if (k === 'z' && !ev.shiftKey) { ev.preventDefault(); undo(); }
    else if (k === 'y' || (k === 'z' && ev.shiftKey)) {
      ev.preventDefault(); redo();
    }
  });
  function finishArrow(a) {
    // Final arrow: an absolutely positioned svg (line + head, plus a fat
    // invisible hit line for the eraser) and the caption at the tip.
    var x1 = a.sx, y1 = a.sy, x2 = a.x, y2 = a.y;
    var L = Math.max(20, Math.abs(x2 - x1) + 40, Math.abs(y2 - y1) + 40);
    var ox = Math.min(x1, x2) - 20, oy = Math.min(y1, y2) - 20;
    var NS = 'http://www.w3.org/2000/svg';
    var layer = document.createElementNS(NS, 'svg');
    layer.setAttribute('class', 'grill-ann-arrow');
    layer.setAttribute('data-seq', String(a.n));
    layer.setAttribute('style', 'left:' + ox + 'px;top:' + oy
        + 'px;width:' + L + 'px;height:' + L + 'px');
    var mk = 'ah' + a.n;
    layer.innerHTML = '<defs><marker id="' + mk + '" markerWidth="8" '
      + 'markerHeight="8" refX="6" refY="3" orient="auto">'
      + '<path d="M0,0 L6,3 L0,6 Z" fill="#f59e0b"/></marker></defs>'
      + '<line x1="' + (x1 - ox) + '" y1="' + (y1 - oy)
      + '" x2="' + (x2 - ox) + '" y2="' + (y2 - oy)
      + '" stroke="#f59e0b" stroke-width="3" stroke-linecap="round" '
      + 'marker-end="url(#' + mk + ')"/>'
      + '<line class="hit" x1="' + (x1 - ox) + '" y1="' + (y1 - oy)
      + '" x2="' + (x2 - ox) + '" y2="' + (y2 - oy)
      + '" stroke="rgba(0,0,0,0)" stroke-width="14"/>';
    document.body.appendChild(layer);
    var cap = document.createElement('textarea');
    cap.className = 'grill-ann-cap';
    cap.rows = 1;
    cap.setAttribute('data-seq', String(a.n));
    cap.style.left = x2 + 'px';
    cap.style.top = (y2 + 6) + 'px';
    cap.placeholder = ANN.fmt_ann_cap.replace('%%d', a.n);
    cap.value = a.caption || '';
    var grow = function () {
      cap.style.height = 'auto';
      cap.style.height = cap.scrollHeight + 'px';
    };
    cap.addEventListener('input', function () {
      a.caption = cap.value;
      grow();
    });
    cap.addEventListener('keydown', function (ev) {
      // Enter finishes the caption; it never submits anything.
      if (ev.key === 'Enter' && !ev.shiftKey) {
        ev.preventDefault();
        ev.stopPropagation();
        a.caption = cap.value;
        cap.blur();
      }
    });
    document.body.appendChild(cap);
    grow();
  }
  function draw(b) {
    var el = document.createElement('div');
    el.className = 'grill-ann-box';
    el.setAttribute('data-seq', String(b.n));
    el.style.left = b.x + 'px'; el.style.top = b.y + 'px';
    el.style.width = b.w + 'px'; el.style.height = b.h + 'px';
    var num = document.createElement('span');
    num.className = 'grill-ann-num'; num.textContent = String(b.n);
    el.appendChild(num);
    var cap = document.createElement('textarea');
    cap.className = 'grill-ann-cap';
    cap.rows = 1;
    cap.setAttribute('data-seq', String(b.n));
    cap.value = b.caption;
    cap.placeholder = ANN.fmt_ann_cap.replace('%%d', b.n);
    var grow = function () {
      // The note wraps and the box grows with the text - long notes stay
      // fully readable while typing.
      cap.style.height = 'auto';
      cap.style.height = cap.scrollHeight + 'px';
    };
    cap.addEventListener('input', function () {
      b.caption = cap.value;
      grow();
    });
    cap.addEventListener('keydown', function (ev) {
      // Enter finishes this annotation: store the caption and leave edit
      // mode - it never submits anything. Shift+Enter breaks the line.
      if (ev.key === 'Enter' && !ev.shiftKey) {
        ev.preventDefault();
        ev.stopPropagation();
        b.caption = cap.value;
        cap.blur();
      }
    });
    el.appendChild(cap);
    var x = document.createElement('button');
    x.className = 'grill-ann-x'; x.textContent = '\\u00d7';
    x.type = 'button';
    x.setAttribute('aria-label', ANN.fmt_ann_remove.replace('%%d', b.n));
    x.addEventListener('click', function (ev) {
      ev.stopPropagation();
      snapshot();
      boxes = boxes.filter(function (o) { return o !== b; });
      el.remove(); refresh();
    });
    el.appendChild(x);
    var grip = document.createElement('span');
    grip.className = 'grill-ann-grip';
    grip.addEventListener('mousedown', function (ev) {
      ev.stopPropagation();
      ev.preventDefault();
      snapshot();
      drawing = { kind: 'resize', b: b };
    });
    el.appendChild(grip);
    document.body.appendChild(el);
  }
  toggle.addEventListener('click', function () { on = !on; refresh(); });
  // Self-capture: serialize the whole page (toolbar hidden, caption texts
  // baked into the DOM as value attributes) into an SVG foreignObject and
  // raster it to a PNG dataURL. Self-contained pages capture cleanly; on
  // any failure the flow degrades to notes-only.
  function capturePage(cb) {
    var toolbar = document.getElementById('grill-ann-toolbar');
    var topbar = document.getElementById('grill-ann-toolbar-top');
    var prevVis = toolbar.style.visibility;
    var prevTop = topbar ? topbar.style.visibility : '';
    toolbar.style.visibility = 'hidden';
    if (topbar) { topbar.style.visibility = 'hidden'; }
    document.querySelectorAll('.grill-ann-cap').forEach(function (c) {
      c.textContent = c.value;  // a textarea's value lives in its text node
    });
    var restore = function () {
      toolbar.style.visibility = prevVis;
      if (topbar) { topbar.style.visibility = prevTop; }
    };
    try {
      var root = document.documentElement;
      var W = Math.max(root.scrollWidth, document.body.scrollWidth);
      var H = Math.max(root.scrollHeight, document.body.scrollHeight);
      var xhtml = new XMLSerializer().serializeToString(root);
      var svg = '<svg xmlns="http://www.w3.org/2000/svg" width="' + W
        + '" height="' + H + '"><foreignObject width="100%%" height="100%%">'
        + xhtml + '</foreignObject></svg>';
      var img = new Image();
      img.onload = function () {
        try {
          var cv = document.createElement('canvas');
          cv.width = W; cv.height = H;
          cv.getContext('2d').drawImage(img, 0, 0);
          restore();
          cb(cv.toDataURL('image/png'));
        } catch (e) { restore(); cb(null); }
      };
      img.onerror = function () { restore(); cb(null); };
      img.src = 'data:image/svg+xml;charset=utf-8,'
        + encodeURIComponent(svg);
    } catch (e) { restore(); cb(null); }
  }
  // Three tools: box (drag a frame), arrow (drag a line with a head),
  // eraser (click any user mark or AI mark to remove it).
  var tool = 'box';
  var toolBtns = { box: document.getElementById('grill-tool-box'),
                   arrow: document.getElementById('grill-tool-arrow'),
                   eraser: document.getElementById('grill-tool-eraser') };
  function setTool(name) {
    tool = name;
    document.body.classList.toggle('eraser-on', name === 'eraser');
    Object.keys(toolBtns).forEach(function (k) {
      if (toolBtns[k]) {
        toolBtns[k].className = 'tool' + (k === tool ? ' on' : '');
      }
    });
  }
  Object.keys(toolBtns).forEach(function (k) {
    if (toolBtns[k]) {
      toolBtns[k].addEventListener('click', function () { setTool(k); });
    }
  });
  function eraseAt(ev) {
    if (ev.target.closest('.grill-ai-x') || ev.target.closest('.grill-ann-x')) {
      return;  // the x buttons keep their own remove path
    }
    var um = ev.target.closest('.grill-ann-box');
    if (um) {
      var sn = Number(um.getAttribute('data-seq'));
      snapshot();
      boxes = boxes.filter(function (b) { return b.n !== sn; });
      var uc = document.querySelector(
        '.grill-ann-cap[data-seq="' + sn + '"]');
      if (uc) { uc.remove(); }
      um.remove();
      refresh();
      return;
    }
    var am = ev.target.closest('.grill-ann-arrow');
    if (am) {
      var an = Number(am.getAttribute('data-seq'));
      snapshot();
      arrows = arrows.filter(function (a) { return a.n !== an; });
      var ac = document.querySelector(
        '.grill-ann-cap[data-seq="' + an + '"]');
      if (ac) { ac.remove(); }
      am.remove();
      refresh();
      return;
    }
    var aim = ev.target.closest('.grill-ai-box');
    if (aim) {
      var idx = Number(aim.getAttribute('data-idx'));
      aiBoxes.splice(idx, 1);
      renderAi();
      refreshAi();
    }
  }
  document.addEventListener('mousedown', function (ev) {
    if (!on || ev.button !== 0
        || ev.target.closest('#grill-ann-toolbar')
        || ev.target.closest('#grill-ann-toolbar-top')) { return; }
    if (tool === 'eraser') {
      eraseAt(ev);
      return;
    }
    if (ev.target.closest('.grill-ann-box')
        || ev.target.closest('.grill-ann-arrow')
        || ev.target.closest('.grill-ai-box')) { return; }
    if (tool === 'arrow') {
      var layer = document.createElementNS(
        'http://www.w3.org/2000/svg', 'svg');
      layer.setAttribute('class', 'grill-ann-arrow');
      layer.style.left = '0'; layer.style.top = '0';
      layer.style.width = '40px'; layer.style.height = '40px';
      document.body.appendChild(layer);
      drawing = { kind: 'arrow', sx: ev.pageX, sy: ev.pageY,
                  x: ev.pageX, y: ev.pageY, el: layer };
      ev.preventDefault();
      return;
    }
    var el = document.createElement('div');
    el.className = 'grill-ann-box';
    document.body.appendChild(el);
    drawing = { kind: 'box', sx: ev.pageX, sy: ev.pageY, x: ev.pageX,
                y: ev.pageY, w: 0, h: 0, el: el };
    ev.preventDefault();
  });
  document.addEventListener('mousemove', function (ev) {
    if (!drawing) { return; }
    if (drawing.kind === 'resize') {
      var rb = drawing.b;
      rb.w = Math.max(8, ev.pageX - rb.x);
      rb.h = Math.max(8, ev.pageY - rb.y);
      var rel = document.querySelector(
        '.grill-ann-box[data-seq="' + rb.n + '"]');
      if (rel) {
        rel.style.width = rb.w + 'px';
        rel.style.height = rb.h + 'px';
      }
      return;
    }
    if (drawing.kind === 'arrow') {
      drawing.x = ev.pageX; drawing.y = ev.pageY;
      var x1 = drawing.sx, y1 = drawing.sy, x2 = drawing.x, y2 = drawing.y;
      var L = Math.max(20, Math.abs(x2 - x1) + 40,
                       Math.abs(y2 - y1) + 40);
      var ox = Math.min(x1, x2) - 20, oy = Math.min(y1, y2) - 20;
      drawing.el.setAttribute('style',
          'left:' + ox + 'px;top:' + oy + 'px;width:' + L + 'px;height:'
          + L + 'px');
      drawing.el.innerHTML = '<defs><marker id="ah' + '" markerWidth="8" '
        + 'markerHeight="8" refX="6" refY="3" orient="auto">'
        + '<path d="M0,0 L6,3 L0,6 Z" fill="#f59e0b"/></marker></defs>'
        + '<line x1="' + (x1 - ox) + '" y1="' + (y1 - oy)
        + '" x2="' + (x2 - ox) + '" y2="' + (y2 - oy)
        + '" stroke="#f59e0b" stroke-width="3" stroke-linecap="round" '
        + 'marker-end="url(#ah)"/>';
      return;
    }
    var b = drawing;
    b.x = Math.min(b.sx, ev.pageX); b.y = Math.min(b.sy, ev.pageY);
    b.w = Math.abs(ev.pageX - b.sx); b.h = Math.abs(ev.pageY - b.sy);
    b.el.style.left = b.x + 'px'; b.el.style.top = b.y + 'px';
    b.el.style.width = b.w + 'px'; b.el.style.height = b.h + 'px';
  });
  document.addEventListener('mouseup', function () {
    if (!drawing) { return; }
    if (drawing.kind === 'resize') {
      drawing = null;  // the pre-resize state was snapshotted at grip mousedown
      refresh();
      return;
    }
    if (drawing.kind === 'arrow') {
      var a = drawing; drawing = null;
      if (Math.abs(a.x - a.sx) > 12 || Math.abs(a.y - a.sy) > 12) {
        snapshot();
        seq += 1; a.n = seq; a.caption = '';
        a.el.remove();  // the preview layer goes; the final arrow takes over
        finishArrow(a);
        arrows.push(a);
        refresh();
      } else { a.el.remove(); }
      return;
    }
    var b = drawing; drawing = null;
    if (b.w > 8 && b.h > 8) {
      snapshot();
      seq += 1; b.n = seq; b.caption = '';
      b.el.remove();
      draw(b); boxes.push(b); refresh();
    } else { b.el.remove(); }
  });
  saveBtn.addEventListener('click', function () {
    if (!boxes.length && !arrows.length) {
      window.alert(ANN.ann_draw_first);
      return;
    }
    if (cardIdx === null || optIdx === null || !window.opener) {
      window.alert(ANN.ann_open_first);
      return;
    }
    var notes = boxes.concat(arrows)
      .filter(function (b) { return (b.caption || '').trim(); })
      .map(function (b) { return b.n + ': ' + b.caption.trim(); });
    capturePage(function (dataUrl) {
      // Swap the option's evidence in the console tab, pick that option,
      // and attach the capture + notes so they ride the submitted answer.
      window.opener.postMessage(
        { grillSave: { q: parseInt(cardIdx, 10), o: parseInt(optIdx, 10),
                       image: dataUrl || '', notes: notes } },
        '*');
      // Return to the console tab: focus it by its window name (a plain
      // cross-tab focus() is ignored by the browser), then close this
      // annotate tab so the user lands back on the console badge.
      try {
        window.opener.focus();
        var nm = window.opener.name;
        if (nm) { window.open('', nm); }
      } catch (e) {}
      setTimeout(function () { window.close(); }, 300);
      // Server-side record (boxes + captions) beside the answers file.
      fetch('/annotations', { method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: location.pathname,
                               title: document.title,
                               boxes: boxes.map(function (b) {
          return { n: b.n, x: b.x, y: b.y, w: b.w, h: b.h,
                   caption: b.caption };
        }) }) }).catch(function (e) {
        window.alert(ANN.fmt_ann_save_fail.replace('%%s', e.message));
      });
      if (!dataUrl) { window.alert(ANN.ann_capture_fail); }
    });
  });
  // Generate prototype: the user cannot say the change in words. The
  // marks saved so far ride along (zero marks is fine - "I cannot say
  // it" needs no annotation), the option is flagged, and the console
  // shows the chip; the agent answers with a generated prototype round.
  var protoBtn = document.getElementById('grill-ann-proto');
  if (protoBtn) {
    protoBtn.addEventListener('click', function () {
      if (cardIdx === null || optIdx === null || !window.opener) {
        window.alert(ANN.ann_open_first);
        return;
      }
      var notes = boxes.concat(arrows)
        .filter(function (b) { return (b.caption || '').trim(); })
        .map(function (b) { return b.n + ': ' + b.caption.trim(); });
      capturePage(function (dataUrl) {
        window.opener.postMessage(
          { grillSave: { q: parseInt(cardIdx, 10), o: parseInt(optIdx, 10),
                         image: dataUrl || '', notes: notes,
                         proto: true } },
          '*');
        try {
          window.opener.focus();
          var nm = window.opener.name;
          if (nm) { window.open('', nm); }
        } catch (e) {}
        setTimeout(function () { window.close(); }, 300);
        fetch('/annotations', { method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: location.pathname,
                                 title: document.title,
                                 proto: true,
                                 boxes: boxes.map(function (b) {
            return { n: b.n, x: b.x, y: b.y, w: b.w, h: b.h,
                     caption: b.caption };
          }) }) }).catch(function (e) {
          window.alert(ANN.fmt_ann_save_fail.replace('%%s', e.message));
        });
        if (!dataUrl) { window.alert(ANN.ann_capture_fail); }
      });
    });
  }
})();
</script>
"""

_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%(title)s</title>
<style>%(css)s</style>
</head>
<body>
<header><h1>%(title)s</h1><p>%(subtitle)s</p></header>
<main>
<form id="panel" method="post" action="/answer">
<section>
<h2>%(options_head)s</h2>
%(radios)s
</section>
<section>
<h2>%(note_head)s</h2>
<textarea id="note" rows="4" placeholder="%(note_placeholder)s"></textarea>
</section>
%(links)s
<section class="actions">
<button id="submit" type="submit">%(submit)s</button>
<span class="hint">%(submit_hint)s</span>
</section>
<input type="hidden" name="payload" id="payload">
<div id="errorbox" class="errbox hidden"></div>
</form>
</main>
<script>const QID = %(qid)s;
const CHROME = %(chrome)s;</script>
<script>
%(js)s
</script>
</body>
</html>
"""

_SPEC_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="%(lang)s">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%(title)s</title>
<style>%(css)s</style>
</head>
<body class="stepper">
<header><h1>%(title)s</h1><p>%(subtitle)s</p>
<div class="pbar" id="pbar"></div>
<div class="pcount" id="pcount"></div>
<div id="live" aria-live="polite"></div>
</header>
<main>
%(alignment)s
<div id="errorbox" class="errbox hidden"></div>
<form id="panel" method="post" action="/answer">
<div class="kpirow" id="kpirow">
  <button type="button" class="kpi" data-kpi="total" id="kpi-total">
    <svg class="ic kic" viewBox="0 0 24 24" aria-hidden="true"><path d="m3 17 2 2 4-4"/><path d="m3 7 2 2 4-4"/><path d="M13 6h8"/><path d="M13 12h8"/><path d="M13 18h8"/></svg>
    <small>%(kpi_cards)s</small><b>0</b></button>
  <button type="button" class="kpi" data-kpi="decided" id="kpi-decided">
    <svg class="ic kic" viewBox="0 0 24 24" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>
    <small>%(kpi_decided)s</small><b>0</b></button>
  <button type="button" class="kpi" data-kpi="pend" id="kpi-pend">
    <svg class="ic kic" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
    <small>%(kpi_pending)s</small><b>0</b></button>
</div>
<div class="stage">
%(cards)s
<section class="card qreview" id="reviewcard">
<header class="chead"><span class="ctype"><svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><rect width="8" height="4" x="8" y="2" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="m9 14 2 2 4-4"/></svg>%(review_head)s</span></header>
<div class="cbody">
<div id="reviewrows"></div>
<section class="actions">
<button id="submit" type="submit"><svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>%(submit)s</button>
<span class="hint">%(submit_hint)s</span>
</section>
</div>
</section>
</div>
<input type="hidden" name="payload" id="payload">
</form>
</main>
<footer class="keysbar" id="keysbar">%(keys_init)s</footer>
<script>const QIDS = %(qids)s;
const QTITLES = %(qtitles)s;
const PENCIL = %(pencil)s;
const CHROME = %(chrome)s;
const ICONS = %(icons)s;
window.name = 'grill-console';</script>
<script>
%(js)s
</script>
</body>
</html>
"""

# Success page returned by POST /answer. Shows "Submitted successfully",
# counts down 3 seconds (3 -> 2 -> 1) and then calls window.close(); if the
# browser blocks the scripted close, the fallback line stays visible.
_CONFIRM_TEMPLATE = """<!DOCTYPE html>
<html lang="%(lang_attr)s">
<head>
<meta charset="utf-8">
<title>%(title)s</title>
<style>
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { font-family: system-ui, "PingFang SC", "Microsoft YaHei", sans-serif;
       margin: 0; color: var(--text);
       background: linear-gradient(135deg, #f1faff, #eef3ff 60%%, #f8f4ff);
       display: flex; min-height: 100vh; align-items: center; justify-content: center; }
main { max-width: 480px; width: 100%%; padding: 24px; text-align: center; }
.confirm { border: 1px solid #bbf7d0; background: var(--okbg); color: var(--ink-ok);
           font-size: 18px; font-weight: 700; padding: 22px 18px;
           border-radius: 12px;
           box-shadow: 0 10px 36px rgba(56, 99, 179, .07); }
.written { color: var(--faint); font-size: 12px; margin: 14px 0 0;
           word-break: break-all; }
.count { color: var(--soft); font-size: 14px; margin: 10px 0 0; }
.fallback { color: #18181b; font-weight: 700; font-size: 15px; margin: 8px 0 0; }
.hidden { display: none; }
</style>
</head>
<body>
<main>
<div class="confirm">%(confirm)s</div>
<p class="written">%(fmt_saved)s</p>
<p id="count" class="count">%(closing)s</p>
<p id="fallback" class="fallback hidden">%(fallback)s</p>
</main>
<script>const CHROME = %(chrome)s;</script>
<script>
(function () {
  var countdown = 3;
  var label = document.getElementById('count');
  var fallback = document.getElementById('fallback');
  function showFallback() { fallback.classList.remove('hidden'); }
  function tick() {
    label.textContent = CHROME.fmt_confirm_countdown.replace('%%d', countdown);
    countdown -= 1;
    if (countdown >= 0) { setTimeout(tick, 1000); return; }
    window.close();
    setTimeout(showFallback, 300);
  }
  setTimeout(tick, 100);
  setTimeout(showFallback, 3000);
})();
</script>
</body>
</html>
"""

_ERROR_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="%(lang_attr)s">
<head>
<meta charset="utf-8">
<title>%(title)s</title>
<style>
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { font-family: system-ui, "PingFang SC", "Microsoft YaHei", sans-serif;
       margin: 0; color: var(--text);
       background: linear-gradient(135deg, #f1faff, #eef3ff 60%%, #f8f4ff); }
main { max-width: 640px; margin: 40px auto; padding: 0 16px; }
.errbox { border: 1px solid var(--line-err); background: var(--tint-err); color: var(--ink-err);
          font-weight: 700; font-size: 16px; padding: 18px 20px;
          border-radius: 12px;
          box-shadow: 0 10px 36px rgba(56, 99, 179, .07); }
.hint { color: var(--faint); font-size: 13px; margin-top: 12px; }
</style>
</head>
<body>
<main>
<div class="errbox">%(message)s</div>
<p class="hint">%(hint)s</p>
</main>
</body>
</html>
"""


def _render_confirm(target, lang='en'):
    chrome = _CHROME[_chrome_lang(lang)]
    return _CONFIRM_TEMPLATE % {
        'written': _esc(target),
        'lang_attr': _chrome_lang(lang),
        'title': chrome['confirm_title'],
        'confirm': chrome['confirm_title'],
        'fmt_saved': chrome['fmt_confirm_saved'],
        'closing': chrome['confirm_closing'],
        'fallback': chrome['confirm_fallback'],
        'chrome': json.dumps(chrome, ensure_ascii=True),
    }


def _render_error_page(message, hint, lang='en'):
    chrome = _CHROME[_chrome_lang(lang)]
    return _ERROR_PAGE_TEMPLATE % {
        'message': _esc(message), 'hint': _esc(hint),
        'lang_attr': _chrome_lang(lang), 'title': chrome['error_title'],
    }


def _render_radios(options, lang='en'):
    if not options:
        return '<p class="empty">%s</p>' % _t(lang, 'no_options')
    rows = []
    for idx, opt in enumerate(options, 1):
        rows.append(
            '<label class="opt"><input type="radio" name="choice" '
            'id="opt%d" value="%s"><span class="optcard">'
            '<span class="oradio"></span><span class="omain">'
            '<span class="otitle"><b>%d. %s</b></span></span></span></label>'
            % (idx, _esc(opt), idx, _esc(opt)))
    return '\n'.join(rows)


def _render_links(links, lang='en'):
    if not links:
        return ''
    items = []
    for name, url in links:
        items.append('<li><a href="%s" target="_blank" rel="noopener">%s</a>'
                     ' <code>%s</code></li>' % (_esc(url), _esc(name), _esc(url)))
    return ('<section class="links"><h2>%s</h2><ul>%s</ul>'
            '<p class="hint">%s</p>'
            '</section>' % (_t(lang, 'attachments'), ''.join(items),
                            _t(lang, 'links_hint')))


def _lines(text):
    """Non-empty stripped lines of a multi-line text field, HTML-escaped."""
    return [_esc(ln.strip()) for ln in str(text).split('\n') if ln.strip()]


# Rich-text rendering for context/delta/why. Spec text follows a
# "label: content" convention per line (short CJK label before a colon);
# the renderer parses it so bullets become structured: bold lead labels, a
# highlighted decision-ask row (the ask label), an example box (the example
# label), **bold** spans, and path-like tokens as <code>. Text without
# any of those renders as a plain bullet (unchanged).
_BL_LABEL_RE = re.compile(r'^([^\s\uff1a:]{1,14}?)(\uff1a|:)\s*(.*)$', re.S)
_BL_CJK_RE = re.compile(r'[\u4e00-\u9fff]')
_BL_BOLD_RE = re.compile(r'\*\*([^*]+)\*\*')
_BL_CODE_RE = re.compile(r'[\w.\-\\]+(?:\\[\w.\-\\]+)+')
_BL_ASK_LABELS = ('\u672c\u5361\u51b3\u5b9a', '\u672c\u5361\u95ee\u9898',
                  '\u672c\u5361\u51b3\u7b56')
_BL_EX_LABELS = ('\u4f8b', '\u4f8b\u5982', '\u793a\u4f8b')


def _rich_inline(esc):
    """Inline formatting on an escaped fragment: **bold** and code paths."""
    txt = _BL_BOLD_RE.sub(r'<b>\1</b>', esc)
    txt = _BL_CODE_RE.sub(lambda m: '<code>%s</code>' % m.group(0), txt)
    return txt


def _rich_line(ln, lead=''):
    """One rich-text line -> a structured bullet div. A leading markdown-style
    bullet mark ("- ", "* ", "· ", "• ") is stripped: the renderer adds its
    own bullet dot, so a literal mark would double up. A leading "N." /
    "N、" / "N)" marker instead renders an ordered, left-aligned item with
    its number bolded and no bullet dot."""
    s = re.sub(r'^[-*·•]\s+', '', str(ln).strip())
    esc = _esc(s)
    num = re.match(r'^(\d{1,2})\s*[.\u3001\uff09)]\s*', esc)
    if num:
        esc = esc[num.end():]
    label = colon = None
    rest = esc
    m = _BL_LABEL_RE.match(esc)
    if m and _BL_CJK_RE.search(m.group(1)):
        label, colon, rest = m.group(1), m.group(2), m.group(3)
    body = _rich_inline(rest)
    if lead:
        body = ('<b>%s</b> %s' % (lead, body)) if body else '<b>%s</b>' % lead
    # Decision-ask lines are pulled out of context by _extract_ask and render
    # as the question block subtitle, so no special class is needed here; the
    # example label still renders as an example box.
    if label in _BL_EX_LABELS:
        cls = 'bl bl-example'
    elif num:
        cls = 'bl num'
        body = ('<b>%s.</b> ' % num.group(1)) + body
    else:
        cls = 'bl'
    if label:
        return '<div class="%s"><b>%s%s</b>%s</div>' % (cls, label, colon, body)
    return '<div class="%s">%s</div>' % (cls, body)


def _rich_bullets(text, lead=''):
    """Structured bullets for a multi-line rich-text field; the optional
    bold lead (e.g. "Delta:") prefixes the first line."""
    lines = [ln for ln in str(text).splitlines() if ln.strip()]
    if not lines:
        return ''
    out = [_rich_line(lines[0], lead)]
    out.extend(_rich_line(ln) for ln in lines[1:])
    return ''.join(out)


def _sublist(lead, items):
    """A bold lead label (Pros:/Cons:) followed by numbered sub-items."""
    out = ['<div class="bl"><b>%s</b></div>' % lead]
    for n, item in enumerate(items, 1):
        out.append('<div class="bl sub">%d. %s</div>'
                   % (n, _rich_inline(_esc(str(item)))))
    return ''.join(out)


def _strip_example_label(text):
    """Drop a leading example-label prefix from the example field: the
    renderer adds its own "Example:" lead, so a literal label would double
    up (same philosophy as the markdown bullet-mark strip)."""
    lines = str(text).splitlines()
    if lines:
        m = re.match(r'^\s*(?:\u4f8b\u5982|\u793a\u4f8b|\u4f8b)\s*[\uff1a:]\s*',
                     lines[0])
        if m:
            lines[0] = lines[0][m.end():]
    return '\n'.join(lines)


def _extract_ask(text):
    """Split a rich-text field into (ask_lines, rest_lines). Ask lines carry
    the decision-ask label and render as the question block subtitle instead
    of a bullet, so the card has exactly one ask surface."""
    ask, rest = [], []
    for ln in str(text).splitlines():
        if not ln.strip():
            continue
        m = _BL_LABEL_RE.match(_esc(ln.strip()))
        if m and m.group(1) in _BL_ASK_LABELS:
            ask.append(ln.strip())
        else:
            rest.append(ln.strip())
    return ask, rest


def _ask_subtitle(ask_lines):
    """Render ask lines as question-block subtitle paragraphs."""
    parts = []
    for ln in ask_lines:
        m = _BL_LABEL_RE.match(_esc(ln))
        if m:
            parts.append('<b>%s%s</b>%s'
                         % (m.group(1), m.group(2), _rich_inline(m.group(3))))
        else:
            parts.append(_rich_inline(_esc(ln)))
    return ''.join('<p class="dqask">%s</p>' % p for p in parts)


def _render_cards(questions, lang='en'):
    """Render one <section class="card"> per question for the batch page.

    Card shell: header
    band with the qid chip, question block (help icon, kicker, title; no
    background fill), explanation and options inside the card body. Cards
    carry the round template structure: 💡 Explanation bullets (context),
    📊 Options header, options with an optional annotated image / delta /
    probability chip / ➡️ RECOMMENDED banner / why bullets, and an
    optional per-card note input. context/delta/why accept multi-line
    text and render one bullet per line. Chrome copy follows lang.
    """
    blocks = []
    for idx, question in enumerate(questions):
        options = list(question['options'])
        has_prob = any(o['probability'] is not None for o in options)
        if has_prob:
            # Round template: options with probabilities render sorted by
            # probability descending; options without one keep their order
            # after the sorted ones. Radio values are labels, so the answer
            # payload is unaffected by the display order.
            options.sort(key=lambda o: (o['probability'] is None,
                                        -(o['probability'] or 0)))
        opts = []
        for no, option in enumerate(options, 1):
            img = ''
            if option['image']:
                # The page runs on http://127.0.0.1 and browsers block file://
                # subresources, so local images are re-served through /img.
                # Images keep their natural size and render
                # right after the delta caption (console-confirmed, round 2):
                # the caption says what to look at, the image is the evidence,
                # the interpretation text follows. Clicking opens a lightbox.
                # Spec "boxes" draw the red circles and red labels ON the
                # capture (page-rendered overlay), so the decided region is
                # always marked.
                src = '/img?path=' + urllib.parse.quote(option['image'], safe='')
                # Only rectangle marks draw as shotboxes on the capture:
                # move/icon/color marks are annotate-page visuals and stay
                # in the spec for the live overlay.
                rect_boxes = [b for b in option['boxes']
                              if b.get('kind', 'box') == 'box']
                overlay = ''.join(
                    '<span class="shotbox" data-x="%d" data-y="%d" '
                    'data-w="%d" data-h="%d"><span class="shotnum">%d</span>'
                    '%s</span>'
                    % (b['x'], b['y'], b['w'], b['h'], n + 1,
                       ('<span class="shotlabel">%s</span>' % _esc(b['label'])
                        if b['label'] else ''))
                    for n, b in enumerate(rect_boxes))
                img = ('<span class="shotwrap"><img class="optimg" src="%s" '
                       'alt="%s" data-zoom data-shot '
                       'title="%s">%s</span>'
                       % (_esc(src), _t(lang, 'option_image_alt'),
                          _t(lang, 'click_enlarge'), overlay))
            openlink = ''
            if option['url']:
                # One capture per option; the live view stays one click away
                # (an embedded iframe would duplicate the capture). A
                # /static-served page opens annotate-capable: the toolbar
                # is already there, one click on Annotate starts drawing.
                if _is_web_url(option['url']):
                    openlink = ('<a class="openlink" href="%s" target="_blank" '
                                'rel="noopener" onclick="event.stopPropagation()">'
                                '%s%s &#8599;</a>'
                                % (_esc(option['url']),
                                   _icon('arrow', 'ic ic-sm'),
                                   _t(lang, 'open_tab')))
                else:
                    # Relative urls are served under /static/; a url that
                    # already carries a query joins the flag with &, never
                    # a second ?. Compose first, escape once. Belt and
                    # braces: load validation rejects a leading /static/,
                    # the strip here keeps the prefix from ever doubling.
                    rel = option['url']
                    if rel.startswith('/static/'):
                        rel = rel[len('/static/'):]
                    sep = '&' if '?' in rel else '?'
                    ann_href = _esc('/static/%s%sannotate=1&q=%d&o=%d'
                                    % (rel, sep, idx, no - 1))
                    # Script-opened (target name grill-ann-tab, one reused
                    # tab) so the annotate tab keeps its opener reference
                    # AND may close itself after Save - a plain target=
                    # _blank tab is neither. Blue link family (the amber
                    # family belongs to the user's marks, not the entries).
                    openlink = ('<a class="openlink" href="%s" '
                                'target="grill-ann-tab" rel="opener" '
                                'onclick="event.stopPropagation();'
                                'window.open(this.href, \'grill-ann-tab\');'
                                'return false;">'
                                '%s%s &#8599;</a>'
                                % (ann_href, _icon('pencil', 'ic ic-sm'),
                                   _t(lang, 'open_tab')))
            if openlink:
                # Right-aligned row: the mouse-friendly edge for the
                # annotate-capable link.
                openlink = '<div class="linkrow">%s</div>' % openlink
            img = openlink + img
            delta = ''
            if option['delta']:
                delta = '<span class="delta">%s</span>' % _rich_bullets(
                    option['delta'], _t(lang, 'delta_lead'))
            prob = ('<span class="prob" title="%s">%g%%</span> '
                    % (_t(lang, 'prob_title'), option['probability'])
                    if option['probability'] is not None else '')
            rec = ('<span class="rec" style="margin-left:auto">'
                   '%s %s</span>'
                   % (_icon('spark', 'ic ic-sm'), _t(lang, 'recommended'))
                   if option['recommended'] else '')
            why = ''
            if option['why']:
                why = '<span class="why">%s</span>' % _rich_bullets(
                    option['why'], _t(lang, 'reason_lead'))
            example = ''
            if option.get('example'):
                example = '<span class="why">%s</span>' % _rich_bullets(
                    _strip_example_label(option['example']),
                    _t(lang, 'example_lead'))
            pros = ''
            if option.get('pros'):
                pros = '<span class="why">%s</span>' % _sublist(
                    _t(lang, 'pros_lead'), option['pros'])
            cons = ''
            if option.get('cons'):
                cons = '<span class="why">%s</span>' % _sublist(
                    _t(lang, 'cons_lead'), option['cons'])
            # Asking template: "N. 65% [RECOMMENDED] Option text",
            # evidence image right after the delta caption, then the
            # details in Reason / Example / Pros / Cons order. The
            # RECOMMENDED tag sits at the right end of the title row
            # (console-confirmed, round 4) so option labels align on a
            # single vertical scan line.
            chips = ''
            if prob:
                chips += prob + ' '
            opts.append(
                '<label class="opt"><input type="radio" name="q%d" '
                'value="%s"><span class="optcard"><span class="oradio">'
                '</span><span class="omain"><span class="otitle">'
                '<b>%d.</b> %s<b>%s</b>%s</span>'
                '<span class="oreveal"><span class="oinner">'
                '%s%s%s%s%s%s</span>'
                '</span></span></span></label>'
                % (idx, _esc(option['label']), no, chips,
                   _esc(option['label']), rec, delta, img, why, example,
                   pros, cons))
        # Write-in option: every card offers "None of these - write my own
        # answer" as its last radio. It is renderer-added, never a spec
        # option, so the evidence gate and the 2-3 option shape still hold.
        opts.append(
            '<label class="opt"><input type="radio" name="q%d" '
            'value="__own__" data-own="1"><span class="optcard">'
            '<span class="oradio"></span><span class="omain">'
            '<span class="otitle"><b>%d.</b> <b>%s</b></span>'
            '<span class="oreveal">'
            '<textarea class="owntext" id="own%d" rows="2" placeholder='
            '"%s">'
            '</textarea>'
            '<span class="pastezone" tabindex="0" role="button" '
            'aria-label="%s">'
            '%s %s</span>'
            '<span class="pastelist" id="pastelist%d"></span>'
            '<input type="file" class="pastefile" accept="image/*" '
            'multiple hidden>'
            '</span></span></span></label>'
            % (idx, len(options) + 1, _t(lang, 'own_label'), idx,
               _t(lang, 'own_placeholder'), _t(lang, 'paste_aria'),
               _icon('clip', 'ic ic-sm'), _t(lang, 'paste_hint'), idx))
        # No per-card note field: the write-in input inside the last option
        # is the card's one and only comment box (user-confirmed ruling).
        nextbtn = ('<button type="button" class="nextbtn">%s%s</button>'
                   % (_icon('arrow', 'ic ic-sm'),
                      _t(lang, 'review_answers') if idx == len(questions) - 1
                      else _t(lang, 'next_card')))
        ctx = ''
        ask_html = ''
        if question['context']:
            ask_lines, rest_lines = _extract_ask(question['context'])
            ask_html = _ask_subtitle(ask_lines) if ask_lines else ''
            if rest_lines:
                ctx = ('<div class="exp"><div class="exphead">%s%s'
                       '</div>%s</div>'
                       % (_icon('doc'), _t(lang, 'explanation'),
                          _rich_bullets('\n'.join(rest_lines))))
        evbadge = ''
        if question.get('evidence') == 'degraded':
            evbadge = ('<div class="evbadge">%s%s</div>'
                       % (_icon('clip', 'ic ic-sm'), _t(lang, 'evbadge')))
        opsh = '%s %s' % (_icon('list'), _t(lang, 'options_head'))
        if has_prob:
            opsh += _t(lang, 'options_sorted')
        if question.get('prob_label'):
            opsh += ('<span class="problegend">= %s</span>'
                     % _esc(question['prob_label']))
        blocks.append(
            '<section class="card qcard">'
            '<header class="chead"><span class="qid">%s</span>'
            '<span class="cbar">'
            '<button type="button" class="cnav" data-cnav="prev" '
            'aria-label="%s">&#8249;</button>'
            '<button type="button" class="cnav" data-cnav="next" '
            'aria-label="%s">&#8250;</button>'
            '</span></header>'
            '<div class="cbody">'
            '<div class="dq"><span class="qmark">%s</span><div>'
            '<div class="kicker">%s</div>'
            '<h2>%s</h2>%s</div></div>'
            '%s%s<div class="opshead">%s</div><div class="olist">%s</div>'
            '%s</div></section>'
            % (_esc(question['qid']), _t(lang, 'prev_card_aria'),
               _t(lang, 'next_card_aria'), _icon('help', 'ic ic-lg'),
               _t(lang, 'kicker'), _esc(question['title']), ask_html,
               evbadge, ctx, opsh, '\n'.join(opts), nextbtn))
    return '\n'.join(blocks)


def _render_page(title, qid, options, links):
    return _PAGE_TEMPLATE % {
        'title': _esc(title),
        'css': _CSS,
        'subtitle': _t('en', 'subtitle_single'),
        'options_head': _t('en', 'options_head'),
        'note_head': _t('en', 'note_head'),
        'note_placeholder': _t('en', 'note_placeholder'),
        'submit': _t('en', 'submit'),
        'submit_hint': _t('en', 'submit_hint'),
        'radios': _render_radios(options, 'en'),
        'links': _render_links(links, 'en'),
        'qid': json.dumps(qid),
        'chrome': json.dumps(_CHROME['en'], ensure_ascii=True),
        'js': _JS_SINGLE,
    }


def _render_spec_page(title, questions, lang='en', alignment=None, topic=''):
    chrome = _CHROME[_chrome_lang(lang)]
    keys_init = (
        '<span><span class="k">&#8592;</span>'
        '<span class="k">&#8594;</span> %s</span>'
        '<span><span class="k">&#8593;</span>'
        '<span class="k">&#8595;</span> %s</span>'
        '<span><span class="k">1-9</span> %s</span>'
        '<span><span class="k">Enter</span> %s</span>'
        % (_t(lang, 'keys_switch'), _t(lang, 'keys_browse'),
           _t(lang, 'keys_pick'), _t(lang, 'keys_confirm')))
    return _SPEC_PAGE_TEMPLATE % {
        'title': _esc(title),
        'lang': _esc(lang),
        'subtitle': _t(lang, 'subtitle'),
        'kpi_cards': _t(lang, 'kpi_cards'),
        'kpi_decided': _t(lang, 'kpi_decided'),
        'kpi_pending': _t(lang, 'kpi_pending'),
        'review_head': _t(lang, 'review_head'),
        'submit': _t(lang, 'submit'),
        'submit_hint': _t(lang, 'submit_hint'),
        'keys_init': keys_init,
        'alignment': _render_alignment(topic, alignment or [], lang),
        'css': _CSS,
        'cards': _render_cards(questions, lang),
        'qids': json.dumps([q['qid'] for q in questions]),
        'qtitles': json.dumps([q['title'] for q in questions]),
        'pencil': json.dumps(_icon('pencil', 'ic ic-sm')),
        'chrome': json.dumps(chrome, ensure_ascii=True),
        'icons': json.dumps({'clock': _icon('clock', 'ic ic-xs'),
                             'check': _icon('check', 'ic ic-xs'),
                             'circle_check': _icon('circle_check',
                                                   'ic ic-xs')}),
        'js': _JS_SPEC,
    }


def _parse_payload(raw, content_type):
    """Return (data, None) or (None, reason). Accepts a raw JSON body or the
    urlencoded form body produced by the page (hidden "payload" field)."""
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError as exc:
        return None, 'request body is not valid UTF-8: %s' % exc
    try:
        return json.loads(text), None
    except ValueError:
        pass  # not raw JSON: fall through to the form-encoded branch
    if 'application/x-www-form-urlencoded' in (content_type or '').lower():
        fields = urllib.parse.parse_qs(text, keep_blank_values=True)
        values = fields.get('payload')
        if not values:
            return None, ('form body must include a "payload" field holding '
                          'the JSON answers array')
        try:
            return json.loads(values[0]), None
        except ValueError as exc:
            return None, 'the "payload" field is not valid JSON: %s' % exc
    return None, ('request body is not valid JSON: expected a JSON array or a '
                  'form-encoded "payload" field')


def _validate_answers(data):
    """Return (answers, None) when the payload is schema-valid, else (None, reason)."""
    if not isinstance(data, list) or len(data) == 0:
        return None, 'request body must be a non-empty JSON array of answer objects'
    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            return None, 'answer #%d is not a JSON object' % idx
        missing = [key for key in REQUIRED_KEYS if key not in item]
        if missing:
            return None, 'answer #%d missing key(s): %s' % (idx, ', '.join(missing))
        for key in ('qid', 'choice', 'note'):
            if not isinstance(item[key], str):
                return None, 'answer #%d field "%s" must be a string' % (idx, key)
        if isinstance(item['ts'], bool) or not isinstance(item['ts'], (int, float)):
            return None, ('answer #%d field "ts" must be a number '
                          '(epoch milliseconds)' % idx)
        if not item['qid'] or not item['choice']:
            return None, 'answer #%d fields "qid" and "choice" must be non-empty' % idx
        images = item.get('images')
        if images is not None:
            if not isinstance(images, list) or not (0 < len(images) <= 4):
                return None, ('answer #%d field "images" must be a list of '
                              '1-4 image objects' % idx)
            for k, im in enumerate(images):
                if (not isinstance(im, dict)
                        or not isinstance(im.get('name'), str)
                        or not isinstance(im.get('data'), str)):
                    return None, ('answer #%d image #%d must carry string '
                                  '"name" and "data" fields' % (idx, k))
                if not re.match(r'^data:image/(png|jpeg|jpg|gif|webp);base64,',
                                im['data']):
                    return None, ('answer #%d image #%d "data" must be a '
                                  'base64 dataURL of png/jpg/gif/webp'
                                  % (idx, k))
    return data, None


_IMAGE_EXT = {'image/png': '.png', 'image/jpeg': '.jpg', 'image/jpg': '.jpg',
              'image/gif': '.gif', 'image/webp': '.webp'}


def _save_answer_images(answers, answers_path):
    """Decode each answer's pasted images to files beside the answers file
    and replace the dataURLs with the saved paths. The paste is the only
    writer: images land only when the user submits."""
    import base64
    import binascii
    stem = answers_path.stem
    saved_total = 0
    for item in answers:
        images = item.get('images')
        if not images:
            continue
        qid_tag = re.sub(r'[^A-Za-z0-9_-]+', '_', str(item['qid']))[:40]
        paths = []
        for k, im in enumerate(images, 1):
            head, _, b64 = im['data'].partition(',')
            mime = head[5:].split(';')[0]
            ext = _IMAGE_EXT.get(mime, '.png')
            try:
                blob = base64.b64decode(b64, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise ValueError('image #%d of %s is not valid base64: %s'
                                 % (k, item['qid'], exc))
            if len(blob) > 8 * 1024 * 1024:
                raise ValueError('image #%d of %s exceeds 8 MB'
                                 % (k, item['qid']))
            img_path = answers_path.with_name(
                '%s-%s-img%d%s' % (stem, qid_tag, k, ext))
            img_path.write_bytes(blob)
            paths.append(str(img_path))
            saved_total += 1
        item['images'] = paths
    return saved_total


def _check_qid_set(answers, expected_qids):
    """Batch mode only: the submitted qid set must match the page questions."""
    qids = [item['qid'] for item in answers]
    if len(set(qids)) != len(qids):
        dupes = sorted({q for q in qids if qids.count(q) > 1})
        return 'duplicate answers for qid(s): %s' % ', '.join(dupes)
    missing = sorted(expected_qids - set(qids))
    unexpected = sorted(set(qids) - expected_qids)
    if missing or unexpected:
        parts = []
        if missing:
            parts.append('missing: %s' % ', '.join(missing))
        if unexpected:
            parts.append('unexpected: %s' % ', '.join(unexpected))
        return ('answers qid set does not match the questions on this page (%s)'
                % '; '.join(parts))
    return None


def _query_param(query, name):
    """First value of a query parameter; '+' stays literal (file paths)."""
    for part in query.split('&'):
        if not part:
            continue
        key, _, value = part.partition('=')
        if urllib.parse.unquote(key) == name:
            return urllib.parse.unquote(value)
    return None


class _DecisionHandler(BaseHTTPRequestHandler):
    """Serves the decision page (GET /), local images (GET /img) and the
    batch answer sink (POST /answer)."""

    page_html = ''
    round_no = 0
    page_lang = 'en'  # chrome language, set by _run_server from the spec
    spec_data = None  # the loaded spec, so /static annotate pages get boxes
    submitted = False  # set by the valid POST; the server self-exits after it
    expected_qids = None  # frozenset in --spec mode -> strict batch validation
    static_root = None  # set by _run_server from --static-root
    answers_path = None  # set by _run_server from --answers or the default
    session = None  # session token, set by _run_server
    protocol_version = 'HTTP/1.1'
    server_version = 'DecisionDesk/2.0'

    def log_message(self, fmt, *args):
        pass  # keep stderr clean for [ERR] JSON only

    def _send(self, status, ctype, text):
        body = text.encode('utf-8')
        self.send_response(status)
        self._responded = True
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def _guard(self, route):
        """Run a route; an unexpected exception becomes a 500 error page
        instead of a silently dropped connection. The error page itself is
        guarded too: if rendering it fails, a plain-text body still goes out."""
        self._responded = False
        try:
            route()
        except Exception as exc:  # loopback tool: report, never hang up silently
            self.close_connection = True
            if not self._responded:
                try:
                    self._send(500, 'text/html; charset=utf-8',
                               _render_error_page(
                                   'Internal server error: %s' % exc,
                                   _t(getattr(self, 'page_lang', 'en'),
                                      'internal_guidance'),
                                   getattr(self, 'page_lang', 'en')))
                except Exception:
                    try:
                        self._send(500, 'text/plain; charset=utf-8',
                                   'Internal server error: %s' % exc)
                    except OSError:
                        pass

    def do_GET(self):
        self._guard(self._route_get)

    def do_POST(self):
        self._guard(self._route_post)

    def _route_get(self):
        split = urllib.parse.urlsplit(self.path)
        if split.path in ('/', '/index.html'):
            self._send(200, 'text/html; charset=utf-8', self.page_html)
        elif split.path == '/img':
            self._serve_image(split.query)
        elif split.path.startswith('/static/'):
            self._serve_static(split.path[len('/static/'):], split.query)
        else:
            self._send(404, 'text/plain; charset=utf-8', 'not found')

    def _serve_static(self, rel, query=''):
        """Serve a file under --static-root (live prototype pages). HTML
        pages requested with ?annotate=1 carry the annotation overlay, so
        the user marks the live page and sends the marks to the agent."""
        root = getattr(self, 'static_root', None)
        if not root:
            self._send(404, 'text/plain; charset=utf-8', 'no --static-root')
            return
        rel = urllib.parse.unquote(rel)
        target = (Path(root) / rel).resolve()
        if Path(root).resolve() not in target.parents:
            self._send(403, 'text/plain; charset=utf-8', 'forbidden')
            return
        ctype = {'.html': 'text/html; charset=utf-8', '.css': 'text/css',
                 '.js': 'application/javascript', '.json': 'application/json',
                 '.svg': 'image/svg+xml', '.png': 'image/png',
                 '.jpg': 'image/jpeg', '.woff2': 'font/woff2'}.get(
                     target.suffix.lower())
        try:
            data = target.read_bytes() if ctype else None
        except OSError:
            data = None
        if data is None:
            self._send(404, 'text/plain; charset=utf-8', 'not found')
            return
        if ctype.startswith('text/html') and 'annotate=1' in query:
            text = data.decode('utf-8', errors='replace')
            marker = '</body>'
            chrome = _CHROME[getattr(self, 'page_lang', 'en')]
            # The option's spec boxes ride along as the red AI-mark layer:
            # q/o arrive in the query, the boxes come from the loaded spec.
            ai = {'captureWidth': 1000, 'boxes': []}
            sd_spec = getattr(self, 'spec_data', None)
            try:
                sq = int(_query_param(query, 'q'))
                so = int(_query_param(query, 'o'))
                ai['boxes'] = [dict(b) for b in
                               sd_spec['questions'][sq]['options'][so]['boxes']]
            except (TypeError, ValueError, IndexError, KeyError, AttributeError):
                pass
            inject = _ANNOTATOR_ASSET % _annotator_injection(chrome, ai)
            if marker in text.lower():
                idx = text.lower().rindex(marker)
                text = text[:idx] + inject + text[idx:]
            else:
                text += inject
            missing = [i for i in _PRELAUNCH_ANN_IDS if i not in text]
            if missing:
                # The toolbar is the annotate flow's spine: a page served
                # without every button breaks the save round-trip. The
                # pre-launch check catches this class first; this re-assert
                # keeps every served page honest.
                self._send(500, 'text/plain; charset=utf-8',
                           'annotator toolbar incomplete: %s'
                           % ', '.join(missing))
                return
            data = text.encode('utf-8')
        self.send_response(200)
        self._responded = True
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def _serve_image(self, query):
        """Serve a local image file by absolute path.

        Design tradeoff: this is a loopback-only, single-user tool. The page
        runs on http://127.0.0.1 and browsers block file:// subresources, so
        local images must be re-served through this endpoint. The server
        never binds beyond 127.0.0.1 and only files with an image extension
        are read; arbitrary local reads by other local processes are out of
        scope for this threat model.
        """
        raw_path = _query_param(query, 'path')
        if not raw_path:
            self._send(400, 'text/plain; charset=utf-8', 'missing path parameter')
            return
        ctype = IMAGE_TYPES.get(Path(raw_path).suffix.lower())
        if ctype is None:
            self._send(404, 'text/plain; charset=utf-8',
                       'unsupported image type: %s (png/jpg/jpeg/gif only)'
                       % Path(raw_path).suffix.lower())
            return
        try:
            data = Path(raw_path).read_bytes()
        except OSError:
            self._send(404, 'text/plain; charset=utf-8',
                       'image not found: %s' % raw_path)
            return
        self.send_response(200)
        self._responded = True
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def _handle_annotations(self, raw):
        """Receive the user's amber annotations from an annotated /static
        page and save them beside the answers file. The server keeps
        serving: the user may keep annotating and sending."""
        try:
            data = json.loads(raw.decode('utf-8'))
        except (ValueError, UnicodeDecodeError) as exc:
            self._send(400, 'application/json',
                       json.dumps({'error': 'invalid JSON: %s' % exc}))
            return
        boxes = data.get('boxes') if isinstance(data, dict) else None
        proto = bool(data.get('proto')) if isinstance(data, dict) else False
        if not isinstance(boxes, list) or (not boxes and not proto):
            self._send(400, 'application/json',
                       json.dumps({'error': 'boxes must be a non-empty list'}))
            return
        if not boxes and proto:
            # A bare prototype request: nothing to record on disk, the
            # flag itself is the message.
            self._send(200, 'application/json',
                       json.dumps({'ok': True, 'proto': True, 'count': 0}))
            return
        for k, b in enumerate(boxes, 1):
            if not isinstance(b, dict) or not isinstance(b.get('caption'), str):
                self._send(400, 'application/json', json.dumps(
                    {'error': 'box #%d must carry a caption' % k}))
                return
            for key in ('n', 'x', 'y', 'w', 'h'):
                if isinstance(b.get(key), bool) or not isinstance(
                        b.get(key), (int, float)):
                    self._send(400, 'application/json', json.dumps(
                        {'error': 'box #%d field "%s" must be a number'
                         % (k, key)}))
                    return
        target = self.answers_path.with_name(
            self.answers_path.stem + '-annotations.json')
        payload = {'url': str(data.get('url', '')),
                   'title': str(data.get('title', '')),
                   'boxes': boxes}
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name('%s.tmp%d' % (target.name,
                                                 time.monotonic_ns()))
            with io.open(tmp, 'w', encoding='utf-8') as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write('\n')
            os.replace(tmp, target)
        except OSError as exc:
            self._send(500, 'application/json',
                       json.dumps({'error': 'write failed: %s' % exc}))
            return
        print('[INFO] annotations ready: %s (%d boxes)'
              % (target, len(boxes)))
        self._send(200, 'application/json',
                   json.dumps({'ok': True, 'path': str(target),
                               'proto': proto, 'count': len(boxes)}))

    def _route_post(self):
        path = urllib.parse.urlsplit(self.path).path
        try:
            length = int(self.headers.get('Content-Length') or 0)
        except ValueError:
            length = 0
        raw = self.rfile.read(length) if length > 0 else b''
        if path == '/annotations':
            self._handle_annotations(raw)
            return
        if path != '/answer':
            self._send(404, 'text/plain; charset=utf-8', 'not found')
            return
        data, err = _parse_payload(raw, self.headers.get('Content-Type'))
        answers = None
        if err is None:
            answers, err = _validate_answers(data)
        if err is None and self.expected_qids is not None:
            err = _check_qid_set(answers, self.expected_qids)
        if err is not None:
            self._send(400, 'text/html; charset=utf-8', _render_error_page(
                'Submission rejected: %s' % err,
                _t(self.page_lang, 'rejected_guidance'), self.page_lang))
            return
        target = self.answers_path
        try:
            _save_answer_images(answers, target)
        except ValueError as exc:
            self._send(400, 'text/html; charset=utf-8', _render_error_page(
                'Submission rejected: %s' % exc,
                _t(self.page_lang, 'images_guidance'), self.page_lang))
            return
        tmp_path = target.with_name('%s.tmp%d' % (target.name, time.monotonic_ns()))
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with io.open(tmp_path, 'w', encoding='utf-8') as handle:
                json.dump([dict(item, session=self.session) for item in answers],
                          handle, ensure_ascii=False, indent=2)
                handle.write('\n')
            os.replace(tmp_path, target)
        except OSError as exc:
            try:
                tmp_path.unlink()
            except OSError:
                pass
            self._send(500, 'text/html; charset=utf-8', _render_error_page(
                'Failed to write the answers file: %s' % exc,
                _t(self.page_lang, 'retry_guidance'), self.page_lang))
            return
        _DecisionHandler.submitted = True
        self._send(200, 'text/html; charset=utf-8',
                   _render_confirm(target, self.page_lang))
        # Submission done: stop serving so the port frees itself (no manual kill).
        threading.Thread(target=self.server.shutdown, daemon=True).start()


class _DecisionServer(ThreadingHTTPServer):
    allow_reuse_address = False  # real bind probe: an occupied port must fail
    daemon_threads = True


def _run_text(cmd):
    """Run a command and return its stdout as text ('' on any failure)."""
    try:
        done = subprocess.run(cmd, capture_output=True, timeout=10,
                              encoding='utf-8', errors='replace')
        return done.stdout or ''
    except (OSError, subprocess.SubprocessError):
        return ''


def _pids_on_ports(ports):
    """PIDs listening on the given loopback ports (netstat on Windows, lsof elsewhere)."""
    pids = set()
    wanted = {str(p) for p in ports}
    if os.name == 'nt':
        out = _run_text(['netstat', '-ano', '-p', 'TCP'])
        for line in out.splitlines():
            parts = line.split()
            if (len(parts) >= 5 and parts[0] == 'TCP' and parts[3] == 'LISTENING'
                    and parts[1].rsplit(':', 1)[-1] in wanted and parts[4].isdigit()):
                pids.add(int(parts[4]))
    else:
        for port in ports:
            out = _run_text(['lsof', '-t', '-i', 'TCP:%d' % port, '-sTCP:LISTEN'])
            pids.update(int(x) for x in out.split() if x.isdigit())
    return pids


def _is_decision_server(pid):
    """True only for processes whose command line runs serve_decision.py (never unrelated apps)."""
    if os.name == 'nt':
        cmd = ['powershell', '-NoProfile', '-Command',
               '(Get-CimInstance Win32_Process -Filter "ProcessId=%d").CommandLine' % pid]
    else:
        cmd = ['ps', '-o', 'command=', '-p', str(pid)]
    return 'serve_decision.py' in _run_text(cmd)


def _free_stale_ports(ports):
    """Stop leftover decision servers that hold the ports. Returns the PIDs stopped."""
    freed = []
    for pid in _pids_on_ports(ports):
        if pid == os.getpid() or not _is_decision_server(pid):
            continue
        try:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(pid), '/F'],
                               capture_output=True, timeout=10)
            else:
                os.kill(pid, 15)
            freed.append(pid)
        except (OSError, subprocess.SubprocessError):
            pass
    return freed


def _answers_preflight(path):
    """Return an OSError when the answers sink cannot take a write. An
    unwritable sink must be discovered before the port binds - never after
    the user completes a whole round."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_dir():
            raise IsADirectoryError(str(path))
        probe = path.with_name(path.name + '.probe')
        with open(probe, 'w', encoding='utf-8') as handle:
            handle.write('probe')
        probe.unlink()
    except OSError as exc:
        return exc
    return None


def _bind_console(ports):
    """Bind the first free port of ports (port+1 fallback). None when all are busy."""
    for candidate in ports:
        try:
            return _DecisionServer(('127.0.0.1', candidate), _DecisionHandler)
        except OSError:
            if candidate == ports[0]:
                sys.stdout.write('[WARN] port %d busy, retrying on %d\n'
                                 % (candidate, candidate + 1))
                sys.stdout.flush()
    return None


def _run_server(args, spec):
    if spec is not None:
        round_no = args.round if args.round is not None else spec['round']
        title = (args.title or spec['title']
                 or 'Decision Console — Round %d' % round_no)
        page_html = _render_spec_page(title, spec['questions'],
                                      spec.get('lang', 'en'),
                                      spec.get('alignment'), spec.get('topic', ''))
        expected_qids = frozenset(q['qid'] for q in spec['questions'])
    else:
        round_no = args.round
        options = _parse_options(args.options)
        links = _parse_links(args.links)
        title = args.title or 'Decision Console — Round %d' % round_no
        page_html = _render_page(title, 'round-%d' % round_no, options, links)
        expected_qids = None

    _DecisionHandler.page_html = page_html
    session = secrets.token_hex(8)
    _DecisionHandler.static_root = args.static_root
    _DecisionHandler.session = session
    _DecisionHandler.round_no = round_no
    _DecisionHandler.page_lang = (_chrome_lang(spec.get('lang'))
                                  if spec is not None else 'en')
    _DecisionHandler.spec_data = spec
    _DecisionHandler.expected_qids = expected_qids
    _DecisionHandler.answers_path = (Path(args.answers) if args.answers
                                      else _answers_path(round_no))
    sink_error = _answers_preflight(_DecisionHandler.answers_path)
    if sink_error is not None:
        return _emit_error(
            'prelaunch', 'answers sink not writable', str(sink_error),
            'pass a writable --answers file path (the path must not name '
            'a directory)')

    if not 0 < args.port <= MAX_PORT:
        return _emit_error(
            'arg_error', 'invalid port',
            '--port %d is outside 1-65535' % args.port,
            'pass a port between 1 and 65535')
    ports = (args.port,) + ((args.port + 1,) if args.port < MAX_PORT else ())
    server = _bind_console(ports)
    if server is None:
        freed = _free_stale_ports(ports)
        if freed:
            sys.stdout.write('[INFO] stopped stale decision server pid(s) %s\n'
                             % ', '.join(str(p) for p in freed))
            sys.stdout.flush()
            time.sleep(0.5)
            server = _bind_console(ports)
    if server is None:
        return _emit_error(
            'bind_error', 'port bind failed',
            'ports %d and %d are both unavailable on 127.0.0.1'
            % (args.port, args.port + 1),
            'free one of the ports or pass --port with an available port')

    try:
        ANSWERS_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass  # POST handler retries mkdir before writing
    url = 'http://127.0.0.1:%d' % server.server_address[1]
    no_open = bool(getattr(args, 'no_open', False))
    sys.stdout.write('[INFO] session %s\n' % session)
    sys.stdout.write('[OK] serving %s\n' % url)
    sys.stdout.flush()
    # Auto-open the console so the user notices a pending decision round
    # even when the server runs in the background. Failure is non-fatal:
    # the URL stays on stdout for manual opening.
    try:
        opened = False if no_open else webbrowser.open(url)
    except Exception:
        opened = False
    if no_open:
        sys.stdout.write('[INFO] browser not opened (--no-open); open %s manually\n' % url)
    elif opened:
        sys.stdout.write('[INFO] opened %s in the default browser\n' % url)
    else:
        sys.stdout.write('[WARN] could not open a browser; open %s manually\n'
                         % url)
    sys.stdout.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    if _DecisionHandler.submitted:
        # Self-exit contract: after the submit the server process itself
        # reports the answers, so one background task covers the whole round
        # and no second watcher process is needed.
        try:
            content = _DecisionHandler.answers_path.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            content = ''
        sys.stdout.write('[OK] answers ready: %s\n'
                         % _DecisionHandler.answers_path)
        if content:
            sys.stdout.write(content)
            if not content.endswith('\n'):
                sys.stdout.write('\n')
        sys.stdout.flush()
    return 0


def _is_session_answers(content, session):
    """True when content is a non-empty answers array and every entry carries the session token."""
    try:
        entries = json.loads(content)
    except ValueError:
        return False
    return (isinstance(entries, list) and len(entries) > 0
            and all(isinstance(item, dict) and item.get('session') == session
                    for item in entries))


def _run_watcher(path_str, timeout, session):
    target = Path(path_str)
    deadline = (None if timeout is None
                else time.monotonic() + max(0.0, timeout))
    while True:
        try:
            ready = target.is_file() and target.stat().st_size > 0
        except OSError:
            ready = False
        if ready:
            content = None
            try:
                content = target.read_text(encoding='utf-8')
            except (OSError, UnicodeDecodeError, ValueError):
                content = None  # mid-write or unreadable: keep polling
            if content is not None and _is_session_answers(content, session):
                sys.stdout.write('[OK] answers ready: %s\n' % target)
                sys.stdout.write(content)
                if not content.endswith('\n'):
                    sys.stdout.write('\n')
                sys.stdout.flush()
                return 0
        if deadline is not None and time.monotonic() >= deadline:
            sys.stdout.write('[WARN] timeout\n')
            sys.stdout.flush()
            return 3
        time.sleep(POLL_INTERVAL)


class _ArgError(Exception):
    """Raised when argparse rejects the command line (exit code 2 path)."""


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise _ArgError(message)


def _build_parser():
    parser = _Parser(
        prog='serve_decision.py',
        description='Local decision console (server) + answer file watcher.')
    parser.add_argument('--spec',
                        help='server mode: batch spec JSON (one page = one round, '
                             'one card per question, single Submit)')
    parser.add_argument('--round', type=int,
                        help='server mode: decision round N (default answers file answers-round<N>.json; '
                             'with --spec it overrides the spec "round" field)')
    parser.add_argument('--port', type=int, default=8765,
                        help='server mode: TCP port (default 8765; busy -> port+1)')
    parser.add_argument('--answers',
                        help='server mode: answers file path (default: '
                             'answers-round<N>.json in the system temp folder)')
    parser.add_argument('--title',
                        help='server mode: page title (default: Decision Console — Round N '
                             'or the spec "title")')
    parser.add_argument('--options',
                        help='server mode: comma-separated radio option labels (single card)')
    parser.add_argument('--links',
                        help='server mode: comma-separated "name|url" attachment links')
    parser.add_argument('--static-root',
                        help='server mode: folder served at /static/ so option '
                             '"url" fields can embed a live prototype')
    parser.add_argument('--watch',
                        help='watcher mode: answers file path to poll')
    parser.add_argument('--timeout', type=float, default=None,
                        help='watcher mode: seconds to wait (default: no '
                             'timeout, wait until the answers file appears)')
    parser.add_argument('--session',
                        help='watcher mode: session token that the server printed (required)')
    parser.add_argument('--no-open', action='store_true',
                        help='serve mode: print the URL only; do not open a browser '
                             '(maintainer checks use this so no page pops up)')
    return parser


def _annotator_injection(chrome, ai):
    """The inject dict for the annotator asset. The pre-launch check
    formats the template with the same keys, so a missing key or a bare
    percent fails before the port binds (never as a runtime 500)."""
    return {
        'count_init': chrome['fmt_ann_count'].replace('%d', '0'),
        'toggle_title': chrome['ann_toggle'],
        'toggle_label': chrome['ann_toggle'],
        'save_title': chrome['ann_save_title'],
        'save_label': chrome['ann_save'],
        'return_title': chrome['ann_return_title'],
        'return_label': chrome['ann_return'],
        'proto_gen': chrome['proto_gen'],
        'proto_gen_title': chrome['proto_gen_title'],
        'ai_count_init': chrome['fmt_ai_count'].replace('%d', '0'),
        'ai_clear_t': chrome['ai_clear'],
        'ai_clear': chrome['ai_clear'],
        'ai_restore_t': chrome['ai_restore'],
        'ai_restore': chrome['ai_restore'],
        'tool_box': chrome['tool_box'],
        'tool_arrow': chrome['tool_arrow'],
        'tool_eraser': chrome['tool_eraser'],
        'tool_box_ic': _icon('box', 'tool-ic'),
        'tool_arrow_ic': _icon('arrow', 'tool-ic'),
        'tool_eraser_ic': _icon('eraser', 'tool-ic'),
        'undo_title': chrome['ann_undo'],
        'undo_label': chrome['ann_undo'],
        'undo_ic': _icon('undo', 'tool-ic'),
        'redo_title': chrome['ann_redo'],
        'redo_label': chrome['ann_redo'],
        'redo_ic': _icon('redo', 'tool-ic'),
        'ai_boxes': json.dumps(ai, ensure_ascii=True),
        'ann': json.dumps(chrome, ensure_ascii=True),
    }


# The annotate toolbar is the save round-trip's spine: every button below
# must exist on a served annotate page, and the pre-launch check refuses
# to serve when any one of them is missing from the asset.
_PRELAUNCH_ANN_IDS = (
    'grill-ann-toolbar', 'grill-ann-toolbar-top', 'grill-tool-group',
    'grill-tool-box', 'grill-tool-arrow', 'grill-tool-eraser',
    'grill-ann-undo', 'grill-ann-redo',
    'grill-ai-group', 'grill-ai-clear', 'grill-ai-restore',
    'grill-ann-count', 'grill-ann-toggle', 'grill-ann-save',
    'grill-ann-return', 'grill-ann-proto',
)
_PRELAUNCH_PROBE_TIMEOUT = 3


def _prelaunch_checks(spec, static_root):
    """Deterministic verify-before-serve. Every option url must be
    openable - a relative url exists as an html file under the static
    root, a remote url answers within a bounded probe - and the annotator
    asset must carry every toolbar button and format cleanly with the
    injected keys. Any issue stops the launch: the port never binds and
    the browser never opens."""
    issues = []

    def bad(loc, msg, fix):
        issues.append({'loc': loc, 'type': 'prelaunch', 'msg': msg,
                       'fix': fix})

    for q, question in enumerate(spec.get('questions') or []):
        for o, option in enumerate(question.get('options') or []):
            url = option.get('url')
            if not url:
                continue
            loc = ['questions', q, 'options', o, 'url']
            if _is_web_url(url):
                try:
                    with urllib.request.urlopen(
                            url, timeout=_PRELAUNCH_PROBE_TIMEOUT) as resp:
                        if resp.status >= 400:
                            bad(loc, 'remote url answers %d' % resp.status,
                                'serve the page or fix the url')
                except Exception as exc:
                    bad(loc, 'remote url does not answer: %s' % exc,
                        'start the artifact server or fix the url')
            else:
                if not static_root:
                    bad(loc, 'relative url without --static-root',
                        'pass --static-root <dir> serving the page')
                    continue
                target = (Path(static_root) / urllib.parse.unquote(
                    url.split('#')[0].split('?')[0])).resolve()
                inside = (Path(static_root).resolve() in target.parents
                          or target == Path(static_root).resolve())
                if not inside:
                    bad(loc, 'relative url escapes the static root',
                        'keep the page inside --static-root')
                    continue
                if not target.is_file() or target.suffix.lower() != '.html':
                    bad(loc, 'relative url has no html file under the '
                             'static root: %s' % target.name,
                        'create the page or fix the url')
    missing = [i for i in _PRELAUNCH_ANN_IDS if i not in _ANNOTATOR_ASSET]
    if missing:
        bad(['annotator_asset'],
            'toolbar buttons missing from the template: %s'
            % ', '.join(missing),
            'restore the ids in _ANNOTATOR_ASSET')
    else:
        try:
            _ANNOTATOR_ASSET % _annotator_injection(
                _CHROME['en'], {'captureWidth': 1000, 'boxes': []})
        except (KeyError, ValueError) as exc:
            bad(['annotator_asset'],
                'annotator template does not format cleanly: %s' % exc,
                'fix the template placeholders or escape bare percents')
    return issues


def main(argv):
    _setup_streams()
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except _ArgError as exc:
        return _emit_error('arg_error', 'invalid arguments', str(exc),
                           'run: python serve_decision.py --help')
    if args.watch:
        if (args.round is not None or args.spec or args.options
                or args.answers is not None or args.title or args.links
                or args.no_open or args.static_root
                or args.port != 8765):
            return _emit_error('arg_error', 'mode flags are mutually exclusive',
                               '--watch cannot be combined with --round, --spec, '
                               '--options, --answers, --title, --port, --links, '
                               '--no-open or --static-root',
                               'pass --watch <file> --session <token> alone '
                               'for watcher mode')
        if args.timeout is not None and args.timeout < 0:
            return _emit_error('arg_error', 'invalid --timeout value',
                               '--timeout must be >= 0, got %r' % args.timeout,
                               'pass a non-negative number of seconds')
        if not args.session:
            return _emit_error('arg_error', 'missing --session',
                               '--watch needs the session token that the server printed',
                               'pass --session <token> from the [INFO] session line')
        return _run_watcher(args.watch, args.timeout, args.session)
    if args.session is not None:
        return _emit_error('arg_error', '--session needs --watch',
                           '--session only applies to watcher mode',
                           'pass --watch <file> --session <token>')
    if args.spec and args.options:
        return _emit_error('arg_error', '--spec and --options are mutually exclusive',
                           'pass --spec <json> for the batch page or --options <csv> '
                           'for the single-card page',
                           'use exactly one page mode flag')
    if not args.spec and args.round is None:
        return _emit_error('arg_error', 'no mode selected',
                           'pass --spec <json> or --round <N> (server) or '
                           '--watch <file> (watcher)',
                           'run: python serve_decision.py --help')
    spec = None
    if args.spec:
        try:
            spec = _load_spec(args.spec, static_root=args.static_root)
        except _SpecError as exc:
            return _emit_error('spec_error', 'invalid --spec file', str(exc),
                               'fix the spec JSON and retry (field types are '
                               'documented in scripts/manifest.json)',
                               errors=exc.issues)
        if args.round is None and spec['round'] is None:
            return _emit_error('arg_error', 'no round number',
                               'the spec has no "round" field and no --round override '
                               'was given',
                               'add "round" to the spec or pass --round <N>')
    if args.round is not None and args.round < 1:
        return _emit_error('arg_error', 'invalid --round value',
                           '--round must be a positive integer, got %r' % args.round,
                           'pass the decision round number (1, 2, ...)')
    if not 1 <= args.port <= 65535:
        return _emit_error('arg_error', 'invalid --port value',
                           '--port must be in 1..65535, got %r' % args.port,
                           'pass an available TCP port')
    if spec is not None:
        # Verify before it serves: the port never binds and the browser
        # never opens until every option url and the annotator toolbar
        # have passed the deterministic checks.
        issues = _prelaunch_checks(spec, args.static_root)
        if issues:
            return _emit_error('prelaunch_error',
                               'pre-launch checks failed',
                               'the console verifies option urls and the '
                               'annotator toolbar before it serves',
                               'fix the listed issues and retry',
                               errors=issues)
    return _run_server(args, spec)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
