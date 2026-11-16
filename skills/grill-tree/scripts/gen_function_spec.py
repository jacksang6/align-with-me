"""gen_function_spec.py - render the design-time function spec page.

Reads a decisions JSON and writes the standalone function-spec.html per
the format contract in references/uiux-tree.md: the replication banner,
the Confirmed decisions table (Seq / Stage / Decision / Why / Lands, one
row per confirmed decision in confirmation order), and the Criteria
section (C-id (tag): criterion - verify: method). The page is design-time
only and is never implemented into production.

Usage:
    python gen_function_spec.py --spec <json> --out <html>

Input JSON keys: topic (str, required); lang ("en" | "zh", default en);
decisions (non-empty array of {seq, stage, decision, why, lands}; lands
is a string or an array of strings; why and lands optional); criteria
(optional array of {cid, tag, criterion, verify}).

Validation is all-at-once: every issue is collected and one [ERR] payload
carrying error.errors[] = [{loc, type, msg, fix}] goes to stderr; the
output file is written only on a fully valid input. Behaviour contract:
scripts/manifest.json.
"""

import argparse
import html
import json
import sys
from pathlib import Path

_BANNER = {
    'en': 'AI replicates production 1:1 from this spec and the prototype '
          'HTML; design-time only: never implement this page or this tab.',
    'zh': 'AI \u53c2\u7167\u672c Function Spec \u4e0e\u539f\u578b HTML '
          '1:1 \u590d\u523b\u5b9e\u73b0\u5230\u751f\u4ea7\uff1b\u672c '
          'Function Spec \u9875\u9762\u4e0e\u5176 Tab \u6c38\u4e0d\u8fdb'
          '\u5165\u751f\u4ea7\u5b9e\u73b0\u3002',
}
_DECISIONS_HEAD = {
    'en': 'Confirmed decisions',
    'zh': '\u5df2\u786e\u8ba4\u51b3\u7b56',
}
_COLS = {
    'en': ['Seq', 'Stage', 'Decision', 'Why', 'Lands'],
    'zh': ['Seq', 'Stage', '\u51b3\u7b56', '\u7406\u7531',
           '\u843d\u5730\u89c4\u5219'],
}
_FOOT = {
    'en': 'Design-time page: the production build starts from the '
          'artifact without this page.',
    'zh': '\u8bbe\u8ba1\u65f6\u9875\u9762\uff1a\u751f\u4ea7\u5b9e\u73b0'
          '\u4ece\u539f\u578b\u672c\u4f53\u51fa\u53d1\uff0c\u4e0d\u5305'
          '\u542b\u672c\u9875\u3002',
}


def _bad(errors, loc, kind, msg, fix):
    errors.append({'loc': loc, 'type': kind, 'msg': msg, 'fix': fix})


def _lands_html(lands):
    if isinstance(lands, list):
        items = ''.join('<li>%s</li>' % html.escape(str(x)) for x in lands)
        return '<ul class="lands">%s</ul>' % items
    return html.escape(str(lands))


