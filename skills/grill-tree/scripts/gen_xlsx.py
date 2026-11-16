# Decision xlsx generator: builds three-sheet workbooks (Candidates / Measured / Notes) from a spec JSON.
"""gen_xlsx.py — decision-table xlsx generator.

Interface:
    python gen_xlsx.py --spec <spec.json> --out <workbook.xlsx>

spec JSON:
    {"candidates": [[header...], [row...] ...],   first row = header
     "measured":   [[header...], [row...] ...],   first row = header
     "notes":      ["...", ...]}

Output workbook, three sheets with fixed names:
    Candidates — candidates table
    Measured   — measured table
    Notes      — two columns (No., Content), one numbered row per note
Table header row: deep blue fill (1F4E78), white bold font.
Body cells: wrap_text. Number the notes starting at 1.

Exit codes: 0 = success; 2 = args / spec / path error
(stderr [ERR] marker line + JSON error object).
"""

import io
import json
import os
import sys

HEADER_FILL = HEADER_FONT = BODY_ALIGN = None
_WORKBOOK = None

SHEET_CANDIDATES = 'Candidates'
SHEET_MEASURED = 'Measured'
SHEET_NOTES = 'Notes'


class DependencyError(Exception):
    """Raised when the openpyxl package is missing on the interpreter."""


def _openpyxl():
    """Import openpyxl on first use and build the shared styles.

    The third-party dependency stays lazy so the error contract also works
    on an interpreter without the package (the bare run reports the missing
    dependency through the [ERR] payload instead of an import traceback).
    """
    global _WORKBOOK, HEADER_FILL, HEADER_FONT, BODY_ALIGN
    if _WORKBOOK is None:
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Alignment, Font, PatternFill
        except ImportError as exc:
            raise DependencyError(str(exc))
        _WORKBOOK = Workbook
        HEADER_FILL = PatternFill(fill_type='solid',
                                  start_color='FF1F4E78',
                                  end_color='FF1F4E78')
        HEADER_FONT = Font(bold=True, color='FFFFFFFF')
        BODY_ALIGN = Alignment(wrap_text=True, vertical='top')
    return _WORKBOOK


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
    """Parse --spec <json> --out <xlsx>; return (args, None) or (None, msg)."""
    flags = ('--spec', '--out')
    got = {}
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in flags:
            if i + 1 >= len(argv):
                return None, 'missing value for %s' % arg
            got[arg] = argv[i + 1]
            i += 2
        else:
            hit = next((f for f in flags if arg.startswith(f + '=')), None)
            if hit is None:
                return None, ('unknown argument: %s '
                              '(expected --spec <json> --out <xlsx>)' % arg)
            got[hit] = arg.split('=', 1)[1]
            i += 1
    for flag in flags:
        if flag not in got:
            return None, 'missing required argument %s' % flag
        if not got[flag]:
            return None, '%s value is empty' % flag
    return got, None


def _collect_cell_issues(value, where, issues):
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    issues.append({
        'loc': where, 'type': 'cell_type',
        'msg': 'cell value must be string/number/boolean/null, got %s'
               % type(value).__name__,
        'fix': 'replace the cell with a string, number, boolean or null'})


def _collect_table_issues(table, key, issues):
    if not isinstance(table, list):
        issues.append({
            'loc': key, 'type': 'shape',
            'msg': '%s must be a list of rows (first row = header)' % key,
            'fix': 'make "%s" an array of row arrays' % key})
        return
    if not table:
        issues.append({
            'loc': key, 'type': 'empty',
            'msg': '%s must contain at least a header row' % key,
            'fix': 'add a header row as the first array'})
        return
    for r, row in enumerate(table):
        if not isinstance(row, list):
            issues.append({
                'loc': '%s[%d]' % (key, r + 1), 'type': 'shape',
                'msg': 'row must be a list',
                'fix': 'make row %d an array of cells' % (r + 1)})
            continue
        for c, value in enumerate(row):
            _collect_cell_issues(value, '%s[%d][%d]' % (key, r + 1, c + 1),
                                 issues)


def _collect_spec_issues(spec):
    """Validate the spec contract; return (issues, notes). Every issue is
    collected, so the model repairs the whole spec in one round-trip."""
    issues = []
    if not isinstance(spec, dict):
        issues.append({
            'loc': 'spec', 'type': 'shape',
            'msg': 'spec root must be a JSON object',
            'fix': 'wrap candidates/measured/notes in one object'})
        return issues, []
    for key in ('candidates', 'measured'):
        if key not in spec:
            issues.append({
                'loc': key, 'type': 'missing',
                'msg': 'spec missing required key "%s"' % key,
                'fix': 'add the "%s" table' % key})
            continue
        _collect_table_issues(spec[key], key, issues)
    notes = spec.get('notes', [])
    if not isinstance(notes, list):
        issues.append({
            'loc': 'notes', 'type': 'shape',
            'msg': 'notes must be a list of strings',
            'fix': 'make "notes" an array of strings'})
        notes = []
    for i, note in enumerate(notes):
        if not isinstance(note, str):
            issues.append({
                'loc': 'notes[%d]' % (i + 1), 'type': 'type',
                'msg': 'note must be a string, got %s' % type(note).__name__,
                'fix': 'make every note a string'})
    return issues, notes


