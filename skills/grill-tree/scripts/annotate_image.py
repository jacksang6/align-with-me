# Evidence annotation for decision-console screenshots (zero dependencies).
"""annotate_image.py - draw evidence boxes on a PNG screenshot.

Writes an SVG that embeds the source PNG at its natural size and draws one
red box per --box, each with a numbered label. The numbers pair with the
--note order; note text is logged to stdout only and belongs in the console
card's delta note, so the artifact carries markers, not paragraphs.

Usage:
    python -B annotate_image.py --img shot.png --out shot-a.svg \\
        --box 12,340,220,48 --note "toolbar moved here" \\
        --box 400,120,180,90

--box is x,y,w,h in image pixels; repeatable; at least one required.
--note is optional and pairs with the --box of the same order.
The input must be a PNG (the size is read from the IHDR header; no image
decoder is used). The output serves through the console /img endpoint like
any png. Exit codes: 0 success; 2 argument or file error ([ERR] + JSON on
stderr).
"""
import argparse
import base64
import json
import struct
import sys
from pathlib import Path

_PNG_SIG = b'\x89PNG\r\n\x1a\n'
_STROKE = '#d92d20'
_LABEL_R = 16


def _setup_streams():
    """Force UTF-8 on stdout/stderr (Windows consoles default to GBK)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError):
            pass


def _emit_error(error_type, title, detail, suggested_fix):
    """Write an [ERR] marker line + JSON error object to stderr; exit code 2."""
    payload = {'ok': False, 'error': {'type': error_type, 'title': title,
                                      'detail': detail,
                                      'suggested_fix': suggested_fix}}
    sys.stderr.write('[ERR] %s\n' % title)
    sys.stderr.write(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    return 2


def _png_size(data):
    """Width and height from the IHDR header (bytes 16-24, big-endian)."""
    if len(data) < 24 or not data.startswith(_PNG_SIG) or data[12:16] != b'IHDR':
        raise ValueError('not a valid PNG (no IHDR header)')
    return struct.unpack('>II', data[16:24])


def _parse_box(raw):
    parts = [p.strip() for p in str(raw).split(',')]
    if len(parts) != 4:
        raise ValueError('a box is x,y,w,h - got %r' % raw)
    try:
        x, y, w, h = (int(p) for p in parts)
    except ValueError:
        raise ValueError('box coordinates must be integers - got %r' % raw)
    if w <= 0 or h <= 0:
        raise ValueError('box w and h must be positive - got %r' % raw)
    return x, y, w, h


def _clamp_box(index, box, width, height, warns):
    """Keep the box inside the image; report every clamp, never fix silently."""
    x, y, w, h = box
    nx = max(0, x)
    ny = max(0, y)
    nw = min(w, width - nx)
    nh = min(h, height - ny)
    if (nx, ny, nw, nh) != (x, y, w, h):
        warns.append('box %d clamped to the image bounds' % index)
    return nx, ny, nw, nh


def _box_svg(number, x, y, w, h):
    """One red box with a numbered label badge at its top-left corner."""
    cx, cy = x + _LABEL_R + 2, y + _LABEL_R + 2
    return (
        '<rect x="%d" y="%d" width="%d" height="%d" rx="4" fill="none" '
        'stroke="%s" stroke-width="4"/>'
        '<circle cx="%d" cy="%d" r="%d" fill="%s"/>'
        '<text x="%d" y="%d" fill="#ffffff" font-family="system-ui, sans-serif" '
        'font-size="17" font-weight="700" text-anchor="middle" '
        'dominant-baseline="central">%d</text>'
        % (x, y, w, h, _STROKE, cx, cy, _LABEL_R, _STROKE, cx, cy, number))


def main(argv):
    _setup_streams()
    parser = argparse.ArgumentParser(
        prog='annotate_image.py',
        description='Draw numbered evidence boxes on a PNG screenshot.')
    parser.add_argument('--img', required=True, help='input PNG path')
    parser.add_argument('--out', help='output SVG path '
                        '(default: <img stem>-annotated.svg beside the input)')
    parser.add_argument('--box', action='append', default=[], metavar='X,Y,W,H',
                        help='box in image pixels; repeatable; at least one')
    parser.add_argument('--note', action='append', default=[], metavar='TEXT',
                        help='note for the box of the same order (stdout log '
                             'only; the words belong in the card delta note)')
    args = parser.parse_args(argv)
    if args.out is not None and Path(args.out).suffix.lower() != '.svg':
        return _emit_error(
            'arg_error', 'non-svg --out',
            'the console serves captures by extension, so the SVG payload '
            'must land under a .svg name (got %s)'
            % Path(args.out).suffix,
            'pass an --out path ending in .svg')
    if not args.box:
        return _emit_error('arg_error', 'no box given',
                           'at least one --box x,y,w,h is required',
                           'pass --box for every region that changed')
    src = Path(args.img)
    try:
        data = src.read_bytes()
    except OSError as exc:
        return _emit_error('file_error', 'cannot read the image',
                           str(exc), 'pass an existing PNG path in --img')
    try:
        width, height = _png_size(data)
    except ValueError as exc:
        return _emit_error('file_error', 'not a PNG', str(exc),
                           'convert the screenshot to PNG and retry')
    boxes = []
    for raw in args.box:
        try:
            boxes.append(_parse_box(raw))
        except ValueError as exc:
            return _emit_error('arg_error', 'invalid --box value', str(exc),
                               'pass --box x,y,w,h in image pixels')
    warns = []
    boxes = [_clamp_box(i + 1, b, width, height, warns)
             for i, b in enumerate(boxes)]
    out = (Path(args.out) if args.out
           else src.with_name('%s-annotated.svg' % src.stem))
    uri = 'data:image/png;base64,' + base64.b64encode(data).decode('ascii')
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" '
             'xmlns:xlink="http://www.w3.org/1999/xlink" width="%d" '
             'height="%d" viewBox="0 0 %d %d">'
             % (width, height, width, height),
             '<image xlink:href="%s" href="%s" x="0" y="0" width="%d" '
             'height="%d"/>' % (uri, uri, width, height)]
    parts += [_box_svg(i + 1, *b) for i, b in enumerate(boxes)]
    parts.append('</svg>')
    try:
        with open(out, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write('\n'.join(parts) + '\n')
    except OSError as exc:
        return _emit_error('file_error', 'cannot write the output', str(exc),
                           'pass a writable --out path')
    for warn in warns:
        sys.stdout.write('[WARN] %s\n' % warn)
    if len(args.note) > len(boxes):
        sys.stdout.write('[WARN] %d extra note(s) dropped: one --note '
                         'pairs with one --box by order\n'
                         % (len(args.note) - len(boxes)))
    for i, note in enumerate(args.note[:len(boxes)]):
        sys.stdout.write('[INFO] box %d - %s\n' % (i + 1, note))
    sys.stdout.write('[OK] wrote %s with %d box(es)\n' % (out, len(boxes)))
    sys.stdout.flush()
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
