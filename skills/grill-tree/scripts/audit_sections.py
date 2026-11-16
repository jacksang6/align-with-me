# Section audit tool for skill files: splits frontmatter/headings into sections, checks reconciliation.
"""audit_sections.py — SKILL.md section inventory.

Interface:
    python audit_sections.py --file <path>

stdout on success (exit code 0), one JSON object:
    {"file": <path>,
     "total_lines": N,
     "sections": [{"name": str, "start": int, "end": int, "lines": int}, ...],
     "blank_lines": N,
     "reconcile": true|false}

Split rules:
    1. Frontmatter: the first line "---" through the next "---" line is one
       section named "frontmatter". Unclosed frontmatter means no
       frontmatter section; content splits normally.
    2. After frontmatter, every "## "/"### " heading line starts a new
       section; the section name is the heading text. "#### " and deeper
       stay inside their section.
    3. Lines between frontmatter and the first heading form a "preamble"
       section (dropped when blank-only).
    4. Continuous blank-line runs that separate sections are counted into
       blank_lines; blank lines inside a section body stay in that section.
    5. reconcile = sum(section lines) + blank_lines == total_lines.

Exit codes: 0 = success; 2 = missing args / file error
(stderr [ERR] marker line + JSON error object).
"""

import io
import json
import sys


def _setup_streams():
    """Force UTF-8 on stdout/stderr (Windows consoles default to GBK)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError):
            pass


def _emit_error(error_type, title, detail, suggested_fix):
    """Write an [ERR] marker line + JSON error object to stderr; exit 2."""
    payload = {
        'ok': False,
        'error': {
            'type': error_type,
            'title': title,
            'detail': detail,
            'suggested_fix': suggested_fix,
        },
    }
    sys.stderr.write('[ERR] %s\n' % title)
    sys.stderr.write(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    return 2


def _parse_args(argv):
    """Parse --file <path>; return (args_dict, None) or (None, message)."""
    got = {}
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == '--file':
            if i + 1 >= len(argv):
                return None, 'missing value for --file'
            got['file'] = argv[i + 1]
            i += 2
        elif arg.startswith('--file='):
            got['file'] = arg.split('=', 1)[1]
            i += 1
        else:
            return None, 'unknown argument: %s (expected --file <path>)' % arg
    if 'file' not in got:
        return None, 'missing required argument --file <path>'
    if not got['file']:
        return None, '--file value is empty'
    return got, None


def _split(lines):
    """Split lines into sections per the rules; return (sections, blanks)."""
    total = len(lines)

    def blank(idx):
        return lines[idx].strip() == ''

    raw = []  # (name, start0, end0_exclusive); contiguous coverage of 0..total
    cursor = 0
    if total and lines[0].strip() == '---':
        close = None
        for i in range(1, total):
            if lines[i].strip() == '---':
                close = i
                break
        if close is not None:
            raw.append(('frontmatter', 0, close + 1))
            cursor = close + 1
    heads = [i for i in range(cursor, total)
             if lines[i].startswith('## ') or lines[i].startswith('### ')]
    raw.append(('preamble', cursor, heads[0] if heads else total))
    for k, head in enumerate(heads):
        end = heads[k + 1] if k + 1 < len(heads) else total
        raw.append((lines[head].lstrip('#').strip(), head, end))

    sections = []
    blank_lines = 0
    for name, start, end in raw:
        while end > start and blank(end - 1):  # separating run -> blank_lines
            blank_lines += 1
            end -= 1
        while start < end and blank(start):
            blank_lines += 1
            start += 1
        if end > start:
            sections.append({'name': name, 'start': start + 1, 'end': end,
                             'lines': end - start})
    return sections, blank_lines


def main(argv):
    _setup_streams()
    args, err = _parse_args(argv)
    if err is not None:
        return _emit_error('arg_error', 'invalid arguments', err,
                           'run: python audit_sections.py --file <path>')
    path = args['file']
    try:
        with io.open(path, 'r', encoding='utf-8-sig') as handle:
            text = handle.read()
    except FileNotFoundError:
        return _emit_error('file_error', 'file not found', path,
                           'pass an existing SKILL.md path to --file')
    except IsADirectoryError:
        return _emit_error('file_error', 'path is a directory', path,
                           'pass a file path, not a directory')
    except UnicodeDecodeError as exc:
        return _emit_error('file_error', 'file is not valid UTF-8',
                           '%s (%s)' % (path, exc),
                           're-save the file with UTF-8 encoding')
    except OSError as exc:
        return _emit_error('file_error', 'cannot read file',
                           '%s (%s)' % (path, exc), 'check file permissions')

    lines = text.splitlines()
    sections, blank_lines = _split(lines)
    accounted = sum(sec['lines'] for sec in sections) + blank_lines
    payload = {
        'file': path,
        'total_lines': len(lines),
        'sections': sections,
        'blank_lines': blank_lines,
        'reconcile': accounted == len(lines),
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