def _emit_issues(issues):
    """Write the [ERR] marker plus one all-at-once errors[] payload; exit 2."""
    sys.stderr.write('[ERR] spec violates contract\n')
    sys.stderr.write(json.dumps({'error': {'errors': issues}},
                                ensure_ascii=False) + '\n')
    return 2


def _cleanup_tmp(path):
    try:
        os.unlink(path)
    except OSError:
        pass


def _write_table(ws, table):
    """Write rows; row 1 gets header styling, the rest get wrap_text."""
    for r, row in enumerate(table, start=1):
        for c, value in enumerate(row, start=1):
            cell = ws.cell(row=r, column=c, value=value)
            if r == 1:
                cell.fill = HEADER_FILL
                cell.font = HEADER_FONT
            else:
                cell.alignment = BODY_ALIGN


def build_workbook(spec, notes):
    """Build the three-sheet workbook from a validated spec."""
    workbook_cls = _openpyxl()
    wb = workbook_cls()
    ws_candidates = wb.active
    ws_candidates.title = SHEET_CANDIDATES
    _write_table(ws_candidates, spec['candidates'])
    _write_table(wb.create_sheet(SHEET_MEASURED), spec['measured'])
    ws_notes = wb.create_sheet(SHEET_NOTES)
    _write_table(ws_notes, [['No.', 'Content']])
    for i, note in enumerate(notes, start=1):
        ws_notes.cell(row=i + 1, column=1, value=i).alignment = BODY_ALIGN
        ws_notes.cell(row=i + 1, column=2, value=note).alignment = BODY_ALIGN
    return wb


def main(argv):
    _setup_streams()
    args, err = _parse_args(argv)
    if err is not None:
        return _emit_error('arg_error', 'invalid arguments', err,
                           'run: python gen_xlsx.py --spec <spec.json> '
                           '--out <workbook.xlsx>')
    spec_path = args['--spec']
    out_path = args['--out']
    try:
        with io.open(spec_path, 'r', encoding='utf-8-sig') as handle:
            spec = json.load(handle)
    except FileNotFoundError:
        return _emit_error('file_error', 'spec file not found', spec_path,
                           'pass an existing spec JSON path to --spec')
    except IsADirectoryError:
        return _emit_error('file_error', 'spec path is a directory', spec_path,
                           'pass a file path, not a directory')
    except UnicodeDecodeError as exc:
        return _emit_error('file_error', 'spec file is not valid UTF-8',
                           '%s (%s)' % (spec_path, exc),
                           're-save the spec with UTF-8 encoding')
    except json.JSONDecodeError as exc:
        return _emit_error('spec_error', 'spec is not valid JSON',
                           '%s (%s)' % (spec_path, exc),
                           'fix the JSON syntax in the spec file')
    except OSError as exc:
        return _emit_error('file_error', 'cannot read spec file',
                           '%s (%s)' % (spec_path, exc),
                           'check file permissions')

    issues, notes = _collect_spec_issues(spec)
    if issues:
        return _emit_issues(issues)

    tmp_path = '%s.tmp' % out_path
    try:
        wb = build_workbook(spec, notes)
        wb.save(tmp_path)
        os.replace(tmp_path, out_path)
    except DependencyError as exc:
        _cleanup_tmp(tmp_path)
        return _emit_error('dependency_error', 'openpyxl is not installed',
                           str(exc),
                           'install the openpyxl package for this '
                           'interpreter (pip install openpyxl) or run the '
                           'script with an interpreter that has it')
    except OSError as exc:
        _cleanup_tmp(tmp_path)
        return _emit_error('file_error', 'cannot write workbook',
                           '%s (%s)' % (out_path, exc),
                           'check the output directory exists and is writable')
    except ValueError as exc:  # openpyxl rejects illegal control characters
        _cleanup_tmp(tmp_path)
        return _emit_error('spec_error', 'spec data rejected by openpyxl',
                           '%s (%s)' % (out_path, exc),
                           'remove control characters from spec strings')

    payload = {
        'ok': True,
        'command': 'gen_xlsx',
        'out': out_path,
        'sheets': [SHEET_CANDIDATES, SHEET_MEASURED, SHEET_NOTES],
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