def _check_fields(data, errors):
    """Field-level checks on a dict spec root; collect, never raise.
    Returns the normalized (decisions, criteria) lists for rendering."""
    if not data.get('topic'):
        _bad(errors, ['topic'], 'missing',
             'topic is required', 'set "topic" to the surface name')
    decisions = data.get('decisions')
    if not isinstance(decisions, list) or not decisions:
        _bad(errors, ['decisions'], 'missing',
             'decisions must be a non-empty array',
             'add one object per confirmed decision')
        decisions = []
    for i, d in enumerate(decisions):
        if not isinstance(d, dict):
            _bad(errors, ['decisions', i], 'type',
                 'every decision must be an object',
                 'give decision %d seq/stage/decision fields' % (i + 1))
            continue
        for key in ('seq', 'stage', 'decision'):
            if not isinstance(d.get(key), str) or not d[key].strip():
                _bad(errors, ['decisions', i, key], 'missing',
                     '%s is required on every decision' % key,
                     'set "%s" to a non-empty string' % key)
        lands = d.get('lands', [])
        if lands and not isinstance(lands, (str, list)):
            _bad(errors, ['decisions', i, 'lands'], 'type',
                 'lands must be a string or an array of strings',
                 'use a string or ["rule one", "rule two"]')
        if d.get('stage') in ('S3', 'S4') and not d.get('probe') \
                and not d.get('evidence'):
            _bad(errors, ['decisions', i], 'evidence',
                 'an S3/S4 decision needs implementable evidence',
                 'add "probe" (path to the support-probe document) or '
                 '"evidence" (quoted file:line or command output)')
    criteria = data.get('criteria', [])
    if not isinstance(criteria, list):
        _bad(errors, ['criteria'], 'type',
             'criteria must be an array', 'use [] when none yet')
        criteria = []
    for i, c in enumerate(criteria):
        if not isinstance(c, dict):
            _bad(errors, ['criteria', i], 'type',
                 'every criterion must be an object',
                 'give criterion %d cid/tag/criterion/verify fields'
                 % (i + 1))
            continue
        for key in ('cid', 'tag', 'criterion', 'verify'):
            if not isinstance(c.get(key), str) or not c[key].strip():
                _bad(errors, ['criteria', i, key], 'missing',
                     '%s is required on every criterion' % key,
                     'set "%s" to a non-empty string' % key)
    return decisions, criteria


def _probe_link(path):
    """Design-time link to a decision's support-probe document (the
    verified API evidence beside the rule)."""
    if not path:
        return ''
    return ' <a class="probe" href="%s">support-probe</a>' % html.escape(
        str(path), quote=True)


def _evidence_block(decision):
    """The structured Evidence block: probe link, probe quote lines, and
    the confirmed capability name."""
    parts = [_probe_link(decision.get('probe', ''))]
    evidence = decision.get('evidence', [])
    if isinstance(evidence, list) and evidence:
        parts.append('<ul class="evq">%s</ul>' % ''.join(
            '<li>%s</li>' % html.escape(str(line)) for line in evidence))
    elif isinstance(evidence, str) and evidence.strip():
        parts.append('<ul class="evq"><li>%s</li></ul>'
                     % html.escape(evidence))
    if decision.get('api'):
        parts.append('<span class="api">API: %s</span>'
                     % html.escape(str(decision['api'])))
    return ''.join(parts)


_STATUS = {
    'en': ('OK', 'Pending'),
    'zh': ('\u5df2\u51b3\u5b9a', '\u5f85\u51b3\u5b9a'),
}

_LADDER_HEADS = {
    'en': ('Version', 'Title', 'Decision', 'Changes', 'Snapshot'),
    'zh': ('\u7248\u672c', '\u6807\u9898', '\u51b3\u5b9a', '\u6539\u52a8',
           '\u5feb\u7167'),
}


def _fragment_page(title, body):
    return ('<!DOCTYPE html><html><head><meta charset="utf-8">'
            '<title>%s</title><style>body { font: 14px/1.5 sans-serif; '
            'margin: 16px } table { border-collapse: collapse } '
            'td, th { border: 1px solid #ccc; padding: 4px 10px; '
            'text-align: left } .ok { color: #166534 } '
            '.pend { color: #92400e }</style></head><body>'
            '<h2>%s</h2>%s</body></html>' % (html.escape(title),
                                             html.escape(title), body))


def _write_alignment_fragment(alignment, lang, path):
    ok_label, pend_label = _STATUS.get(lang, _STATUS['en'])
    rows = ''
    for row in alignment:
        if not isinstance(row, dict):
            continue
        decision = row.get('decision')
        cell = ('<span class="ok">%s</span>' % html.escape(str(decision))
                if decision else
                '<span class="pend">%s</span>' % pend_label)
        rows += ('<tr><td>%s</td><td>%s</td><td>%s</td></tr>'
                 % (html.escape(str(row.get('seq', ''))),
                    html.escape(str(row.get('question', ''))), cell))
    body = ('<table><tr><th>Seq</th><th>Question</th><th>Decision</th>'
            '</tr>%s</table>' % rows)
    with open(path, 'w', encoding='utf-8', newline='\n') as handle:
        handle.write(_fragment_page('Decision Log', body))


def _write_ladder_fragment(ladder, lang, path):
    heads = _LADDER_HEADS.get(lang, _LADDER_HEADS['en'])
    head = ''.join('<th>%s</th>' % html.escape(h) for h in heads)
    rows = ''
    for entry in ladder:
        if not isinstance(entry, dict):
            continue
        snapshot = html.escape(str(entry.get('snapshot', '')), quote=True)
        rows += ('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td>'
                 '<td><a href="%s">%s</a></td></tr>'
                 % (html.escape(str(entry.get('version', ''))),
                    html.escape(str(entry.get('title', ''))),
                    html.escape(str(entry.get('decision', ''))),
                    html.escape(str(entry.get('changes', ''))),
                    snapshot, heads[4]))
    body = ('<table><tr>%s</tr>%s</table>'
            % (head, rows))
    with open(path, 'w', encoding='utf-8', newline='\n') as handle:
        handle.write(_fragment_page('Version Ladder', body))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--spec', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--alignment',
                        help='alignment JSON ({"alignment": [{seq, question, '
                             'decision}]}) -> writes <out-stem>-decision-log'
                             '.html beside the spec page')
    parser.add_argument('--ladder',
                        help='ladder JSON ({"ladder": [{version, title, '
                             'decision, changes, snapshot}]}) -> writes '
                             '<out-stem>-version-ladder.html; snapshot '
                             'paths resolve against the ladder JSON folder')
    args = parser.parse_args()
    errors = []
    try:
        data = json.loads(Path(args.spec).read_text(encoding='utf-8'))
    except OSError as exc:
        _bad(errors, ['spec'], 'io', 'spec file unreadable', str(exc))
        data = None
    except json.JSONDecodeError as exc:
        _bad(errors, ['spec'], 'json', 'spec is not valid JSON', str(exc))
        data = None
    if data is not None:
        if not isinstance(data, dict):
            _bad(errors, ['spec'], 'type', 'spec must be a JSON object',
                 'wrap the fields in one object')
        else:
            decisions, criteria = _check_fields(data, errors)
    lang = data.get('lang', 'en') if isinstance(data, dict) else 'en'
    if lang not in _BANNER:
        lang = 'en'
    alignment_rows = None
    if args.alignment:
        try:
            adata = json.loads(Path(args.alignment).read_text(
                encoding='utf-8-sig'))
            alignment_rows = (adata.get('alignment', [])
                              if isinstance(adata, dict) else [])
        except (OSError, ValueError) as exc:
            _bad(errors, ['alignment'], 'io', 'alignment file unreadable',
                 str(exc))
            alignment_rows = []
    ladder_rows = None
    if args.ladder:
        try:
            ldata = json.loads(Path(args.ladder).read_text(
                encoding='utf-8-sig'))
            ladder_rows = (ldata.get('ladder', [])
                           if isinstance(ldata, dict) else [])
        except (OSError, ValueError) as exc:
            _bad(errors, ['ladder'], 'io', 'ladder file unreadable', str(exc))
            ladder_rows = []
        base = Path(args.ladder).parent
        for entry in ladder_rows:
            if isinstance(entry, dict) and entry.get('snapshot'):
                if not (base / str(entry['snapshot'])).is_file():
                    _bad(errors, ['ladder'], 'ladder',
                         'ladder snapshot missing: %s' % entry['snapshot'],
                         'keep one snapshot per confirmed round beside '
                         'the ladder JSON')
    if errors:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        print('[ERR] function spec input invalid', file=sys.stderr)
        print(json.dumps({'error': {'errors': errors}}, ensure_ascii=False),
              file=sys.stderr)
        return 2

    rows = ''.join(
        '<tr><td>%s</td><td>%s</td><td class="dec">%s</td><td>%s</td>'
        '<td>%s%s</td></tr>' % (
            html.escape(d['seq']), html.escape(d['stage']),
            html.escape(d['decision']),
            html.escape(d.get('why', '')) or '&mdash;',
            _lands_html(d.get('lands', [])) or '&mdash;',
            _evidence_block(d))
        for d in decisions)
    crit = ''.join(
        '<li><b>%s (%s):</b> %s &mdash; verify: %s</li>' % (
            html.escape(c['cid']), html.escape(c['tag']),
            html.escape(c['criterion']), html.escape(c['verify']))
        for c in criteria)
    crit_html = ('<h2>Criteria</h2><ul class="crit">%s</ul>' % crit
                 if crit else '')
    page = '''<!DOCTYPE html>
<html lang="%(lang)s">
<head>
<meta charset="utf-8">
<title>Function Spec (Aligned) &middot; %(topic)s</title>
<style>
  body { font: 14px/1.6 system-ui, sans-serif; color: #333;
    max-width: 900px; margin: 24px auto; padding: 0 24px; }
  h1 { font-size: 20px; margin-bottom: 2px; }
  h2 { font-size: 15px; margin: 22px 0 8px; }
  .banner { border: 1.5px solid #b45309; background: #fffbeb;
    color: #7c3e00; border-radius: 8px; padding: 12px 16px;
    margin: 12px 0 20px; font-weight: 600; }
  table { border-collapse: collapse; width: 100%%; }
  th, td { border: 1px solid #ccc; padding: 7px 10px;
    text-align: left; vertical-align: top; font-size: 13px; }
  th { background: #f2f2f2; }
  td.dec { font-weight: 600; }
  ul.lands { margin: 0; padding-left: 16px; }
  ul.crit { padding-left: 18px; }
  ul.crit li { margin: 5px 0; }
  .foot { color: #888; font-size: 12px; margin-top: 26px; }
</style>
</head>
<body>
<h1>Function Spec (Aligned) &middot; %(topic)s</h1>
<div class="banner">%(banner)s</div>
<h2>%(decisions_head)s</h2>
<table>
<tr><th>%(c0)s</th><th>%(c1)s</th><th>%(c2)s</th><th>%(c3)s</th><th>%(c4)s</th></tr>
%(rows)s
</table>
%(crit_html)s
<p class="foot">%(foot)s</p>
</body>
</html>
''' % {
        'lang': lang,
        'topic': html.escape(str(data['topic'])),
        'banner': _BANNER[lang],
        'decisions_head': _DECISIONS_HEAD[lang],
        'c0': _COLS[lang][0], 'c1': _COLS[lang][1], 'c2': _COLS[lang][2],
        'c3': _COLS[lang][3], 'c4': _COLS[lang][4],
        'rows': rows, 'crit_html': crit_html, 'foot': _FOOT[lang],
    }
    out = Path(args.out)
    written = [out]
    try:
        if out.parent and not out.parent.exists():
            out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page, encoding='utf-8')
        if alignment_rows is not None:
            frag = out.with_name('%s-decision-log.html' % out.stem)
            _write_alignment_fragment(alignment_rows, lang, frag)
            written.append(frag)
        if ladder_rows is not None:
            frag = out.with_name('%s-version-ladder.html' % out.stem)
            _write_ladder_fragment(ladder_rows, lang, frag)
            written.append(frag)
    except OSError as exc:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        print('[ERR] function spec not written', file=sys.stderr)
        print(json.dumps({'error': {'errors': [
            {'loc': str(out), 'type': 'io', 'msg': str(exc),
             'fix': 'pass a writable --out file path, not a directory'}]}},
            ensure_ascii=False), file=sys.stderr)
        return 2
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    for path in written:
        print('[OK] written: %s' % path)
    return 0


if __name__ == '__main__':
    sys.exit(main())
