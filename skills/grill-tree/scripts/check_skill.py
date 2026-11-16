"""Maintainer checks for the grill-tree skill.

Run from any folder:  python -B scripts/check_skill.py [--live]

Stdlib only. Every path comes from this file's location, the home folder or the
temp folder, so the checks run unchanged on any machine. --live adds two browser
checks (needs playwright): the rendered page, and the real server started on the
fixture spec. Live checks click options only. They never submit, and they fail
if a run writes an answers file.
"""
import io
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import Request, urlopen

sys.dont_write_bytecode = True
SKILL = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL / 'scripts'
WORK = Path(tempfile.gettempdir()) / 'grill-tree-check'
ANSWERS_ROUND = Path(tempfile.gettempdir()) / 'opencode' / 'answers-round9.json'
PNG_1PX = ('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ'
           'AAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')


def png_bytes(width, height):
    """Zero-dependency solid-color PNG for page fixtures."""
    import struct
    import zlib
    raw = b''.join(b'\x00' + b'\xcc\xd4\xe0' * width
                   for _ in range(height))

    def chunk(tag, data):
        body = tag + data
        return (struct.pack('>I', len(data)) + body
                + struct.pack('>I', zlib.crc32(body) & 0xffffffff))
    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 9))
            + chunk(b'IEND', b''))
LIVE = '--live' in sys.argv
SELF = 'check_skill.py'
CJK_RE = re.compile(r'[\u4e00-\u9fff]')
LONE_LF_RE = re.compile(r'(?<!\r)\n')
ABS_PATH_RE = re.compile(r'(?<![A-Za-z])[A-Za-z]:[\\/][A-Za-z]|Users[\\/]|sangj|lenovo|Jack|Jarvis|vault|butler')
failed = []


def check(name, ok, detail=''):
    print(('[OK] ' if ok else '[ERR] ') + name + ((' - ' + detail) if detail else ''))
    if not ok:
        failed.append(name)


def read(path):
    with io.open(str(path), encoding='utf-8', newline='') as handle:
        return handle.read()


def write(path, text):
    with io.open(str(path), 'w', encoding='utf-8', newline='') as handle:
        handle.write(text)


def text_files():
    files = [SKILL / 'SKILL.md', SKILL / 'AGENTS.md', SCRIPTS / 'manifest.json']
    files += sorted((SKILL / 'references').glob('*.md'))
    files += sorted(SCRIPTS.glob('*.py'))
    return [path for path in files if path.exists()]


def static_checks():
    serve = SCRIPTS / 'serve_decision.py'
    try:
        compile(read(serve), str(serve), 'exec')
        check('serve_decision.py compiles', True)
    except SyntaxError as exc:
        check('serve_decision.py compiles', False, str(exc))
    source = read(serve)
    for symbol in ['def _render_alignment', 'def _strip_example_label', 'def _sublist',
                   'def _extract_ask', 'chip pend', 'class="evbadge"',
                   'submitted = False', "'.webp': 'image/webp'",
                   "spec.get('alignment')", 'function syncAlignment']:
        check('code has: ' + symbol, symbol in source)
    # The rule that hides the native radio must not catch the write-in
    # text input (it once did: the input rendered absolute + opacity 0).
    check('CSS hides only the native radio, never the write-in input',
          '.opt input[type=radio] { position: absolute' in source
          and '.opt input { position: absolute' not in source)
    check('code has: KPI row, in-bar card nav, card-enter animation',
          'class="kpi"' in source and 'data-cnav' in source
          and 'id="navprev"' not in source and 'card-enter' in source)
    check('code has: hover-collapsible alignment with spring rows',
          '.alignwrap' in source and 'grid-template-rows:0fr' in source
          and 'cubic-bezier(.2,1.2,.4,1)' in source)
    check('code has: image-only write-in fallback',
          "choice = '(image answer)'" in source
          and source.count("'(image answer)'") >= 2)
    check('code has: paste selects the write-in radio',
          'ownRadio.checked = true' in source)
    check('render: qid chip capitalizes and leads the review row',
          'text-transform: capitalize' in source
          and source.index('row.appendChild(q);')
          < source.index('row.appendChild(main);'))
    check('uiux-tree.md captures the own artifact, not the user original',
          "never the user's supplied original" in read(
              SKILL / 'references' / 'uiux-tree.md')
          and 'only when the question is about that original' in read(
              SKILL / 'references' / 'uiux-tree.md'))
    uiux_all = read(SKILL / 'references' / 'uiux-tree.md')
    check('uiux-tree.md designs for a user who has never heard of an agent',
          'Novice-first design' in uiux_all
          and 'never heard of an agent' in uiux_all
          and 'zero technical terms' in uiux_all
          and 'has never heard of an agent' in uiux_all)
    check('uiux-tree.md carries the unified design principles module',
          '### Design principles' in uiux_all
          and 'Human-machine principles' in uiux_all
          and 'Human-agent principles' in uiux_all
          and 'Visual and interface principles' in uiux_all)
    check('uiux-tree.md self-checks before it asks',
          'Self-check before ask' in uiux_all
          and 'never reaches the user' in uiux_all
          and 'page errors' in uiux_all)
    check('uiux-tree.md maintains the function spec',
          '### Function spec' in uiux_all
          and 'never drift' in uiux_all and 'written twin' in uiux_all)
    # The function spec is a DESIGN-TIME page beside the artifact: it never
    # enters the 1:1 production mirror, so an implementer cannot mistake it
    # for a page to build.
    check('uiux-tree.md serves the function spec as a design-time page',
          'function-spec.html' in uiux_all
          and 'never implement this page' in uiux_all
          and 'Function Spec (Aligned)' in uiux_all)
    check('uiux-tree.md rides the spec as a design-time tab on greenfield',
          'Function Spec" tab' in uiux_all
          and 'the real page is never decorated with design chrome' in uiux_all)
    check('uiux-tree.md refinement evidence opens the real page',
          'never a rebuilt mockup' in uiux_all)
    check('uiux-tree.md annotation view is entry-uniform',
          'behaves identically in both entries' in uiux_all)
    check('uiux-tree.md opens the prototype round when words cannot say it',
          'request a generated prototype' in uiux_all
          and 'copied 1:1 with the change applied' in uiux_all
          and 'header tab row' in uiux_all)
    check('uiux-tree.md regenerates only the commented variant',
          'regenerates only the commented variant' in uiux_all
          and 'never assumes it understood' in uiux_all)
    # A prototype request starts with the scope ask: the user chooses
    # between a full rebuild, a marked-part prototype, and folding the
    # change into the confirmed prototype (the default).
    check('uiux-tree.md asks the prototype scope before generating',
          'Scope ask' in uiux_all
          and 'rebuild every prototype from the first stage' in uiux_all
          and 'prototype only the marked part' in uiux_all
          and 'fold the change into the confirmed prototype' in uiux_all
          and 'Nothing is generated until it is answered' in uiux_all)
    check('uiux-tree.md returns the confirmed prototype to the real page',
          'implemented 1:1 into the real page' in uiux_all
          and 'never enter the production mirror' in uiux_all)
    # The deployment mirror check: the confirmed artifact is deployed, then a
    # scripted browser regression compares the deployed page against the
    # acceptance baseline (prototype HTML plus function spec) 1:1.
    check('uiux-tree.md pairs a deployment mirror check in the criteria pool',
          'Deployment mirror check' in uiux_all
          and 'prototype HTML plus its function spec' in uiux_all
          and 'any drift fails' in uiux_all)
    # The function spec banner tells the implementer the replication source:
    # production is replicated 1:1 from the spec and the prototype HTML,
    # while the spec page and its tab never enter production.
    check('uiux-tree.md banner tells the implementer the replication source',
          'AI replicates production 1:1 from this spec and the prototype HTML'
          in uiux_all
          and 'never implement this page or this tab' in uiux_all)
    check('code has: AI evidence boxes on the annotate page',
          "'ai_boxes'" in source and 'grill-ai-box' in source
          and 'grill-ai-clear' in source and 'grill-ai-restore' in source
          and "'fmt_ai_count':" in source)
    # Three annotation tools: box, arrow, eraser (erases user marks and
    # AI marks alike), as toolbar modes.
    check('code has: box/arrow/eraser tool modes on the annotate page',
          'grill-tool-arrow' in source and 'grill-tool-eraser' in source
          and 'grill-ann-arrow' in source and "'tool_box':" in source
          and "'tool_arrow':" in source and "'tool_eraser':" in source)
    # Tool buttons carry icons, never text labels: the content comes from
    # the icon set (box and eraser joined the set), the name survives in
    # title and aria-label only.
    check('code has: icon-only tool buttons fed by the icon set',
          'aria-label="%(tool_box)s">%(tool_box_ic)s' in source
          and 'aria-label="%(tool_arrow)s">%(tool_arrow_ic)s' in source
          and 'aria-label="%(tool_eraser)s">%(tool_eraser_ic)s' in source
          and "'box':" in source and "'eraser':" in source
          and re.search(r'id="grill-tool-box"[^>]*>%\(tool_box\)s<', source)
          is None)
    # Icon-only buttons carry the tool alone, so the icon reads at full
    # weight. The size follows the console's m size class (15px, var
    # --icon-size-m): the tools bar matches the console's icon family and
    # never drifts back to an oversized 20px.
    check('code has: full-weight 15px tool icons on the tools bar',
          re.search(r'\.tool-ic \{ width: 15px; height: 15px;', source)
          is not None)
    # The tools live in their own bar at the top of the page, shown only
    # while Annotate is on: idle pages keep the full canvas visible.
    check('code has: separate top tools bar hidden until Annotate is on',
          'grill-ann-toolbar-top' in source
          and re.search(r'#grill-ann-toolbar-top \{[^}]*display: none',
                        source) is not None
          and re.search(r'body\.grill-ann-on #grill-ann-toolbar-top \{ display: flex',
                        source) is not None
          and 'grill-tool-group' in source)
    # Verify before it serves: deterministic pre-launch gates on every
    # option url and on the annotator toolbar's completeness.
    check('code has: pre-launch url and toolbar verification',
          '_prelaunch_checks' in source and '_PRELAUNCH_ANN_IDS' in source
          and '_annotator_injection' in source
          and '_PRELAUNCH_PROBE_TIMEOUT' in source)
    # Undo and redo: every structural annotation step (add, erase, resize)
    # is reversible; buttons on the tools bar plus Ctrl+Z / Ctrl+Y parity.
    check('code has: undo and redo on the annotate tools bar',
          "'grill-ann-undo'" in source and "'grill-ann-redo'" in source
          and "'undo':" in source and "'redo':" in source
          and "'ann_undo':" in source and "'ann_redo':" in source
          and 'undoStack' in source and 'redoStack' in source
          and 'ctrlKey' in source)
    # A drawn box is resizable: a corner grip rides the box while Annotate
    # is on; dragging it resizes the box (never redraw from scratch).
    check('code has: a resize grip on drawn annotation boxes',
          'grill-ann-grip' in source and "'resize'" in source)
    # Visual AI annotation kinds: a positional change renders as a move
    # arrow (from -> to), an icon suggestion renders the real icon in
    # place, a color suggestion renders current and suggested swatches
    # with a small hex line. Words never carry these; the code stays in
    # the spec for implementation.
    check('code has: visual AI annotation kinds move/icon/color',
          "'move'" in source and "'icon'" in source and "'color'" in source
          and 'grill-ai-move' in source and 'grill-ai-icon' in source
          and 'grill-ai-color' in source)
    check('code has: color swatches with a small hex line',
          'grill-ai-swatch' in source and 'grill-ai-hex' in source)
    # The eraser reaches the AI marks: while the eraser tool is on the
    # marks become hit-testable, and the tool branch runs before the
    # mark-skip so the skip never shadows the eraser.
    check('code has: eraser reach over the AI mark layer',
          'eraser-on' in source and "'eraser') {" in source)
    # Generate prototype: an annotate-page action that saves the marks,
    # flags the option, and returns; the console shows a chip and the
    # submitted answer carries the request.
    check('code has: generate-prototype action on the annotate page',
          'grill-ann-proto' in source and "'proto_gen':" in source
          and "'proto_gen_title':" in source)
    check('code has: prototype request chip and badge on the console',
          "'proto_requested':" in source and "'proto_badge':" in source)
    check('code has: full-width hover strip, capitalized title, KPI breathing',
          '.alignstrip { display: flex; width: 100%;' in source
          and 'margin: 12px auto 18px' in source
          and '.pcount { position: absolute' in source)
    check('code has: white surfaces, segmented progress, merged strip border',
          '--card: #fff' in source
          and '100deg, var(--tint-blue), #f4efff' not in source
          and '.pseg.on' in source
          and 'border-radius: 0 0 10px 10px' in source)
    check('code has: check and clock icons in the set',
          "'check':" in source and "'clock':" in source)
    check('code has: centered ask icon and clickable titled segments',
          '.dq { display: flex; gap: 12px; align-items: center;' in source
          and "seg.setAttribute('role', 'button')" in source
          and 'seg.title =' in source)
    check('code has: numbered bullet support', "'bl num'" in source
          and '.bl.num::before' in source)
    check('code has: prominent progress bar and ask subtitle',
          '.pbar { display: flex; gap: 3px' in source
          and '.pcount { position: absolute; right: 24px' in source
          and '.dqask { margin: 8px 0 0; font-size: 16px' in source)
    # Chrome copy follows the page language: every fixed string the console
    # page shows comes from the en/zh table picked by the spec lang.
    check('code has: chrome copy table selected by page lang',
          '_CHROME = {' in source and 'def _chrome_lang(' in source
          and 'def _t(lang, key)' in source)
    # Spec validation is pydantic-style: every issue is collected with a
    # JSON loc path and reported ALL at once as error.errors[] on the
    # [ERR] payload, so the orchestrating model repairs the whole spec in
    # one round-trip.
    check('code has: pydantic-style all-at-once spec issues',
          'def bad(loc, kind, msg, fix)' in source
          and 'errors=exc.issues' in source)
    check('code has: ic-xs icon size rule for the alignment chips',
          'svg.ic-xs' in source)
    check('code has: JS-synced alignment chips carry icons',
          'ICONS.check' in source and 'ICONS.clock' in source
          and 'chip.innerHTML' in source)
    check('code has: question block and ask subtitle without background fill',
          re.search(r'\.dq \{[^}]*background: none', source) is not None
          and re.search(r'\.dqask \{[^}]*background: none', source) is not None)
    # The saved badge is the loud "done, click to continue" signal: green
    # (the palette's ok family), not the annotator's amber.
    check('code has: saved badge in the green ok family',
          re.search(r'\.savebadge \{[^}]*var\(--okbg\)', source) is not None
          and re.search(r'\.savebadge \{[^}]*var\(--ok\)', source) is not None
          and not re.search(r'\.savebadge \{[^}]*#f59e0b', source))
    # The annotation caption grows with its text AND the user can drag it
    # wider/taller (a narrow fixed box truncated long notes).
    check('code has: draggable resizable annotation caption',
          re.search(r'\.grill-ann-cap \{[^}]*resize: both', source)
          is not None)
    # The fold frame lives on the table INSIDE the overflow-hidden clipper:
    # a frame on the clipper itself would paint its own border even when the
    # fold is collapsed (a stray line poking out beside the strip's rounded
    # corners). The clipper carries neither border nor background.
    check('code has: fold frame on the clipped table, bare clipper',
          re.search(r'\.align table \{[^}]*border: 1px solid var\(--line\)',
                    source) is not None
          and not re.search(r'\.alignfold \.align \{[^}]*border', source)
          and not re.search(r'\.alignfold \.align \{[^}]*background', source))
    manifest = read(SCRIPTS / 'manifest.json')
    try:
        json.loads(manifest)
        check('manifest.json is valid JSON', True)
    except ValueError as exc:
        check('manifest.json is valid JSON', False, str(exc))
    # Drift guard: script-owned behaviour must be reachable from the manifest.
    check('manifest documents --static-root', '--static-root' in manifest)
    check('manifest documents annotate_image.py', 'annotate_image.py' in manifest)
    check('manifest documents spec field types',
          'string or an array of strings' in manifest)
    check('manifest documents the wireframe evidence mode',
          'wireframe' in manifest and 'the wireframe self-annotates' in manifest)
    check('manifest documents the visual annotation kinds',
          'box, move, icon and color' in manifest)
    check('manifest documents the generate-prototype request',
          'prototype request' in manifest)
    check('manifest keeps image a file location, never a web route',
          'never a web route' in manifest)
    check('manifest documents the paste-to-answer contract',
          'paste or drop' in manifest and 'images' in manifest
          and 'dataURL' in manifest)
    check('code has: paste zone collector and image sink',
          'pastezone' in source and 'entry.images = cardImages[i]' in source
          and 'def _save_answer_images' in source)
    check('code has: annotation overlay and sink',
          '_ANNOTATOR_ASSET' in source and 'annotate=1' in source
          and 'def _handle_annotations' in source)
    # The caption note is a growing textarea: typed text wraps, the box
    # grows with the content (a single-line input truncated long notes),
    # Enter finishes, Shift+Enter breaks the line, and the self-capture
    # serializes the live value into the DOM text node.
    check('code has: annotation caption as a growing wrapping textarea',
          "cap = document.createElement('textarea')" in source
          and 'cap.style.height = cap.scrollHeight' in source
          and 'c.textContent = c.value' in source
          and "ev.key === 'Enter' && !ev.shiftKey" in source
          and re.search(r'\.grill-ann-cap \{[^}]*white-space: pre-wrap',
                        source) is not None)
    check('code has: linkrow right alignment css',
          '.linkrow { display: flex; justify-content: flex-end' in source)
    check('code has: one merged annotate-capable openlink with icon',
          "'/static/%s%sannotate=1&q=%d&o=%d'" in source
          and 'annotatelink' not in source
          and "_icon('pencil'" in source)
    check('code has: blue annotate entry (no amber class), pencil icon',
          '.openlink.amber' not in source
          and 'def _handle_annotations' in source
          and "_icon('pencil'" in source)
    # The saved badge leads with a circled checkmark, then the text.
    check('code has: circled-check icon leading the saved badge',
          "'circle_check':" in source and 'ICONS.circle_check' in source)
    # The entry link names the capability, not the mechanism (user ruling):
    # "view and annotate in the interactive interface". The zh copy lives
    # in the script as a \uXXXX escape, so the pin matches the escape text.
    check('code has: capability-named annotate entry copy',
          "'\\u5728\\u53ef\\u4ea4\\u4e92\\u754c\\u9762\\u67e5\\u770b"
          "\\u5e76\\u6279\\u6ce8'" in source)
    check('code has: two-button annotator (toggle + save-replace), no choose',
          '/annotations/view' not in source
          and 'View in tab' not in source
          and 'grill-ann-choose' not in source and 'grillChoose' not in source
          and 'grill-ann-toggle' in source and 'grill-ann-save' in source
          and "addEventListener('message'" in source)
    # A quiet return exit: browsing the artifact without annotating must
    # still land the user back on the console (focus + close, no save).
    check('code has: a quiet return-to-console exit on the annotate toolbar',
          'grill-ann-return' in source
          and "'ann_return':" in source
          and 'returnBtn' in source)
    check('code has: save flow - self capture, swap evidence, ride the answer',
          'function capturePage' in source
          and 'grillSave' in source
          and 'optCaptures' in source
          and 'annotated-capture.png' in source
          and 'savebadge' in source and 'suppressAdvanceOnce' in source
          and 'savetoast' not in source)
    # The save must land the user back on the console tab: the console page
    # names its window, the annotate tab opens script-side (closable), and
    # Save focuses the console by name then closes the annotate tab.
    check('code has: save returns to the console tab and closes the tab',
          "'grill-console'" in source and 'window.name' in source
          and 'window.open(' in source and 'window.close()' in source)
    check('code has: Enter confirms an annotation caption',
          'cap.blur()' in source)
    check('manifest documents the annotation overlay contract',
          'annotate=1' in manifest and 'Save and replace' in manifest
          and 'amber' in manifest and '/annotations' in manifest
          and 'grillSave' in manifest)
    check('manifest documents the gen_xlsx input shape',
          'candidates/measured/notes' in manifest)
    # The design tree is the session spine: every branch walks its process
    # as an overlay, never a replacement; the alignment table must reach the
    # console spec every round (user-facing alignment surface).
    spine = read(SKILL / 'SKILL.md')
    check('SKILL.md makes the design tree the spine of every branch',
          'Every round of every branch walks the design tree' in spine)
    for name in ('uiux-tree.md', 'logic-tree.md', 'doc-tree.md'):
        branch = read(SKILL / 'references' / name)
        check(name + ' runs as a design-tree overlay',
              'walk the design tree' in branch)
    uiux_bind = read(SKILL / 'references' / 'uiux-tree.md')
    check('uiux-tree.md mandates alignment rows in every console spec',
          'every console spec carries' in uiux_bind)
    # "Layout" has exactly one meaning: the region wireframe (which region
    # holds what), and S1's confirmed output is that wireframe.
    check('uiux-tree.md defines layout as the region wireframe',
          'Layout means the region map' in uiux_bind)
    check('uiux-tree.md wireframe is skeleton-only (no content, no styling)',
          'no concrete content and no visual styling' in uiux_bind
          and 'not the artifact' in uiux_bind)
    s1_row = re.search(r'^\| S1 .*$', uiux_bind, re.MULTILINE)
    check('uiux-tree.md S1 row outputs the region wireframe',
          bool(s1_row) and 'region wireframe' in s1_row.group(0))
    check('uiux-tree.md S1 row declares each region semantic assumptions',
          bool(s1_row) and 'semantic assumption' in s1_row.group(0)
          and 'logic sub-round' in s1_row.group(0))
    check('uiux-tree.md layout never rests on an unstated premise',
          'unstated premise' in uiux_bind)
    check('uiux-tree.md gates stage advance on realization',
          'Realization gate' in uiux_bind
          and 'realized in the artifact' in uiux_bind
          and 'never a redrawn frame' in uiux_bind)
    dtree = read(SKILL / 'references' / 'design-tree.md')
    check('design-tree round mechanics owns the neutral challenge',
          'argues against its own' in dtree)
    check('uiux-tree points to the spine for the neutral challenge',
          'argues against its own' not in read(SKILL / 'references' / 'uiux-tree.md')
          and 'neutral challenge' in read(SKILL / 'references' / 'uiux-tree.md'))
    check('design-tree close gate ticks the neutral challenge',
          'The proposal carried its neutral challenge' in dtree)
    # The checklist gate: a reader-judged ritual alongside the script gates.
    agents = read(SKILL / 'AGENTS.md')
    check('AGENTS.md carries the checklist gate section',
          '## Checklist gates' in agents
          and agents.count('- [ ]') >= 10)
    check('AGENTS.md stays a principles file, never a changelog',
          'never turn it into a change log' in agents)
    check('AGENTS.md index lists every tree file',
          all(marker in agents for marker in (
              '- `references/design-tree.md`', '- `references/logic-tree.md`',
              '- `references/uiux-tree.md`', '- `references/doc-tree.md`')))
    check('AGENTS.md index owns the new gates and contracts',
          'Round gates' in agents and 'neutral challenge' in agents
          and 'Stage gates' in agents and 'state display contracts' in agents
          and 'agent participation contracts' in agents)
    check('AGENTS.md mandates the mirror sync and recursive diff',
          'discovery mirror' in agents and 'recursive diff' in agents)
    check('AGENTS.md generalizes RED then GREEN',
          'writes the failing check first (RED), then the change (GREEN)'
          in agents)
    check('AGENTS.md pins the rendered evidence gate (capture + live url)',
          'carries both its boxed capture and its live url' in agents)
    check('AGENTS.md routes console critiques back to the tool',
          'critique the console itself are tool feedback' in agents)
    check('AGENTS.md pins the design-time function spec page',
          'function-spec.html' in agents
          and 'never implemented into production' in agents
          and 'Function Spec" tab' in agents)
    check('AGENTS.md pins the one-shot error-list repair loop',
          'error.errors[]' in agents and 'whole list and retries once'
          in agents)
    check('AGENTS.md binds the runtime gates ritual',
          'launch gate' in agents and 'close gate' in agents)
    # The user-confirmed standards (2026-10-31 alignment): every UI/UX
    # criterion verifies on the deployed environment; icons, whitespace over
    # dividers and Title Case are pooled, deterministic criteria; the
    # artifact page carries the four-tab design-time dock; elements enter as
    # 1:1 fragments appended into the cumulative artifact.
    check('uiux-tree.md pools deployment-verified criteria',
          'Deployment-verified criteria' in uiux_all
          and 'browser-automation or computer-control' in uiux_all
          and 'only a local machine never passes' in uiux_all)
    check('uiux-tree.md pools the icon audit',
          'Icon audit' in uiux_all and 'emoji-icon count is zero' in uiux_all)
    check('uiux-tree.md pools whitespace over dividers',
          'Whitespace over dividers' in uiux_all
          and 'zero hr and zero divider-only elements' in uiux_all)
    check('uiux-tree.md pools the Title Case copy audit',
          'Title Case copy' in uiux_all
          and 'other scripts are out of scope' in uiux_all)
    check('uiux-tree.md pools append-only growth',
          'Append-only growth' in uiux_all
          and 'zero changed markup' in uiux_all)
    check('uiux-tree.md pools the motion audit',
          'Motion audit' in uiux_all and '80-450 ms' in uiux_all
          and 'prefers-reduced-motion' in uiux_all)
    check('uiux-tree.md pools the token consistency audit',
          'Token consistency' in uiux_all
          and 'element kinds carry identical tokens' in uiux_all)
    check('manifest documents the tokens check',
          'tokens' in manifest and 'one background value' in manifest)
    check('uiux-tree.md carries the micro-to-medium motion principle',
          'Micro-to-medium motion' in uiux_all
          and 'nothing heavier than medium' in uiux_all)
    check('uiux-tree.md carries the standards design principles',
          'Decoration stripped' in uiux_all
          and 'whitespace by default' in uiux_all
          and 'Icon consistency' in uiux_all
          and 'Title Case copy' in uiux_all)
    check('uiux-tree.md never swallows decisions or logic',
          'opens a design-tree round' in uiux_all
          and 'opens a logic-tree round' in uiux_all)
    check('uiux-tree.md carries the design-time dock section',
          '### The design-time dock' in uiux_all
          and 'Design Preview' in uiux_all and 'Decision Log' in uiux_all
          and 'Version Ladder' in uiux_all
          and 'collapsed by default' in uiux_all
          and 'never implemented into production' in uiux_all)
    check('uiux-tree.md appends elements as 1:1 fragments',
          'own 1:1 fragment' in uiux_all
          and 'confirmed regions are never regenerated' in uiux_all)
    check('uiux-tree.md gates the artifact server on the validator',
          'validate_artifact.py' in uiux_all
          and 'starts only after' in uiux_all)
    check('uiux-tree.md stage gate names the deployed verify',
          'no verify method names only a local machine' in uiux_all)
    # Whole-page variant copies (the one-shot round path): every S3/S4
    # option shows the whole current artifact with the candidate applied,
    # never an isolated fragment page; the winner appends without a
    # re-confirmation round.
    check('uiux-tree.md pins whole-page variant copies for options',
          'copied 1:1 with the candidate applied' in uiux_all
          and 'never an isolated fragment page' in uiux_all)
    check('uiux-tree.md closes every round with the append duties',
          'Round close (every S2-S5 round)' in uiux_all
          and 'version ladder entry and snapshot written' in uiux_all)
    check('manifest documents the baseline append-only check',
          '--baseline <prev-snapshot>' in manifest
          and 'append-only' in manifest)
    check('AGENTS.md pins the script-controlled standards gate',
          'validate_artifact.py' in agents
          and 'only after the validator passes' in agents)
    check('AGENTS.md pins deployment-verified UI/UX criteria',
          'deployed environment' in agents
          and 'browser-automation or computer-control' in agents)
    check('AGENTS.md pins the design-time dock',
          'design-time dock' in agents
          and 'never enter the production mirror' in agents)
    check('AGENTS.md pins the incremental element append',
          'own 1:1 fragments' in agents
          and 'confirmed regions are never regenerated' in agents)
    check('AGENTS.md pins the version ladder rounds',
          'one entry and one snapshot per confirmed round' in agents)
    check('AGENTS.md pins micro-to-medium motion',
          'micro-to-medium motion' in agents
          and 'reduced motion' in agents)
    # D8-D14 standards absorbed into the constitution body.
    check('AGENTS.md pins the support probe',
          'probed, never assumed' in agents
          and 'knowledge base' in agents)
    check('AGENTS.md pins the coverage gate',
          'coverage gate' in agents and 'version ladder' in agents)
    check('AGENTS.md pins the high-fidelity prototype',
          'high-fidelity prototype, not a mockup' in agents)
    check('AGENTS.md pins whole-page variant copies',
          'copied 1:1 with the candidate applied' in agents)
    check('AGENTS.md pins the never-swell rule',
          'never swallows decisions or logic' in agents)
    check('AGENTS.md pins version parity and the verify generator',
          'Version parity' in agents and 'gen_verify_script.py' in agents)
    check('AGENTS.md pins the session language',
          'session language' in agents)
    check('AGENTS.md checklist indexes the probe and round close',
          '- [ ] Support-probe before options' in agents
          and '- [ ] Round close commits' in agents)
    check('AGENTS.md pins token consistency',
          'token consistency' in agents)
    check('AGENTS.md registers the artifact validator',
          '- `scripts/validate_artifact.py`' in agents)
    check('AGENTS.md checklist indexes the standards gate',
          '- [ ] Deterministic standards are script-controlled' in agents)
    check('manifest documents the artifact validator',
          'validate_artifact.py' in manifest
          and 'pre-launch gate' in manifest)
    check('SKILL.md carries the round launch gate',
          '## Round gates' in read(SKILL / 'SKILL.md'))
    gate_files = {
        'references/design-tree.md': '### Round gates',
        'references/logic-tree.md': '### Round gates',
        'references/doc-tree.md': '### Round gates',
        'references/uiux-tree.md': '### Stage gates',
        'references/question-form.md': '## Delivery gate',
    }
    for rel, marker in gate_files.items():
        body = read(SKILL / rel)
        check('%s carries its tick-list (%s)' % (rel, marker),
              marker in body and body.count('- [ ]') >= 3)
    skill_md = read(SKILL / 'SKILL.md')
    ui_row = re.search(r'^\| UI: .*$', skill_md, re.MULTILINE)
    check('router UI row names the five stages, not three',
          bool(ui_row) and 'Five stages' in ui_row.group(0)
          and 'Three stages' not in ui_row.group(0))
    check('router UI row points to the entry rules',
          bool(ui_row) and 'refinement' in ui_row.group(0))
    check('router UI row names the two-layer routing',
          bool(ui_row) and 'two-layer routing' in ui_row.group(0))
    uiux_body = read(SKILL / 'references' / 'uiux-tree.md')
    check('uiux-tree carries card rules as pointers, no restatement',
          'One page = one round batch' not in uiux_body
          and 'Each card renders the round template' not in uiux_body
          and 'Round rules:' not in uiux_body
          and 'Card rules' in uiux_body)
    check('question-form Delivery owns the never-plain-text rule',
          'never plain-text asking' in read(SKILL / 'references' / 'question-form.md'))
    # Console chrome language: the author sets the page lang to the session
    # language every round; fixed copy renders from the script's built-in
    # table, never authored ad hoc in the spec.
    check('question-form Delivery owns the session-language rule',
          'follows the session language' in read(SKILL / 'references' / 'question-form.md')
          and 'built-in copy table' in read(SKILL / 'references' / 'question-form.md'))
    # Implementation support is probed, never assumed: an option that
    # depends on an API or existing code reaches the user only after the
    # agent confirmed that support in the real environment.
    check('question-form Options owns the support-probe rule',
          'Implementation support is probed, never assumed'
          in read(SKILL / 'references' / 'question-form.md')
          and 'designing what the environment cannot back'
          in read(SKILL / 'references' / 'question-form.md'))
    check('question-form probe searches the knowledge base first',
          'knowledge base' in read(SKILL / 'references' / 'question-form.md'))
    check('question-form Delivery gate indexes the support probe',
          'Capability-dependent options carry a probe'
          in read(SKILL / 'references' / 'question-form.md'))
    check('logic-tree folds How to ask into Node confirmation',
          '### How to ask' not in read(SKILL / 'references' / 'logic-tree.md')
          and 'Novice mode:' in read(SKILL / 'references' / 'logic-tree.md'))
    check('SKILL.md exception points instead of restating console behaviour',
          'it opens in the browser automatically' not in skill_md)
    check('uiux-tree.md stages the evidence: wireframes exempt from boxes',
          'self-annotates' in uiux_bind and '/prototype' in uiux_bind)
    check('uiux-tree.md wireframes render at true page size (1:1 starts here)',
          'true viewport size' in uiux_bind)
    rules = {'CJK=0': [], 'CRLF in markdown': [], 'no absolute path or user name': []}
    for path in text_files():
        rel = path.relative_to(SKILL).as_posix()
        text = read(path)
        if CJK_RE.search(text):
            rules['CJK=0'].append(rel)
        if path.suffix == '.md' and LONE_LF_RE.search(text):
            rules['CRLF in markdown'].append(rel)
        if path.name != SELF and ABS_PATH_RE.search(text):
            rules['no absolute path or user name'].append(rel)
    for rule, bad in rules.items():
        check(rule, not bad, ', '.join(bad))
    head = read(SKILL / 'SKILL.md').splitlines()[:6]
    check('SKILL.md name matches folder name', 'name: ' + SKILL.name in head)
    # Alignment-shaped requests (align on the UI/UX with me) must land
    # here, not on the align-with-me wrapper: the description claims the
    # align verb for UI/UX explicitly.
    check('SKILL.md description claims align/review of UI/UX',
          'align on, review, or change anything UI/UX' in head[2])
    wiring = [('SKILL.md', 'question-form.md'),
              ('references/logic-tree.md', 'question-form.md'),
              ('references/uiux-tree.md', 'question-form.md'),
              ('references/design-tree.md', '## Round preamble'),
              ('AGENTS.md', SELF)]
    for rel, needle in wiring:
        check(rel + ' -> ' + needle, needle in read(SKILL / rel))
    # Trigger sentences stay out of references; the router in SKILL.md owns routing (AGENTS.md).
    trigger_re = re.compile(r'Read this file|Use when|When to read', re.IGNORECASE)
    trig = [str(p.relative_to(SKILL)) for p in sorted((SKILL / 'references').glob('*.md'))
            if trigger_re.search(read(p))]
    check('references carry no trigger sentences', not trig, ', '.join(trig))
    # UI rounds run in five stages (S1 page, S2 block, S3 element,
    # S4 interaction scenarios, S5 visual sweep); the table owns the order.
    uiux = read(SKILL / 'references' / 'uiux-tree.md')
    check('uiux-tree.md stages table has S1-S5 rows',
          all(re.search(r'^\| S%d ' % n, uiux, re.MULTILINE)
              for n in (1, 2, 3, 4, 5)))
    s2_row = re.search(r'^\| S2 .*$', uiux, re.MULTILINE)
    check('uiux-tree.md S2 row excludes interaction',
          bool(s2_row) and 'no interaction' in s2_row.group(0).lower())
    s4_row = re.search(r'^\| S4 .*$', uiux, re.MULTILINE)
    check('uiux-tree.md S4 row aligns scenario interaction contracts',
          bool(s4_row)
          and all(word in s4_row.group(0).lower()
                  for word in ('trigger', 'feedback', 'state', 'recovery')))
    check('uiux-tree.md S4 row opens with a combed scenario inventory',
          bool(s4_row)
          and 'combed scenario inventory' in s4_row.group(0)
          and 'convenience first' in s4_row.group(0))
    check('uiux-tree.md S4 row walks the state machine per scenario',
          bool(s4_row)
          and 'state machine' in s4_row.group(0)
          and 'non-ideal state' in s4_row.group(0))
    check('uiux-tree.md carries the state display contracts section',
          '### State display contracts (S4)' in uiux
          and 'Empty is not an error' in uiux
          and "what happened, why, and what to do next" in uiux
          and 'most severe first' in uiux)
    check('uiux-tree.md S4 row combs the agent layer',
          bool(s4_row) and 'agent layer' in s4_row.group(0)
          and 'self-learn' in s4_row.group(0))
    check('uiux-tree.md carries the agent participation contracts section',
          '### Agent participation contracts (S4)' in uiux
          and 'surface problems, assist the fix, deepen the analysis, '
              'remind proactively' in uiux
          and 'Intent preview' in uiux and 'Autonomy level' in uiux
          and 'Confidence' in uiux and 'undo' in uiux
          and 'learns from the correction' in uiux)
    s5_row = re.search(r'^\| S5 .*$', uiux, re.MULTILINE)
    # The host project's own UI/UX standard is a hard acceptance baseline
    # when it exists: conformance is verified on the deployed environment,
    # referenced but never copied into the skill.
    s5_check = re.search(r'^\| S5 .*$', uiux, re.MULTILINE)
    check('uiux-tree.md S5 row makes the project standard a hard baseline',
          bool(s5_check) and 'hard acceptance baseline' in s5_check.group(0)
          and 'referenced, never copied in' in s5_check.group(0))
    check('uiux-tree.md S5 row sweeps the four visual principles',
          bool(s5_row)
          and all(word in s5_row.group(0).lower()
                  for word in ('contrast', 'repetition', 'alignment',
                               'proximity')))
    check('uiux-tree.md pools the four principles at every scope',
          'four visual principles' in uiux)
    check('uiux-tree.md binds every stage to the design-tree walk',
          'S1-S5 runs as full design-tree rounds' in uiux
          and 'The stage changes the scope, never the process' in uiux)
    check('uiux-tree.md stages hold many rounds; a write-in restarts from S1',
          'A stage is one or more rounds' in uiux
          and 're-opens every stage from S1' in uiux
          and 'never a stage exit' in uiux)
    # The stages are lenses: a greenfield walk runs all five in order, a
    # refinement (a confirmed artifact exists) enters at the change's
    # scope with the baseline confirmed.
    check('uiux-tree.md carries the two-entry rule (greenfield/refinement)',
          '### Two entries' in uiux
          and 'Greenfield entry' in uiux and 'Refinement entry' in uiux
          and 'scope round' in uiux and 'stay confirmed' in uiux)
    check('uiux-tree.md routes its entry from context',
          'Entry routing' in uiux and 'judged from the context' in uiux)
    check('uiux-tree.md scopes a refinement write-in to touched scopes',
          're-opens only the scopes' in uiux)
    check('AGENTS.md five-stage rule names the refinement entry',
          "enters at the change's scope" in read(SKILL / 'AGENTS.md'))
    # The where-things-live list registers every script, so a new file
    # never lands unannounced.
    check('AGENTS.md registers the function spec generator',
          'gen_function_spec.py' in read(SKILL / 'AGENTS.md'))
    check('AGENTS.md requires verify-before-serve',
          'Verify before it serves' in read(SKILL / 'AGENTS.md'))
    # Tree files share one skeleton (AGENTS.md): H1 title first, then the
    # four fixed H2 slots in order. question-form.md is exempt (shared
    # standard, not a tree).
    slots = ['## Round preamble', '## Round rules', '## Evidence',
             '## Round closing']
    for name in ('design-tree.md', 'logic-tree.md', 'uiux-tree.md',
                 'doc-tree.md'):
        tree_text = read(SKILL / 'references' / name)
        first_line = next((ln for ln in tree_text.splitlines() if ln.strip()),
                          '')
        check(name + ' opens with an H1 title', first_line.startswith('# '))
        idx = [tree_text.find(slot) for slot in slots]
        check(name + ' carries the four skeleton slots in order',
              all(i >= 0 for i in idx) and idx == sorted(idx))
    # Maintainer checks must never pop the decision console in the user's browser.
    # Every launch of serve_decision.py in this file must pass --no-open within its next lines.
    own = read(SKILL / 'scripts' / SELF).splitlines()
    unopened = []
    for i, line in enumerate(own):
        if "[sys.executable" in line and 'serve_decision.py' in line:
            window = ' '.join(own[i:i + 3])
            if '--watch' not in window and '--no-open' not in window:
                unopened.append('line %d' % (i + 1))
    check('check_skill launches the server with --no-open', not unopened, ', '.join(unopened))


def render_checks():
    WORK.mkdir(parents=True, exist_ok=True)
    spec = {
        'title': 'check page', 'round': 9, 'topic': 'Jira Bulk Import', 'lang': 'zh-CN',
        'alignment': [
            {'seq': 'Q1', 'question': 'Earlier round: version scheme',
             'decision': 'Semantic versioning'},
            {'seq': 'Q2', 'question': 'Retry policy', 'decision': None, 'qid': 'q1'},
            {'seq': 'Q3', 'question': 'Bump version', 'decision': None, 'qid': 'q2'},
        ],
        'questions': [
            {'qid': 'q1', 'title': 'Retry policy', 'context': '- Explanation line',
             'prob_label': 'Prior probability of adoption',
             'evidence': 'degraded',
             'options': [
                 {'label': 'Retry', 'probability': 65, 'recommended': True,
                  'why': 'fast path', 'example': 'row 120 failed on timeout',
                  'pros': ['no manual rerun'], 'cons': ['slower import']},
                 {'label': 'Fail fast', 'probability': 35}]},
            {'qid': 'q2', 'title': 'Bump version', 'context': '',
             'options': [
                 {'label': 'Keep',
                  'url': 'proto/keep.html?variant=1',
                  'image': 'shots/box.png',
                  'boxes': [{'x': 0, 'y': 0, 'w': 1, 'h': 1,
                             'label': 'changed region'}]},
                 {'label': 'Bump', 'url': 'proto/bump.html',
                  'image': 'shots/bump.png',
                  'boxes': [{'x': 0, 'y': 0, 'w': 2, 'h': 1,
                             'label': 'bumped region'}]}]},
        ],
    }
    (WORK / 'shots').mkdir(exist_ok=True)
    import base64 as _b64
    (WORK / 'shots' / 'box.png').write_bytes(png_bytes(200, 120))
    (WORK / 'shots' / 'bump.png').write_bytes(png_bytes(220, 90))
    (WORK / 'proto').mkdir(exist_ok=True)
    (WORK / 'proto' / 'keep.html').write_text(
        '<!DOCTYPE html><html><body><p>keep page</p></body></html>',
        encoding='utf-8')
    (WORK / 'proto' / 'bump.html').write_text(
        '<!DOCTYPE html><html><body><p>bump page</p></body></html>',
        encoding='utf-8')
    spec_path = WORK / 'check-spec.json'
    write(spec_path, json.dumps(spec, ensure_ascii=False, indent=2))
    sys.path.insert(0, str(SCRIPTS))
    import serve_decision as sd
    loaded = sd._load_spec(str(spec_path), static_root=str(WORK))
    html = sd._render_spec_page(loaded['title'], loaded['questions'], loaded['lang'],
                                loaded['alignment'], loaded['topic'])
    check('render: alignment table at top', 'class="align"' in html
          and ('Jira Bulk Import' in html))
    # zh fixture (lang zh-CN): chrome copy renders Chinese from the zh table.
    check('render: decided + pending chips localized with icons',
          'chip ok"><svg' in html and 'chip pend"><svg' in html
          and ('>\u5df2\u51b3\u5b9a</span>' in html)
          and ('>\u5f85\u51b3\u5b9a</span>' in html))
    check('render: Reason/Example/Pros/Cons leads localized, no recap row',
          '<b>\u539f\u56e0:</b>' in html
          and '<b>\u4f8b\u5982:</b>' in html and '<b>\u4f18\u70b9:</b>' in html
          and '<b>\u7f3a\u70b9:</b>' in html and 'class="recap"' not in html
          and 'Recommended answer:' not in html)
    check('render: zh page shows Chinese chrome, no English chrome',
          '\u4e00\u6b21\u4e00\u5f20\u5361' in html
          and '\u5199\u51fa\u4f60\u81ea\u5df1\u7684\u7b54\u6848' in html
          and '\u60ac\u505c\u5c55\u5f00' in html
          and '\u51b3\u7b56\u6811' in html
          and 'One card at a time' not in html
          and 'hover to expand' not in html
          and 'None of these - write my own answer' not in html)
    html_en = sd._render_spec_page(loaded['title'], loaded['questions'], 'en',
                                   loaded['alignment'], loaded['topic'])
    check('render: en page shows English chrome, no Chinese chrome',
          'One card at a time' in html_en
          and 'None of these - write my own answer' in html_en
          and '\u5f85\u51b3\u5b9a' not in html_en)
    check('render: leading bullet mark stripped', 'Explanation line' in html
          and '- Explanation line' not in html)
    check('render: lang passthrough', 'lang="zh-CN"' in html)
    check('render: prob_label kept by loader and shown as legend',
          loaded['questions'][0].get('prob_label') == 'Prior probability of adoption'
          and 'class="problegend"' in html)
    check('render: error page renders', '60%,' in sd._render_error_page('m', 'h'))
    check('render: confirm page renders', '60%,' in sd._render_confirm('x'))
    check('render: live rows carry data-qid and the table id',
          'data-qid="q1"' in html and 'data-qid="q2"' in html
          and 'id="aligntable"' in html)
    check('render: prior-round row has no data-qid', '<tr><td>Q1</td>' in html)
    check('render: sync function shipped', 'function syncAlignment' in html)
    check('render: degraded card shows the evidence badge',
          'class="evbadge"' in html)
    check('render: one capture per option with an open-in-tab link, no iframe',
          'liveframe' not in html
          and html.count('class="openlink') == 2)
    check('render: KPI row of three cards and in-bar card arrows',
          html.count('class="kpi"') == 3
          and html.count('data-cnav=') == 4
          and 'alignwrap' in html)
    check('render: every card ends with a write-in option',
          html.count('data-own="1"') == 2 and html.count('class="owntext"') == 2)
    check('render: every write-in option carries a paste zone',
          html.count('class="pastezone"') == 2
          and html.count('class="pastelist"') == 2)
    check('render: status chips carry icons',
          html.count('chip ok"><svg') == 1
          and html.count('chip pend"><svg') == 2)
    check('render: KPI cards carry icons',
          html.count('class="ic kic"') == 3)
    check('render: write-in box is a growing textarea, Enter confirms',
          html.count('<textarea class="owntext"') == 2
          and '<input type="text" class="owntext"' not in html)
    check('render: one annotate-capable openlink, no separate annotate link',
          html.count('annotate=1') == 2 and 'annotatelink' not in html)
    check('render: openlink row right-aligned', html.count('class="linkrow"') == 2)
    check('render: annotate href carries card and option indices',
          html.count('annotate=1&amp;q=') == 2)
    check('render: relative url href carries /static/ and a joined query',
          'href="/static/proto/keep.html?variant=1&amp;annotate=1&amp;q=1&amp;o=0"'
          in html)
    check('render: the write-in box is the only comment field (no per-card note)',
          'notewrap' not in html and 'id="note' not in html)
    check('render: errors render in flow, never covering card text',
          html.index('id="errorbox"') < html.index('<form')
          and '.errbox { position: static' in html)
    check('render: capture boxes drawn with red labels',
          'class="shotbox"' in html and 'class="shotlabel"' in html)
    keep_img = Path(loaded['questions'][1]['options'][0]['image'])
    check('loader resolves a relative image against the spec folder',
          keep_img.is_absolute() and keep_img.is_file(),
          str(keep_img))

    def reject(name, rows):
        bad = dict(spec)
        bad['alignment'] = rows
        bad_path = WORK / 'check-bad.json'
        write(bad_path, json.dumps(bad, ensure_ascii=False))
        try:
            sd._load_spec(str(bad_path), static_root=str(WORK))
        except sd._SpecError as exc:
            check(name, True, str(exc))
            return
        check(name, False, 'loader accepted the row')

    reject('loader rejects a linked row that also carries a decision',
           [{'seq': 'Q2', 'question': 'x', 'decision': 'y', 'qid': 'q1'}])
    reject('loader rejects a qid that names no card on the page',
           [{'seq': 'Q2', 'question': 'x', 'decision': None, 'qid': 'q9'}])

    def reject_spec(name, mutated, needle=''):
        bad_path = WORK / 'check-bad-spec.json'
        write(bad_path, json.dumps(mutated, ensure_ascii=False))
        try:
            sd._load_spec(str(bad_path), static_root=str(WORK))
        except sd._SpecError as exc:
            hits = [i for i in getattr(exc, 'issues', [])
                    if needle in i.get('msg', '')]
            check(name, not needle or bool(hits) or needle in str(exc),
                  str(getattr(exc, 'issues', []) or exc)[:220])
            return
        check(name, False, 'loader accepted the spec')

    bare = json.loads(json.dumps(spec))
    for question in bare['questions']:
        question.pop('evidence', None)
        for option in question['options']:
            option.pop('url', None)
    reject_spec('loader rejects a rendered card with no image or url',
                bare, 'rendered-evidence')
    wrong = json.loads(json.dumps(spec))
    wrong['questions'][0]['evidence'] = 'guesswork'
    reject_spec('loader rejects an unknown evidence mode', wrong, 'evidence')
    noimg = json.loads(json.dumps(spec))
    noimg['questions'][1]['options'][0]['image'] = 'shots/missing.png'
    reject_spec('loader rejects an image file that does not exist',
                noimg, 'not found')
    nobox = json.loads(json.dumps(spec))
    del nobox['questions'][1]['options'][0]['boxes']
    reject_spec('loader rejects a screenshot without boxes',
                nobox, 'boxes')
    webimg = json.loads(json.dumps(spec))
    webimg['questions'][1]['options'][0]['image'] = '/static/shots/a.png'
    reject_spec('loader rejects a web route in image and points to url',
                webimg, 'url')
    httpimg = json.loads(json.dumps(spec))
    httpimg['questions'][1]['options'][0]['image'] = 'https://example.com/a.png'
    reject_spec('loader rejects an http URL in image and points to url',
                httpimg, 'url')
    stprefix = json.loads(json.dumps(spec))
    stprefix['questions'][1]['options'][0]['url'] = '/static/proto/keep.html'
    reject_spec('loader rejects a relative url carrying the /static/ prefix',
                stprefix, '/static/')
    stmiss = json.loads(json.dumps(spec))
    stmiss['questions'][1]['options'][1]['url'] = 'proto/absent.html'
    reject_spec('loader rejects a relative url missing under --static-root',
                stmiss, 'not found')
    # Rendered evidence needs BOTH the boxed capture and the live url: a
    # capture without a live view hides the annotate entry, a url without
    # a capture has no evidence. The loader refuses either at startup.
    nocap = json.loads(json.dumps(spec))
    del nocap['questions'][1]['options'][0]['image']
    reject_spec('loader rejects a rendered option with a url but no capture',
                nocap, 'capture')
    nolive = json.loads(json.dumps(spec))
    del nolive['questions'][1]['options'][0]['url']
    reject_spec('loader rejects a rendered option with a capture but no url',
                nolive, 'url')
    two = json.loads(json.dumps(spec))
    two['questions'][1]['evidence'] = 'guesswork'
    two['questions'][1]['options'][0]['image'] = 'shots/missing.png'
    two_path = WORK / 'check-two.json'
    write(two_path, json.dumps(two, ensure_ascii=False))
    try:
        sd._load_spec(str(two_path), static_root=str(WORK))
        check('loader reports all issues at once', False,
              'no error raised')
    except sd._SpecError as exc:
        check('loader reports all issues at once (pydantic-style)',
              len(getattr(exc, 'issues', [])) >= 2,
              str(getattr(exc, 'issues', []) or exc)[:220])
    frac = json.loads(json.dumps(spec))
    # A UTF-8 BOM in the spec file is accepted (the same tolerance
    # gen_xlsx and audit_sections already have).
    bom_path = WORK / 'check-bom.json'
    bom_spec = json.loads(json.dumps(spec))
    bom_spec['questions'][1]['evidence'] = 'wireframe'
    del bom_spec['questions'][1]['options'][0]['boxes']
    del bom_spec['questions'][1]['options'][0]['image']
    write(bom_path, '\ufeff' + json.dumps(bom_spec, ensure_ascii=False))
    try:
        loaded_bom = sd._load_spec(str(bom_path), static_root=str(WORK))
        check('loader accepts a UTF-8 BOM in the spec file', True)
    except sd._SpecError as exc:
        check('loader accepts a UTF-8 BOM in the spec file', False, str(exc)[:160])
    frac['questions'][1]['options'][0]['probability'] = 0.8
    frac_path = WORK / 'check-frac.json'
    write(frac_path, json.dumps(frac, ensure_ascii=False))
    loaded_frac = sd._load_spec(str(frac_path), static_root=str(WORK))
    check('loader reads a fraction probability as a percentage',
          loaded_frac['questions'][1]['options'][0]['probability'] == 80,
          str(loaded_frac['questions'][1]['options'][0]['probability']))
    wf_path = WORK / 'check-wireframe.json'
    wf_ok = json.loads(json.dumps(spec))
    wf_ok['questions'][1]['evidence'] = 'wireframe'
    del wf_ok['questions'][1]['options'][0]['boxes']
    del wf_ok['questions'][1]['options'][0]['image']
    write(wf_path, json.dumps(wf_ok, ensure_ascii=False))
    try:
        loaded_wf = sd._load_spec(str(wf_path), static_root=str(WORK))
        check('loader accepts wireframe evidence without boxes (url-only)',
              loaded_wf['questions'][1]['evidence'] == 'wireframe')
    except sd._SpecError as exc:
        check('loader accepts wireframe evidence without boxes (url-only)',
              False, str(exc))
    wf_bad = json.loads(json.dumps(wf_ok))
    del wf_bad['questions'][1]['options'][0]['url']
    reject_spec('loader rejects a wireframe option with no url or image',
                wf_bad, 'wireframe')
    # Visual annotation kinds must be complete: a move needs both ends,
    # an icon needs its icon, a color needs both colors.
    mv = json.loads(json.dumps(spec))
    mv['questions'][1]['options'][0]['boxes'] = [
        {'kind': 'move', 'from': {'x': 10, 'y': 10}, 'label': 'm'}]
    reject_spec('loader rejects a move box without a target point',
                mv, 'to')
    ic = json.loads(json.dumps(spec))
    ic['questions'][1]['options'][0]['boxes'] = [
        {'kind': 'icon', 'x': 10, 'y': 10, 'w': 24, 'h': 24, 'label': 'i'}]
    reject_spec('loader rejects an icon box without icon paths',
                ic, 'icon')
    cl = json.loads(json.dumps(spec))
    cl['questions'][1]['options'][0]['boxes'] = [
        {'kind': 'color', 'x': 10, 'y': 10, 'suggested': '#2563eb',
         'label': 'c'}]
    reject_spec('loader rejects a color box without the current color',
                cl, 'current')
    uk = json.loads(json.dumps(spec))
    uk['questions'][1]['options'][0]['boxes'] = [{'kind': 'sparkle'}]
    reject_spec('loader rejects an unknown annotation kind',
                uk, 'kind')
    vk = json.loads(json.dumps(spec))
    vk['questions'][1]['options'][0]['boxes'] = [
        {'kind': 'move', 'from': {'x': 10, 'y': 10}, 'to': {'x': 200, 'y': 40},
         'label': 'm'},
        {'kind': 'icon', 'x': 10, 'y': 10, 'w': 24, 'h': 24,
         'icon': '<path d="M12 20h9"/>', 'label': 'i'},
        {'kind': 'color', 'x': 10, 'y': 10, 'current': '#94a3b8',
         'suggested': '#2563eb', 'label': 'c'}]
    vk_path = WORK / 'check-kinds.json'
    write(vk_path, json.dumps(vk, ensure_ascii=False))
    try:
        kb = sd._load_spec(str(vk_path),
                           static_root=str(WORK))['questions'][1]['options'][0]['boxes']
        check('loader accepts complete visual kinds move/icon/color',
              kb[0]['kind'] == 'move' and kb[1]['kind'] == 'icon'
              and kb[2]['kind'] == 'color' and kb[0]['to']['x'] == 200
              and kb[1]['icon'] == '<path d="M12 20h9"/>'
              and kb[2]['current'] == '#94a3b8')
    except sd._SpecError as exc:
        check('loader accepts complete visual kinds move/icon/color',
              False, str(exc))

    arr_path = WORK / 'check-array.json'
    arr_spec = json.loads(json.dumps(spec))
    arr_spec['questions'][0]['context'] = [
        '\u672c\u5361\u51b3\u5b9a\uff1a\u6570\u7ec4\u4e0a\u4e0b\u6587',
        '\u7b2c\u4e8c\u884c\u8bf4\u660e']
    arr_spec['questions'][0]['options'][0]['why'] = [
        '\u884c\u4e00', '\u884c\u4e8c']
    write(arr_path, json.dumps(arr_spec, ensure_ascii=False))
    joined_ctx = ('\u672c\u5361\u51b3\u5b9a\uff1a\u6570\u7ec4\u4e0a\u4e0b\u6587'
                  '\n\u7b2c\u4e8c\u884c\u8bf4\u660e')
    joined_why = '\u884c\u4e00\n\u884c\u4e8c'
    try:
        loaded_arr = sd._load_spec(str(arr_path), static_root=str(WORK))
        check('loader accepts array context/why (joined to lines)',
              loaded_arr['questions'][0]['context'] == joined_ctx
              and loaded_arr['questions'][0]['options'][0]['why'] == joined_why)
    except sd._SpecError as exc:
        check('loader accepts array context/why (joined to lines)', False, str(exc))
    return html


def drive_page(url, shot, label):
    from playwright.sync_api import sync_playwright
    cell_js = """(q) => {
  const tr = document.querySelector('#aligntable tr[data-qid="' + q + '"]');
  return tr ? tr.querySelector('.alcell').textContent.trim() : null;
}"""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page(viewport={'width': 1280, 'height': 900})
        page_errors = []
        pg.on('pageerror', lambda e: page_errors.append(str(e)))
        pg.goto(url)
        pg.wait_for_timeout(300)
        zh_pending = '\u5f85\u51b3\u5b9a'
        zh_decided = '\u5df2\u51b3\u5b9a'
        check('live %s: linked row q1 is Pending' % label,
              pg.evaluate(cell_js, 'q1') == zh_pending)
        check('live %s: linked row q2 is Pending' % label,
              pg.evaluate(cell_js, 'q2') == zh_pending)
        static_txt = pg.evaluate(
            "document.querySelector('#aligntable tbody tr').textContent")
        check('live %s: prior-round row stays static' % label,
              'Semantic versioning' in static_txt and zh_decided in static_txt)
        kpi = pg.evaluate(
            "(function(){ var g = function (id) {"
            " var el = document.getElementById(id);"
            " return el ? el.querySelector('b').textContent : null; };"
            " return [g('kpi-total'), g('kpi-decided'), g('kpi-pend')]; })()")
        check('live %s: KPI cards render the counts' % label,
              kpi == ['2', '0', '2'], str(kpi))
        heights = pg.evaluate(
            "(function(){ var w = document.querySelector('.alignwrap');"
            " var k = document.querySelector('.kpi');"
            " return w && k ? [Math.round(w.getBoundingClientRect().height),"
            " Math.round(k.getBoundingClientRect().height)] : null; })()")
        check('live %s: collapsed strip matches the KPI card height' % label,
              bool(heights) and abs(heights[0] - heights[1]) <= 8,
              str(heights))
        pg.hover('.alignwrap')
        pg.wait_for_timeout(450)
        open_h = pg.evaluate(
            "(function(){ var w = document.querySelector('.alignwrap');"
            " return w ? w.scrollHeight : -1; })()")
        check('live %s: hovering the alignment strip expands it' % label,
          open_h > 40, str(open_h))
        pg.click('.qcard.active .cnav[data-cnav="next"]')
        pg.wait_for_timeout(150)
        q_next = pg.evaluate(
            "(function(){ var q = document.querySelector('.qcard.active .qid');"
            " return q ? q.textContent : null; })()")
        check('live %s: in-bar next advances to card 2' % label,
              q_next == 'q2', str(q_next))
        pg.click('.qcard.active .cnav[data-cnav="prev"]')
        pg.wait_for_timeout(150)
        q_back = pg.evaluate(
            "(function(){ var q = document.querySelector('.qcard.active .qid');"
            " return q ? q.textContent : null; })()")
        check('live %s: in-bar prev returns to card 1' % label,
              q_back == 'q1', str(q_back))
        pg.click('.qcard.active .otitle >> nth=0')
        pg.wait_for_timeout(150)
        first = pg.evaluate(cell_js, 'q1') or ''
        check('live %s: card 1 decided -> row q1 shows Decided + option text' % label,
              zh_decided in first and 'Retry' in first, first)
        check('live %s: card 2 row still Pending' % label,
              pg.evaluate(cell_js, 'q2') == zh_pending)
        pg.wait_for_timeout(900)
        pg.keyboard.press('ArrowLeft')
        pg.wait_for_timeout(300)
        pg.click('.qcard.active .otitle >> nth=1')
        pg.wait_for_timeout(150)
        changed = pg.evaluate(cell_js, 'q1') or ''
        check('live %s: changed decision -> row q1 follows the new option' % label,
              'Fail fast' in changed and 'Retry' not in changed, changed)
        pg.keyboard.press('ArrowRight')
        pg.wait_for_timeout(300)
        pg.click('.qcard.active .opt:has(input[data-own]) .otitle')
        pg.wait_for_timeout(150)
        vis = pg.evaluate(
            "(function(){ var card = document.querySelector('.qcard.active');"
            " var o = card.querySelector('input[data-own]');"
            " var t = card.querySelector('.owntext');"
            " var cs = getComputedStyle(t);"
            " return t.offsetWidth > 100 && t.offsetHeight > 20"
            " && cs.opacity !== '0' && cs.visibility === 'visible'; })()")
        check('live %s: clicking the write-in shows a visible input' % label,
              vis is True, str(vis))
        pg.evaluate(
            """() => {
              const card = document.querySelector('.qcard.active');
              const dt = new DataTransfer();
              dt.items.add(new File([new Uint8Array([137, 80, 78, 71])],
                                   'probe.png', {type: 'image/png'}));
              card.dispatchEvent(new ClipboardEvent('paste',
                  {clipboardData: dt, bubbles: true}));
            }""")
        pg.wait_for_timeout(200)
        chips = pg.evaluate(
            "document.querySelectorAll('.qcard.active .pastechip').length")
        check('live %s: pasting an image adds a thumbnail chip' % label,
              chips == 1, str(chips))
        # Overlay geometry needs a visible capture: card 2 is still active
        # here (server mode only - file mode has no /img behind the page).
        if label == 'server':
            geom = pg.evaluate(
                """(function(){
                  var img = document.querySelector('img[data-shot]');
                  var box = document.querySelector('.shotbox');
                  var num = document.querySelector('.shotnum');
                  var lab = document.querySelector('.shotlabel');
                  if (!img || !box || !img.naturalWidth) { return null; }
                  var i = img.getBoundingClientRect();
                  var b = box.getBoundingClientRect();
                  var inside = b.left >= i.left - 0.5 && b.top >= i.top - 0.5
                    && b.right <= i.right + 0.5 && b.bottom <= i.bottom + 0.5;
                  var pad = b.width > 5;
                  var marks = true;
                  [num, lab].forEach(function (el) {
                    if (!el) { marks = false; return; }
                    var r = el.getBoundingClientRect();
                    if (r.left < i.left - 0.5 || r.top < i.top - 0.5
                        || r.right > i.right + 0.5
                        || r.bottom > i.bottom + 0.5) { marks = false; }
                  });
                  return { inside: inside, pad: pad, marks: marks };
                })()""")
            check('live %s: overlay frames the region with padding, '
                  'inside the capture' % label,
                  bool(geom) and geom['inside'] and geom['pad'], str(geom))
            check('live %s: badge and label stay inside the capture' % label,
                  bool(geom) and geom['marks'], str(geom))
        pg.evaluate("document.activeElement && document.activeElement.blur()")
        pg.wait_for_timeout(100)
        pg.keyboard.press('3')
        pg.wait_for_timeout(150)
        pg.keyboard.type('defer one week')
        pg.wait_for_timeout(200)
        second = pg.evaluate(cell_js, 'q2') or ''
        check('live %s: write-in answer fills the linked row' % label,
              'defer one week' in second, second)
        pg.keyboard.press('Enter')
        pg.wait_for_timeout(200)
        still_hidden = pg.evaluate(
            "document.getElementById('errorbox').classList.contains('hidden')")
        on_page = pg.evaluate("!!document.getElementById('panel')")
        check('live %s: Enter in the write-in input never submits the round'
              % label, still_hidden and on_page,
              'errorbox=%s on_page=%s' % (still_hidden, on_page))
        # The overlay needs the capture to load; in file mode /img has no
        # server behind it, so positioning is only assertable over HTTP.
        if label == 'server':
            boxed = pg.evaluate(
                "(function(){ var b = document.querySelector('.shotbox');"
                " return b ? getComputedStyle(b).left : 'none'; })()")
            check('live %s: capture box positioned over the image' % label,
                  str(boxed).endswith('px'), str(boxed))
            from urllib.request import Request
            ann_page = urlopen(
                url.rstrip('/') + '/static/proto/keep.html?variant=1&annotate=1',
                timeout=5).read().decode('utf-8')
            check('live %s: annotate flag injects the overlay' % label,
                  'grill-ann-toolbar' in ann_page)
            req = Request(url.rstrip('/') + '/annotations',
                          data=json.dumps(
                              {'url': '/static/proto/keep.html',
                               'title': 't',
                               'boxes': [{'n': 1, 'x': 1, 'y': 2, 'w': 30,
                                          'h': 20, 'caption': 'probe'}]}
                          ).encode('utf-8'),
                          headers={'Content-Type': 'application/json'})
            body = json.loads(urlopen(req, timeout=5).read().decode('utf-8'))
            ann_path = ANSWERS_ROUND.with_name(
                ANSWERS_ROUND.stem + '-annotations.json')
            ok = body.get('ok') is True and ann_path.exists()
            if ok:
                saved = json.loads(ann_path.read_text(encoding='utf-8'))
                ok = saved['boxes'][0]['caption'] == 'probe'
                ann_path.unlink()
            check('live %s: annotation POST round-trips to a file' % label,
                  ok, str(body))
            # A generate-prototype request posts with no marks at all:
            # "I cannot say it" needs no annotation to be actionable.
            preq = Request(url.rstrip('/') + '/annotations',
                           data=json.dumps(
                               {'url': '/static/proto/keep.html',
                                'title': 't', 'proto': True, 'boxes': []}
                           ).encode('utf-8'),
                           headers={'Content-Type': 'application/json'})
            pbody = json.loads(urlopen(preq, timeout=5).read().decode('utf-8'))
            check('live %s: prototype request round-trips without marks' % label,
                  pbody.get('ok') is True and pbody.get('proto') is True,
                  str(pbody))
        pg.locator('#alignwrap').screenshot(path=str(WORK / shot))
        check('live %s: no page errors (self-check before ask)' % label,
              page_errors == [], '; '.join(page_errors[:3]))
        browser.close()


def save_flow_check(url):
    """End-to-end annotate Save: console opens the annotate tab, a box is
    drawn, Save self-captures and swaps the option's evidence in the
    console, checks its radio without auto-advancing, and the annotate tab
    closes itself - no answers file is written (Save never submits)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={'width': 1280, 'height': 900})
        console = ctx.new_page()
        errors = []
        console.on('pageerror', lambda e: errors.append(str(e)))
        console.goto(url)
        console.wait_for_timeout(300)
        # Card 1 of the check spec is degraded evidence (no openlink);
        # advance to card 2, whose option carries a live url.
        console.click('.qcard.active .cnav[data-cnav="next"]')
        console.wait_for_timeout(300)
        with ctx.expect_page() as pop_info:
            console.click('.qcard.active .openlink >> nth=0')
        ann = pop_info.value
        ann.wait_for_load_state()
        ann.wait_for_timeout(200)
        check('save flow: annotate tab opens with opener and q/o params',
              ann.evaluate('!!window.opener')
              and 'q=' in ann.url and 'o=' in ann.url, ann.url[:90])
        ann.click('#grill-ann-toggle')
        ann.wait_for_timeout(150)
        ann.mouse.move(400, 300)
        ann.mouse.down()
        ann.mouse.move(620, 430, steps=6)
        ann.mouse.up()
        ann.wait_for_timeout(200)
        drawn = ann.evaluate(
            "document.querySelectorAll('.grill-ann-box').length"
            " + document.querySelectorAll('[class*=annbox]').length")
        if not drawn:
            # The drawn-box class name may differ; fall back to any box
            # element the toolbar's counter sees.
            drawn = ann.evaluate(
                "(function(){ var c = document.getElementById("
                "'grill-ann-count'); return c ? c.textContent : '0'; })()")
        ann.click('#grill-ann-save')
        # A successful Save closes the annotate tab itself (~300ms after
        # the postMessage); wait for the close event on the page object,
        # never on the dying page's timers.
        try:
            ann.wait_for_event('close', timeout=5000)
        except Exception:
            pass
        check('save flow: annotate tab closes itself after Save',
              ann.is_closed(), 'still open')
        badge = console.evaluate(
            "(function(){ var b = document.querySelector('.savebadge');"
            " return b ? getComputedStyle(b).display !== 'none'"
            " && b.offsetParent !== null : false; })()")
        check('save flow: console shows the green saved badge', badge)
        checked = console.evaluate(
            "(function(){ var card = document.querySelector('.qcard.active');"
            " var radios = card.querySelectorAll('.opt input[type=radio]');"
            " for (var i = 0; i < radios.length; i++)"
            " { if (radios[i].checked) return i; } return -1; })()")
        check('save flow: the annotated option radio is checked', checked == 0,
              'checked index %s' % checked)
        swapped = console.evaluate(
            "(function(){ var card = document.querySelector('.qcard.active');"
            " var img = card.querySelector('img');"
            " return img ? (img.src || '').slice(0, 11) : ''; })()")
        check('save flow: the option capture swapped to the self-capture',
              swapped == 'data:image/', 'img src prefix %r' % swapped)
        active = console.evaluate(
            "document.querySelector('.qcard.active .qid')")
        check('save flow: no auto-advance after Save', active is not None)
        check('save flow: no page errors during the save round-trip',
              errors == [], '; '.join(errors[:2]))
        browser.close()


def server_checks():
    existed = ANSWERS_ROUND.exists()
    proc = subprocess.Popen(
        [sys.executable, '-B', '-u', str(SCRIPTS / 'serve_decision.py'),
         '--spec', str(WORK / 'check-spec.json'), '--round', '9', '--port', '8765',
         '--no-open', '--static-root', str(WORK)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        encoding='utf-8', errors='replace')
    try:
        url = None
        assert proc.stdout is not None  # Popen was given stdout=PIPE
        for line in proc.stdout:
            if 'serving http://' in line:
                url = line.split('serving ', 1)[1].split()[0]
                break
        check('server started and printed its URL', url is not None)
        if url is None:
            return
        served = urlopen(url, timeout=5).read().decode('utf-8')
        check('served page carries the alignment table',
              'id="aligntable"' in served and 'data-qid="q1"' in served)
        drive_page(url, 'live-server.png', 'server')
        save_flow_check(url)
        check('live server run wrote no answers file', ANSWERS_ROUND.exists() == existed)
    finally:
        if proc.poll() is None:
            proc.terminate()
        proc.wait(timeout=10)


def answers_flag_check():
    custom = WORK / 'custom-answers.json'
    if custom.exists():
        custom.unlink()
    proc = subprocess.Popen(
        [sys.executable, '-B', '-u', str(SCRIPTS / 'serve_decision.py'),
         '--round', '9', '--answers', str(custom), '--port', '8765', '--no-open'],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        encoding='utf-8', errors='replace')
    try:
        url = None
        assert proc.stdout is not None  # Popen was given stdout=PIPE
        for line in proc.stdout:
            if 'serving http://' in line:
                url = line.split('serving ', 1)[1].split()[0]
                break
        check('--answers: server starts with the flag', url is not None)
        if url is None:
            return
        body = json.dumps([{'qid': 'round-9', 'choice': 'Keep', 'note': '', 'ts': 1}])
        request = Request(url + '/answer', data=body.encode('utf-8'),
                          headers={'Content-Type': 'application/json'})
        urlopen(request, timeout=5).read()
        check('--answers: POST writes the file given on the command line', custom.is_file())
        check('--answers: the file holds the posted answer',
              custom.is_file() and 'round-9' in read(custom))
    finally:
        if proc.poll() is None:
            proc.terminate()
        proc.wait(timeout=10)


def watcher_session_checks():
    answers = WORK / 'session-watch.json'
    base = [sys.executable, '-B', str(SCRIPTS / 'serve_decision.py'), '--watch', str(answers)]

    def watch(*extra):
        return subprocess.run(base + list(extra), capture_output=True, text=True,
                              encoding='utf-8', errors='replace', timeout=30)

    plain = json.dumps([{'qid': 'q1', 'choice': 'Retry', 'note': '', 'ts': 1}])
    write(answers, plain)
    check('watcher: refuses to start without --session',
          watch('--timeout', '1').returncode == 2)
    # Server-mode flags are never silently ignored in watcher mode: every
    # one of them is refused through the [ERR] contract (--session is
    # included so the rejection is really about the mode flag).
    result = watch('--title', 'x', '--session', 'abc123', '--timeout', '1')
    check('watcher: refuses --title instead of ignoring it',
          result.returncode == 2 and '[ERR]' in result.stderr
          and 'mutually exclusive' in result.stderr,
          'rc=%s out=%s' % (result.returncode, result.stdout[:80]))
    result = watch('--port', '99', '--session', 'abc123', '--timeout', '1')
    check('watcher: refuses --port instead of ignoring it',
          result.returncode == 2 and '[ERR]' in result.stderr)
    result = watch('--no-open', '--session', 'abc123', '--timeout', '1')
    check('watcher: refuses --no-open instead of ignoring it',
          result.returncode == 2 and '[ERR]' in result.stderr)
    write(answers, plain)
    result = watch('--session', 'abc123', '--timeout', '1')
    check('watcher: ignores an answers file without the session token',
          result.returncode == 3 and '[WARN] timeout' in result.stdout)
    other = json.dumps([{'qid': 'q1', 'choice': 'Retry', 'note': '', 'ts': 1, 'session': 'other9'}])
    write(answers, other)
    result = watch('--session', 'abc123', '--timeout', '1')
    check('watcher: ignores an answers file from another session',
          result.returncode == 3 and '[WARN] timeout' in result.stdout)
    mine = json.dumps([{'qid': 'q1', 'choice': 'Retry', 'note': '', 'ts': 1, 'session': 'abc123'}])
    write(answers, mine)
    result = watch('--session', 'abc123', '--timeout', '1')
    check('watcher: returns for an answers file with the session token',
          result.returncode == 0 and '[OK] answers ready' in result.stdout)


def session_token_check():
    custom = WORK / 'session-live.json'
    if custom.exists():
        custom.unlink()
    proc = subprocess.Popen(
        [sys.executable, '-B', '-u', str(SCRIPTS / 'serve_decision.py'),
         '--round', '9', '--answers', str(custom), '--port', '8765', '--no-open'],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        encoding='utf-8', errors='replace')
    try:
        url = None
        previous = ''
        assert proc.stdout is not None  # Popen was given stdout=PIPE
        for line in proc.stdout:
            if 'serving http://' in line:
                url = line.split('serving ', 1)[1].split()[0]
                break
            previous = line
        token = None
        if previous.startswith('[INFO] session '):
            token = previous.split('session ', 1)[1].strip()
        check('session: server prints its token before serving', token is not None)
        if url is None or token is None:
            return
        body = json.dumps([{'qid': 'round-9', 'choice': 'Keep', 'note': '', 'ts': 1}])
        request = Request(url + '/answer', data=body.encode('utf-8'),
                          headers={'Content-Type': 'application/json'})
        urlopen(request, timeout=5).read()
        entries = json.loads(read(custom))
        check('session: every stored entry carries the token',
              bool(entries) and all(item.get('session') == token for item in entries))
        result = subprocess.run(
            [sys.executable, '-B', str(SCRIPTS / 'serve_decision.py'), '--watch', str(custom),
             '--session', token, '--timeout', '5'],
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)
        check('session: watcher with the token returns the answer',
              result.returncode == 0 and '[OK] answers ready' in result.stdout)
    finally:
        if proc.poll() is None:
            proc.terminate()
        proc.wait(timeout=10)


def server_guard_check():
    result = subprocess.run(
        [sys.executable, '-B', str(SCRIPTS / 'serve_decision.py'), '--round', '9', '--session', 'abc123'],
        capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)
    check('server: --session without --watch is refused (exit 2)', result.returncode == 2)


def self_exit_check():
    """On submit the server itself must report the answers and exit 0, so one
    background task covers the whole round (no watcher, no token parsing)."""
    custom = WORK / 'self-exit.json'
    if custom.exists():
        custom.unlink()
    proc = subprocess.Popen(
        [sys.executable, '-B', '-u', str(SCRIPTS / 'serve_decision.py'),
         '--round', '9', '--answers', str(custom), '--port', '8931', '--no-open'],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        encoding='utf-8', errors='replace')
    try:
        url = None
        seen = []
        assert proc.stdout is not None  # Popen was given stdout=PIPE
        for line in proc.stdout:
            seen.append(line)
            if 'serving http://' in line:
                url = line.split('serving ', 1)[1].split()[0]
                break
        check('self-exit: server starts', url is not None)
        if url is None:
            return
        body = json.dumps([{'qid': 'round-9', 'choice': 'Keep', 'note': '', 'ts': 1}])
        request = Request(url + '/answer', data=body.encode('utf-8'),
                          headers={'Content-Type': 'application/json'})
        urlopen(request, timeout=5).read()
        rest = proc.communicate(timeout=10)[0] or ''
        whole = ''.join(seen) + rest
        check('self-exit: server exits 0 after the submit', proc.returncode == 0)
        check('self-exit: stdout carries answers ready + content',
              '[OK] answers ready' in whole and 'round-9' in whole)
    finally:
        if proc.poll() is None:
            proc.terminate()
        proc.wait(timeout=10)


def annotate_checks():
    script = SCRIPTS / 'annotate_image.py'
    if not script.exists():
        check('annotate_image.py exists', False, str(script))
        return
    try:
        compile(read(script), str(script), 'exec')
        check('annotate_image.py compiles', True)
    except SyntaxError as exc:
        check('annotate_image.py compiles', False, str(exc))
        return
    import base64
    src = WORK / 'px.png'
    src.write_bytes(base64.b64decode(PNG_1PX))
    out = WORK / 'px-annotated.svg'
    if out.exists():
        out.unlink()
    result = subprocess.run(
        [sys.executable, '-B', str(script), '--img', str(src), '--out', str(out),
         '--box', '0,0,1,1', '--note', 'changed region'],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=30)
    check('annotate: writes an svg with a box and a numbered label',
          out.is_file() and 'rect' in read(out) and 'circle' in read(out))
    check('annotate: stdout logs the [OK] marker and the note',
          '[OK]' in result.stdout and 'changed region' in result.stdout)
    result = subprocess.run(
        [sys.executable, '-B', str(script), '--img', str(src), '--out', str(out)],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=30)
    check('annotate: refuses to run without a box (exit 2)',
          result.returncode == 2)


def gen_spec_checks():
    # The function spec page is generated, never hand-built: one writer
    # script renders the format contract (banner, Confirmed decisions
    # table, Criteria) from the decisions data.
    script = SCRIPTS / 'gen_function_spec.py'
    if not script.exists():
        check('gen_function_spec.py exists', False, str(script))
        return
    try:
        compile(read(script), str(script), 'exec')
        check('gen_function_spec.py compiles', True)
    except SyntaxError as exc:
        check('gen_function_spec.py compiles', False, str(exc))
        return
    data = WORK / 'gen-spec-input.json'
    write(data, '''{
      "topic": "Sample Page",
      "lang": "en",
      "decisions": [
        {"seq": "Q1", "stage": "S1", "decision": "Sidebar layout",
         "why": "Tags stay visible", "lands": ["single-select filter"]}
      ],
      "criteria": [
        {"cid": "C1", "tag": "uiux", "criterion": "Labels fully readable",
         "verify": "scripted bounding-box check"}
      ]
    }''')
    out = WORK / 'gen-spec-out.html'
    if out.exists():
        out.unlink()
    result = subprocess.run(
        [sys.executable, '-B', str(script), '--spec', str(data),
         '--out', str(out)],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=30)
    body = read(out) if out.exists() else ''
    check('gen_function_spec writes the contracted page',
          result.returncode == 0 and out.is_file()
          and 'Function Spec (Aligned)' in body
          and 'Confirmed decisions' in body
          and '>Seq</th>' in body and '>Stage</th>' in body
          and '>Decision</th>' in body and '>Why</th>' in body
          and '>Lands</th>' in body
          and 'Sidebar layout' in body and 'Criteria' in body
          and '<b>C1 (uiux):</b> Labels fully readable' in body
          and 'verify: scripted bounding-box check' in body
          and 'replicates production 1:1' in body
          and 'never implement this page or this tab' in body)
    check('gen_function_spec stdout carries the [OK] marker',
          '[OK]' in result.stdout)
    result = subprocess.run(
        [sys.executable, '-B', str(script), '--spec', str(data)],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=30)
    check('gen_function_spec refuses to run without --out (exit 2)',
          result.returncode == 2)
    bad = WORK / 'gen-spec-bad.json'
    write(bad, '{"topic": "X", "lang": "en", "decisions": [{"seq": "Q1"}]}')
    result = subprocess.run(
        [sys.executable, '-B', str(script), '--spec', str(bad),
         '--out', str(WORK / 'gen-spec-bad.html')],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=30)
    check('gen_function_spec refuses incomplete decisions (exit 2)',
          result.returncode == 2
          and not (WORK / 'gen-spec-bad.html').exists())
    check('manifest documents the function spec generator',
          'gen_function_spec.py' in read(SCRIPTS / 'manifest.json'))


def validate_artifact_checks():
    # Deterministic standards are script-controlled (AGENTS.md): the
    # validator audits a generated artifact page - icon coverage, divider
    # count, dock structure, Title Case copy - and the artifact server
    # starts only after it passes.
    script = SCRIPTS / 'validate_artifact.py'
    if not script.exists():
        check('validate_artifact.py exists', False, str(script))
        return
    try:
        compile(read(script), str(script), 'exec')
        check('validate_artifact.py compiles', True)
    except SyntaxError as exc:
        check('validate_artifact.py compiles', False, str(exc))
        return

    def page(button_icon, heading_icon, body_extra, heading_text, css):
        icon = ('<svg viewBox="0 0 24 24"><path d="M4 4h16v16H4z"/></svg>'
                if button_icon else '')
        hic = ('<svg viewBox="0 0 24 24"><path d="M5 5h14v14H5z"/></svg>'
               if heading_icon else '')
        return ('<!DOCTYPE html><html><head><title>Fixture</title>'
                '<style>%s</style></head>'
                '<body><div id="dock" class="dock collapsed" '
                'aria-expanded="false">'
                '<button class="tab"><svg viewBox="0 0 24 24">'
                '<path d="M3 3h18v18H3z"/></svg>Design Preview</button>'
                '<button class="tab"><svg viewBox="0 0 24 24">'
                '<path d="M6 6h12v12H6z"/></svg>Function Spec</button>'
                '<button class="tab"><svg viewBox="0 0 24 24">'
                '<path d="M7 7h10v10H7z"/></svg>Decision Log</button>'
                '<button class="tab"><svg viewBox="0 0 24 24">'
                '<path d="M8 8h8v8H8z"/></svg>Version Ladder</button>'
                '</div><h1>%s%s</h1><p>Body copy.%s</p>'
                '<button class="act">%sSave Changes</button>'
                '<script>document.querySelector(".act")'
                '.addEventListener("click", function () {});</script>'
                '</body></html>'
                % (css, hic, heading_text, body_extra, icon))

    good_css = ('button { transition: transform .18s ease, opacity .18s ease;'
                ' background: var(--btn-bg) }'
                ' @media (prefers-reduced-motion: reduce) '
                '{ button { transition: none } }')
    bad_css = ('button { transition: all .9s ease }'
               ' .btn-a { background: #123456 }'
               ' .btn-a { background: #654321 }'
               ' .btn { color: #123456 }')

    good = WORK / 'artifact-good.html'
    write(good, page(True, True, '', 'Sample Page Title', good_css))
    result = subprocess.run(
        [sys.executable, '-B', str(script), '--html', str(good)],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=30)
    check('validate_artifact passes a conforming page (exit 0)',
          result.returncode == 0
          and '[OK] artifact standards passed' in result.stdout,
          ((result.stdout or '') + (result.stderr or ''))[:160])

    bad = WORK / 'artifact-bad.html'
    write(bad, page(False, False, '<hr><div class="divider"></div>'
                    '<p>\U0001f389 emoji</p>', 'sample page title', bad_css))
    result = subprocess.run(
        [sys.executable, '-B', str(script), '--html', str(bad)],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=30)
    payload_ok = False
    if result.returncode == 2 and '[ERR]' in result.stderr:
        try:
            tail = result.stderr.split('[ERR]', 1)[1]
            payload = json.loads(tail[tail.index('{'):])
            issues = payload.get('error', {}).get('errors', [])
            kinds = ' '.join(i.get('type', '') for i in issues)
            payload_ok = (len(issues) >= 3 and 'icon' in kinds
                          and 'divider' in kinds and 'title' in kinds
                          and 'token' in kinds)
        except (ValueError, IndexError):
            payload_ok = False
    check('validate_artifact reports all failures at once (exit 2)',
          payload_ok, (result.stderr or '')[:200])

    result = subprocess.run(
        [sys.executable, '-B', str(script)],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=30)
    check('validate_artifact refuses to run without --html/--url (exit 2)',
          result.returncode == 2 and '[ERR]' in result.stderr)


def audit_fix_checks():
    # Audit fixes (2026-10-31 neutral audit): every script's own failure
    # surface must follow the [ERR]+JSON contract so the orchestrating
    # model discovers errors BEFORE a service starts - including the gate
    # script itself.
    serve_src = read(SCRIPTS / 'serve_decision.py')
    check('code has: port fallback clamped to 65535',
          '65535' in serve_src and 'MAX_PORT' in serve_src)

    # validate_artifact: argparse failures and undecodable input go through
    # the [ERR] payload, and a CSS comment can never fail the motion check.
    va = SCRIPTS / 'validate_artifact.py'
    result = subprocess.run(
        [sys.executable, '-B', str(va), '--html', 'x.html', '--bogus', '1'],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=30)
    check('validate_artifact: argparse failure carries [ERR]+JSON (exit 2)',
          result.returncode == 2 and '[ERR]' in result.stderr
          and '{' in result.stderr)
    bin_html = WORK / 'artifact-bin.html'
    bin_html.write_bytes(b'\x80\x81\x82')
    result = subprocess.run(
        [sys.executable, '-B', str(va), '--html', str(bin_html)],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=30)
    check('validate_artifact: undecodable html reports [ERR] (exit 2)',
          result.returncode == 2 and '[ERR]' in result.stderr
          and 'UnicodeDecodeError' not in result.stderr)
    comment_css = ('button { transition: transform .18s ease }'
                   ' /* legacy 60ms timing kept for reference */'
                   ' @media (prefers-reduced-motion: reduce) '
                   '{ button { transition: none } }')
    good = WORK / 'artifact-comment.html'
    write(good, '<!DOCTYPE html><html><head><style>%s</style></head>'
                '<body><div id="dock" class="dock collapsed" '
                'aria-expanded="false"></div></body></html>' % comment_css)
    result = subprocess.run(
        [sys.executable, '-B', str(va), '--html', str(good),
         '--skip', 'icons,dividers,dock,titles'],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=30)
    check('validate_artifact: a CSS comment never fails the motion check',
          result.returncode == 0, result.stdout + result.stderr)

    # gen_xlsx: spec validation is all-at-once (error.errors[]).
    multi = WORK / 'xlsx-multi.json'
    write(multi, json.dumps({
        'candidates': [[{'bad': 'cell'}, 'ok']],
        'measured': 'not-a-table',
        'notes': ['n1']}))
    out = WORK / 'xlsx-multi-out.xlsx'
    result = subprocess.run(
        [sys.executable, '-B', str(SCRIPTS / 'gen_xlsx.py'), '--spec',
         str(multi), '--out', str(out)],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=30)
    multi_ok = False
    if result.returncode == 2 and '[ERR]' in result.stderr:
        try:
            payload = json.loads(result.stderr.split('[ERR]', 1)[1][
                result.stderr.split('[ERR]', 1)[1].index('{'):])
            multi_ok = len(payload.get('error', {}).get('errors', [])) >= 2
        except (ValueError, IndexError):
            multi_ok = False
    check('gen_xlsx: multi-issue spec reports all issues at once',
          multi_ok, result.stderr[:200])

    # gen_function_spec: a non-dict spec root and an unwritable --out
    # report [ERR]+JSON, never a traceback.
    gfs = SCRIPTS / 'gen_function_spec.py'
    bad_root = WORK / 'gen-spec-root.json'
    write(bad_root, '[1,2]')
    result = subprocess.run(
        [sys.executable, '-B', str(gfs), '--spec', str(bad_root),
         '--out', str(WORK / 'gen-spec-root.html')],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=30)
    check('gen_function_spec: non-dict spec root reports [ERR] (exit 2)',
          result.returncode == 2 and '[ERR]' in result.stderr
          and 'AttributeError' not in result.stderr)
    result = subprocess.run(
        [sys.executable, '-B', str(gfs),
         '--spec', str(WORK / 'gen-spec-input.json'),
         '--out', str(WORK)],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=30)
    check('gen_function_spec: unwritable --out reports [ERR] (exit 2)',
          result.returncode == 2 and '[ERR]' in result.stderr
          and not result.stderr.startswith('Traceback'))

    # serve_decision: an unwritable answers sink refuses before the port
    # binds - a completed round must never die at submit time.
    proc = subprocess.Popen(
        [sys.executable, '-B', str(SCRIPTS / 'serve_decision.py'),
         '--round', '91', '--answers', str(WORK), '--port', '8793',
         '--no-open'],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding='utf-8', errors='replace')
    try:
        served = False
        deadline = time.time() + 15
        while time.time() < deadline:
            line = proc.stdout.readline()
            if not line:
                break
            if '[OK] serving' in line:
                served = True
                break
        if served:
            # RED state only: the server started despite the unwritable
            # sink; stop it instead of waiting for an exit that never comes.
            proc.terminate()
        rc = proc.wait(timeout=20)
        err = proc.stderr.read()
        check('serve_decision: directory --answers refuses before serving',
              not served and rc == 2 and '[ERR]' in err,
              'rc=%s served=%s' % (rc, served))
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    # annotate_image: an svg payload under a non-svg name is refused (the
    # console serves by extension), extra notes never drop silently.
    import base64
    src = WORK / 'audit-px.png'
    src.write_bytes(base64.b64decode(PNG_1PX))
    stale = WORK / 'audit-ann.png'
    if stale.exists():
        stale.unlink()
    result = subprocess.run(
        [sys.executable, '-B', str(SCRIPTS / 'annotate_image.py'),
         '--img', str(src), '--out', str(WORK / 'audit-ann.png'),
         '--box', '0,0,1,1'],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=30)
    check('annotate_image: non-svg --out is refused (exit 2)',
          result.returncode == 2 and '[ERR]' in result.stderr
          and not (WORK / 'audit-ann.png').exists())
    result = subprocess.run(
        [sys.executable, '-B', str(SCRIPTS / 'annotate_image.py'),
         '--img', str(src), '--out', str(WORK / 'audit-ann.svg'),
         '--box', '0,0,1,1', '--box', '0,0,1,1',
         '--note', 'one', '--note', 'two', '--note', 'three'],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=30)
    check('annotate_image: dropped extra notes warn, never drop silently',
          result.returncode == 0 and '[WARN]' in result.stdout)


def baseline_checks():
    # The append-only growth check is a real script gate: the validator
    # diffs the current artifact page against the previous round's
    # snapshot -- confirmed regions carry zero changed markup.
    va = SCRIPTS / 'validate_artifact.py'
    base = WORK / 'baseline-prev.html'
    good = WORK / 'baseline-cur.html'
    head = ('<!DOCTYPE html><html><head><title>t</title><style>'
            'button { transition: opacity .2s ease }'
            ' @media (prefers-reduced-motion: reduce)'
            ' { button { transition: none } }</style></head><body>'
            '<div id="dock" class="dock collapsed" aria-expanded="false">'
            '</div>')
    appended = '<section class="newblock"><p>new element</p></section>'
    # The current page is the previous snapshot PLUS one appended block:
    # append-only -> pass.
    write(base, head + '</body></html>')
    write(good, head + appended + '</body></html>')
    result = subprocess.run(
        [sys.executable, '-B', str(va), '--html', str(good),
         '--baseline', str(base), '--skip', 'icons,titles,dividers,dock,tokens'],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=30)
    check('validate_artifact: append-only growth passes with --baseline',
          result.returncode == 0
          and '[OK] artifact standards passed (3 checks)' in result.stdout,
          result.stdout + result.stderr)

    # The current page REMOVED confirmed markup that the baseline had:
    # refuse with a baseline issue.
    removed = head.replace('<div id="dock" class="dock collapsed" '
                           'aria-expanded="false">', '') \
                   .replace('</div>', '') + appended + '</body></html>'
    write(good, removed)
    result = subprocess.run(
        [sys.executable, '-B', str(va), '--html', str(good),
         '--baseline', str(base), '--skip', 'icons,titles,dividers,dock,tokens'],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=30)
    refused = result.returncode == 2 and '[ERR]' in result.stderr
    if refused:
        try:
            tail = result.stderr.split('[ERR]', 1)[1]
            payload = json.loads(tail[tail.index('{'):])
            refused = any(i.get('type') == 'baseline'
                          for i in payload.get('error', {}).get('errors', []))
        except (ValueError, IndexError):
            refused = False
    check('validate_artifact: removed confirmed markup reports baseline',
          refused, result.stderr[:160])

    result = subprocess.run(
        [sys.executable, '-B', str(va), '--html', str(good),
         '--baseline', str(WORK / 'baseline-missing.html')],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=30)
    check('validate_artifact: a missing baseline file reports baseline',
          result.returncode == 2 and '[ERR]' in result.stderr
          and 'baseline' in result.stderr)


def probe_gate_checks():
    # D10/D11/D12: support probes run before options, probe results become
    # reference documents the function spec cites, and a deterministic gate
    # proves every aligned answer reached the function spec and the version
    # ladder.
    check('manifest documents the decision probe field',
          'support-probe document' in read(SCRIPTS / 'manifest.json'))
    check('manifest documents the coverage gate args',
          all(tok in read(SCRIPTS / 'manifest.json')
              for tok in ('--round-answers', '--snapshots', '--spec-data')))
    check('uiux-tree.md references the probe documents in the spec',
          'support-probe document' in read(SKILL / 'references' / 'uiux-tree.md'))

    # gen_function_spec: a decision with a probe path renders a design-time
    # link to the probe document.
    gfs = SCRIPTS / 'gen_function_spec.py'
    data = WORK / 'probe-spec.json'
    write(data, json.dumps({
        'topic': 'Probe Page', 'lang': 'en',
        'decisions': [{'seq': 'Q1', 'stage': 'S3', 'decision': 'Use the '
                      'clipboard API', 'probe': 'probes/clipboard.md'}],
        'criteria': []}, ensure_ascii=False))
    out = WORK / 'probe-spec.html'
    if out.exists():
        out.unlink()
    result = subprocess.run(
        [sys.executable, '-B', str(gfs), '--spec', str(data),
         '--out', str(out)],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=30)
    body = read(out) if out.exists() else ''
    check('gen_function_spec renders the probe document link',
          result.returncode == 0 and 'probes/clipboard.md' in body
          and 'href="probes/clipboard.md"' in body)

    # validate_artifact coverage gate: every confirmed answer reaches the
    # function spec data, and every answered round has its ladder snapshot.
    va = SCRIPTS / 'validate_artifact.py'
    page = WORK / 'probe-gate-page.html'
    write(page, '<!DOCTYPE html><html><head><style>button { transition: '
                'opacity .2s ease } @media (prefers-reduced-motion: reduce) '
                '{ button { transition: none } }</style></head><body>'
                '<div id="dock" class="dock collapsed" '
                'aria-expanded="false"></div></body></html>')
    spec_data = WORK / 'probe-gate-spec.json'
    write(spec_data, json.dumps({'decisions': [
        {'seq': 'q1', 'stage': 'S3', 'decision': 'Use the clipboard API'}]}))
    answers = WORK / 'probe-gate-answers-round1.json'
    write(answers, json.dumps([{'qid': 'q1', 'choice': 'Use the clipboard '
                                'API', 'note': '', 'ts': 1}]))
    snaps = WORK / 'probe-gate-snaps'
    snaps.mkdir(exist_ok=True)
    (snaps / 'snapshot-r1.html').write_text('<html></html>', encoding='utf-8')

    def gate(spec_data_path, snaps_dir, answers_path):
        return subprocess.run(
            [sys.executable, '-B', str(va), '--html', str(page),
             '--skip', 'icons,titles,dividers,dock,tokens,motion',
             '--spec-data', str(spec_data_path),
             '--round-answers', str(answers_path),
             '--snapshots', str(snaps_dir)],
            capture_output=True, text=True, encoding='utf-8',
            errors='replace', timeout=30)

    result = gate(spec_data, snaps, answers)
    check('validate_artifact: full coverage passes the gate (exit 0)',
          result.returncode == 0, result.stdout + result.stderr)

    partial = WORK / 'probe-gate-spec-partial.json'
    write(partial, json.dumps({'decisions': [
        {'seq': 'q9', 'stage': 'S3', 'decision': 'Something else'}]}))
    result = gate(partial, snaps, answers)
    kinds = ''
    if result.returncode == 2:
        try:
            tail = result.stderr.split('[ERR]', 1)[1]
            payload = json.loads(tail[tail.index('{'):])
            kinds = ' '.join(i.get('type', '')
                             for i in payload.get('error', {}).get('errors', []))
        except (ValueError, IndexError):
            kinds = ''
    check('validate_artifact: an unwritten answer reports a spec gap',
          'spec' in kinds, 'kinds=%r' % kinds)

    result = gate(spec_data, WORK / 'probe-gate-empty', answers)
    kinds = ''
    if result.returncode == 2:
        try:
            tail = result.stderr.split('[ERR]', 1)[1]
            payload = json.loads(tail[tail.index('{'):])
            kinds = ' '.join(i.get('type', '')
                             for i in payload.get('error', {}).get('errors', []))
        except (ValueError, IndexError):
            kinds = ''
    check('validate_artifact: a missing round snapshot reports a ladder gap',
          'ladder' in kinds, 'kinds=%r' % kinds)


def real_behaviour_checks():
    # D13: the artifact is the production 1:1 high-fidelity prototype -
    # real behaviour, real interfaces, real state - never a mockup.
    uiux = read(SKILL / 'references' / 'uiux-tree.md')
    check('uiux-tree.md defines the artifact as the high-fidelity prototype',
          'high-fidelity prototype, not a mockup' in uiux
          and 'never a drawn mockup' in uiux)
    check('uiux-tree.md pools the real behaviour audit',
          'Real behaviour audit' in uiux and 'click-through' in uiux)
    check('uiux-tree.md pools real state over fake state',
          'reads from the real data source' in uiux
          and 'sibling surfaces agree' in uiux)
    check('uiux-tree.md gate demands wired controls',
          'every control is wired to real behaviour' in uiux)
    check('manifest documents the behaviour check',
          'behaviour' in read(SCRIPTS / 'manifest.json')
          and 'no script' in read(SCRIPTS / 'manifest.json'))

    # validator: controls with zero behaviour declarations are a mockup.
    va = SCRIPTS / 'validate_artifact.py'
    dead = WORK / 'behaviour-dead.html'
    write(dead, '<!DOCTYPE html><html><head><style>button { transition: '
                'opacity .2s ease } @media (prefers-reduced-motion: reduce)'
                ' { button { transition: none } }</style></head><body>'
                '<button class="act"><svg viewBox="0 0 24 24">'
                '<path d="M4 4h16v16H4z"/></svg>Approve Draft</button>'
                '</body></html>')
    result = subprocess.run(
        [sys.executable, '-B', str(va), '--html', str(dead),
         '--skip', 'titles,dock'],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=30)
    kinds = ''
    if result.returncode == 2 and '[ERR]' in result.stderr:
        try:
            tail = result.stderr.split('[ERR]', 1)[1]
            payload = json.loads(tail[tail.index('{'):])
            kinds = ' '.join(i.get('type', '')
                             for i in payload.get('error', {}).get('errors', []))
        except (ValueError, IndexError):
            kinds = ''
    check('validate_artifact: controls with no behaviour are refused',
          'behaviour' in kinds, 'kinds=%r' % kinds)
    live = WORK / 'behaviour-live.html'
    write(live, '<!DOCTYPE html><html><head><style>button { transition: '
                'opacity .2s ease } @media (prefers-reduced-motion: reduce)'
                ' { button { transition: none } }</style></head><body>'
                '<button id="go" class="act"><svg viewBox="0 0 24 24">'
                '<path d="M4 4h16v16H4z"/></svg>Approve Draft</button>'
                '<script>document.getElementById("go")'
                '.addEventListener("click", function () {});</script>'
                '</body></html>')
    result = subprocess.run(
        [sys.executable, '-B', str(va), '--html', str(live),
         '--skip', 'titles,dock'],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=30)
    check('validate_artifact: wired controls pass the behaviour check',
          result.returncode == 0, result.stdout + result.stderr)


def dock_structure_checks():
    # The four dock tabs are structured and script-guarded: the Function
    # Spec's Evidence block (probe link + probe quotes + API name), the
    # generated decision-log alignment table, the fixed five-field version
    # ladder, and probe documents that must exist on disk.
    gfs = SCRIPTS / 'gen_function_spec.py'

    def run_gfs(extra):
        return subprocess.run(
            [sys.executable, '-B', str(gfs)] + extra,
            capture_output=True, text=True, encoding='utf-8',
            errors='replace', timeout=30)

    # An S3/S4 decision without probe or evidence refuses to generate.
    bare = WORK / 'dock-spec.json'
    write(bare, json.dumps({'topic': 'Dock', 'lang': 'en', 'decisions': [
        {'seq': 'Q1', 'stage': 'S3', 'decision': 'Use the clipboard API',
         'lands': ['state contract']}]}))
    out = WORK / 'dock-spec.html'
    if out.exists():
        out.unlink()
    result = run_gfs(['--spec', str(bare), '--out', str(out)])
    kinds = ''
    if result.returncode == 2:
        try:
            tail = result.stderr.split('[ERR]', 1)[1]
            payload = json.loads(tail[tail.index('{'):])
            kinds = ' '.join(i.get('type', '')
                             for i in payload.get('error', {}).get('errors', []))
        except (ValueError, IndexError):
            kinds = ''
    check('gen_function_spec: an S3/S4 decision without evidence refuses',
          'evidence' in kinds and not out.exists(), 'kinds=%r' % kinds)

    # A fully evidenced decision renders the structured Evidence block.
    (WORK / 'probes').mkdir(exist_ok=True)
    (WORK / 'probes' / 'clipboard.md').write_text('# probe', encoding='utf-8')
    full = WORK / 'dock-full.json'
    write(full, json.dumps({'topic': 'Dock', 'lang': 'en', 'decisions': [
        {'seq': 'Q1', 'stage': 'S3', 'decision': 'Use the clipboard API',
         'lands': ['state contract'],
         'probe': 'probes/clipboard.md',
         'evidence': ['scripts/clip.py:12 - clipboard.writeText supported'],
         'api': 'Clipboard API'}]}))
    out_full = WORK / 'dock-full.html'
    if out_full.exists():
        out_full.unlink()
    result = run_gfs(['--spec', str(full), '--out', str(out_full)])
    body = read(out_full) if out_full.exists() else ''
    check('gen_function_spec renders the structured Evidence block',
          result.returncode == 0
          and 'href="probes/clipboard.md"' in body
          and 'scripts/clip.py:12' in body
          and 'Clipboard API' in body)

    # The decision-log tab fragment is generated from the alignment data.
    align = WORK / 'dock-align.json'
    write(align, json.dumps({'alignment': [
        {'seq': 'Q1', 'question': 'Icon set', 'decision': None},
        {'seq': 'Q2', 'question': 'Layout', 'decision': 'Sidebar'}]}))
    result = run_gfs(['--spec', str(full), '--out', str(out_full),
                      '--alignment', str(align)])
    frag = WORK / 'dock-full-decision-log.html'
    check('gen_function_spec writes the decision-log fragment',
          result.returncode == 0 and frag.is_file()
          and 'Icon set' in read(frag) and 'Sidebar' in read(frag))

    # The version-ladder fragment carries the five fixed fields and
    # refuses a snapshot path that does not exist (r404 never exists,
    # even across suite runs).
    ladder = WORK / 'dock-ladder.json'
    write(ladder, json.dumps({'ladder': [
        {'version': 'v0.45', 'title': 'Dock added', 'decision': 'D5',
         'changes': 'append dock', 'snapshot': 'snaps/snapshot-r404.html'}]}))
    result = run_gfs(['--spec', str(full), '--out', str(out_full),
                      '--ladder', str(ladder)])
    kinds = ''
    if result.returncode == 2:
        try:
            tail = result.stderr.split('[ERR]', 1)[1]
            payload = json.loads(tail[tail.index('{'):])
            kinds = ' '.join(i.get('type', '')
                             for i in payload.get('error', {}).get('errors', []))
        except (ValueError, IndexError):
            kinds = ''
    check('gen_function_spec: a missing ladder snapshot refuses',
          'ladder' in kinds, 'kinds=%r' % kinds)
    (WORK / 'snaps').mkdir(exist_ok=True)
    (WORK / 'snaps' / 'snapshot-r45.html').write_text('<html></html>',
                                                     encoding='utf-8')
    write(ladder, json.dumps({'ladder': [
        {'version': 'v0.45', 'title': 'Dock added', 'decision': 'D5',
         'changes': 'append dock', 'snapshot': 'snaps/snapshot-r45.html'}]}))
    result = run_gfs(['--spec', str(full), '--out', str(out_full),
                      '--ladder', str(ladder)])
    frag_l = WORK / 'dock-full-version-ladder.html'
    body_l = read(frag_l) if frag_l.exists() else ''
    check('gen_function_spec writes the five-field ladder fragment',
          result.returncode == 0 and frag_l.is_file()
          and all(tok in body_l for tok in
                  ('v0.45', 'Dock added', 'D5', 'append dock')))

    # validate_artifact: a probe path that does not exist is refused.
    va = SCRIPTS / 'validate_artifact.py'
    page = WORK / 'probe-exist-page.html'
    write(page, '<!DOCTYPE html><html><body></body></html>')
    spec_data = WORK / 'probe-exist-spec.json'
    write(spec_data, json.dumps({'decisions': [
        {'seq': 'q1', 'stage': 'S3', 'decision': 'x',
         'probe': 'probes/missing.md'}]}))
    answers = WORK / 'probe-exist-answers-round1.json'
    write(answers, json.dumps([{'qid': 'q1', 'choice': 'x', 'note': '',
                                'ts': 1}]))
    snaps = WORK / 'probe-exist-snaps'
    snaps.mkdir(exist_ok=True)
    (snaps / 'snapshot-r1.html').write_text('<html></html>', encoding='utf-8')
    result = subprocess.run(
        [sys.executable, '-B', str(va), '--html', str(page),
         '--spec-data', str(spec_data), '--round-answers', str(answers),
         '--snapshots', str(snaps)],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=30)
    kinds = ''
    if result.returncode == 2 and '[ERR]' in result.stderr:
        try:
            tail = result.stderr.split('[ERR]', 1)[1]
            payload = json.loads(tail[tail.index('{'):])
            kinds = ' '.join(i.get('type', '')
                             for i in payload.get('error', {}).get('errors', []))
        except (ValueError, IndexError):
            kinds = ''
    check('validate_artifact: a missing probe document is refused',
          'probe' in kinds, 'kinds=%r' % kinds)

    # Contract lines.
    uiux = read(SKILL / 'references' / 'uiux-tree.md')
    check('uiux-tree.md contracts the structured Evidence block',
          'Evidence block' in uiux and 'generation refuses' in uiux)
    check('uiux-tree.md makes the dock tab fragments generated',
          'decision-log' in uiux and 'version-ladder' in uiux
          and 'never hand-built' in uiux)
    manifest = read(SCRIPTS / 'manifest.json')
    check('manifest documents the evidence and api fields',
          'evidence' in manifest and 'api' in manifest
          and 'support-probe document' in manifest)
    check('manifest documents --alignment and --ladder',
          '--alignment' in manifest and '--ladder' in manifest)
    check('manifest documents the probe existence check',
          'type probe' in manifest or 'missing probe document' in manifest)


def version_parity_checks():
    # D14: every ladder version is archived in version control (commit +
    # push + tag), implementation branches from tagged versions in
    # parallel, and the deployed build carries the same version tag.
    uiux = read(SKILL / 'references' / 'uiux-tree.md')
    check('uiux-tree.md archives every ladder version in version control',
          'committed and pushed' in uiux
          and 'branch from any tagged version' in uiux)
    check('uiux-tree.md archives the version verify script',
          'verify script' in uiux and 'named after the version' in uiux)
    check('uiux-tree.md pools version parity',
          'Version parity' in uiux and 'mismatch fails' in uiux)
    check('uiux-tree.md round close commits the version',
          'committed and pushed with its tag' in uiux)
    check('manifest documents the expected-version check',
          '--expect-version' in read(SCRIPTS / 'manifest.json')
          and 'type version' in read(SCRIPTS / 'manifest.json'))

    va = SCRIPTS / 'validate_artifact.py'
    page = WORK / 'version-parity.html'
    write(page, '<!DOCTYPE html><html><body><div id="dock" class="dock '
                'collapsed" aria-expanded="false">'
                '<span class="vtag">v0.45</span></div></body></html>')
    result = subprocess.run(
        [sys.executable, '-B', str(va), '--html', str(page),
         '--skip', 'icons,titles,dividers,dock,tokens,motion,behaviour',
         '--expect-version', 'v0.45'],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=30)
    check('validate_artifact: a matching dock version passes',
          result.returncode == 0, result.stdout + result.stderr)
    result = subprocess.run(
        [sys.executable, '-B', str(va), '--html', str(page),
         '--skip', 'icons,titles,dividers,dock,tokens,motion,behaviour',
         '--expect-version', 'v0.46'],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=30)
    kinds = ''
    if result.returncode == 2 and '[ERR]' in result.stderr:
        try:
            tail = result.stderr.split('[ERR]', 1)[1]
            payload = json.loads(tail[tail.index('{'):])
            kinds = ' '.join(i.get('type', '')
                             for i in payload.get('error', {}).get('errors', []))
        except (ValueError, IndexError):
            kinds = ''
    check('validate_artifact: a version mismatch is refused',
          'version' in kinds, 'kinds=%r' % kinds)


def gen_verify_checks():
    # The per-version verify script is generated, never hand-written from
    # scratch: version parity + baseline + a click-through skeleton that
    # refuses to pass until the per-version steps are filled.
    script = SCRIPTS / 'gen_verify_script.py'
    if not script.exists():
        check('gen_verify_script.py exists', False, str(script))
        return
    try:
        compile(read(script), str(script), 'exec')
        check('gen_verify_script.py compiles', True)
    except SyntaxError as exc:
        check('gen_verify_script.py compiles', False, str(exc))
        return

    def run_gen(extra):
        return subprocess.run(
            [sys.executable, '-B', str(script)] + extra,
            capture_output=True, text=True, encoding='utf-8',
            errors='replace', timeout=30)

    result = run_gen(['--url', 'http://127.0.0.1:9/x.html'])
    check('gen_verify_script: refuses to run without --version (exit 2)',
          result.returncode == 2 and '[ERR]' in result.stderr)
    result = run_gen(['--version', 'v0.80',
                      '--url', 'http://127.0.0.1:9/x.html',
                      '--prev-snapshot', str(WORK / 'no-such-snap.html'),
                      '--out', str(WORK / 'verify_v0.80.py')])
    kinds = ''
    if result.returncode == 2 and '[ERR]' in result.stderr:
        try:
            tail = result.stderr.split('[ERR]', 1)[1]
            payload = json.loads(tail[tail.index('{'):])
            kinds = ' '.join(i.get('type', '')
                             for i in payload.get('error', {}).get('errors', []))
        except (ValueError, IndexError):
            kinds = ''
    check('gen_verify_script: a missing prev snapshot refuses (exit 2)',
          'snapshot' in kinds, 'kinds=%r' % kinds)

    out = WORK / 'verify_v0.80.py'
    fixture_page = WORK / 'verify-fixture.html'
    write(fixture_page, '<!DOCTYPE html><html><body><div class="dock">'
                        '<span class="vtag">v0.80</span></div>'
                        '</body></html>')
    result = run_gen(['--version', 'v0.80', '--url', 'http://127.0.0.1:8797/'
                      'verify-fixture.html', '--out', str(out)])
    body = read(out) if out.is_file() else ''
    check('gen_verify_script: writes the pre-wired verify script',
          result.returncode == 0 and out.is_file()
          and "VERSION = 'v0.80'" in body
          and 'CLICKTHROUGH_FILLED = False' in body)
    check('gen_verify_script stdout carries [OK]', '[OK]' in result.stdout)

    fixture = subprocess.Popen(
        [sys.executable, '-m', 'http.server', '8797', '--bind',
         '127.0.0.1', '--directory', str(WORK)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.8)  # let the fixture bind before the first fetch
    try:
        # Unfilled click-through refuses to pass: an empty gate is a fake
        # gate.
        result = subprocess.run(
            [sys.executable, '-B', str(out)], capture_output=True,
            text=True, encoding='utf-8', errors='replace', timeout=30)
        unfilled = (result.returncode == 2 and '[ERR]' in result.stderr
                    and 'clickthrough' in result.stderr)
        filled = WORK / 'verify_v0.80-filled.py'
        write(filled, body.replace('CLICKTHROUGH_FILLED = False',
                                   'CLICKTHROUGH_FILLED = True'))
        result = subprocess.run(
            [sys.executable, '-B', str(filled)], capture_output=True,
            text=True, encoding='utf-8', errors='replace', timeout=30)
        check('verify script: version parity passes on the matching page',
              result.returncode == 0 and '[OK]' in result.stdout,
              result.stdout + result.stderr)

        mismatch_page = WORK / 'verify-mismatch.html'
        write(mismatch_page, '<!DOCTYPE html><html><body><div class="dock">'
                             '<span class="vtag">v0.79</span></div>'
                             '</body></html>')
        result = subprocess.run(
            [sys.executable, '-B', str(filled), '--url',
             'http://127.0.0.1:8797/verify-mismatch.html'],
            capture_output=True, text=True, encoding='utf-8',
            errors='replace', timeout=30)
        kinds = ''
        if result.returncode == 2 and '[ERR]' in result.stderr:
            try:
                tail = result.stderr.split('[ERR]', 1)[1]
                payload = json.loads(tail[tail.index('{'):])
                kinds = ' '.join(i.get('type', '') for i in
                                 payload.get('error', {}).get('errors', []))
            except (ValueError, IndexError):
                kinds = ''
        check('verify script: a version mismatch is refused',
              'version' in kinds, 'kinds=%r' % kinds)
        check('gen_verify_script: unfilled click-through refuses to pass',
              unfilled, 'unfilled rc/out checked above')
    finally:
        if fixture.poll() is None:
            fixture.terminate()
            try:
                fixture.wait(timeout=5)
            except subprocess.TimeoutExpired:
                fixture.kill()
    check('manifest documents the verify script generator',
          'gen_verify_script.py' in read(SCRIPTS / 'manifest.json'))


def prelaunch_checks():
    # Verify before it serves: the console refuses to start - the port
    # never binds, the browser never opens - when an option url is not
    # openable, and the served annotate page carries every toolbar button.
    serve = SCRIPTS / 'serve_decision.py'

    def spec_with(urls):
        opts = ','.join('{"label": "opt %d", "url": "%s"}'
                        % (i, u) for i, u in enumerate(urls))
        return ('{"title": "prelaunch", "round": 90, "lang": "en", '
                '"topic": "prelaunch", "alignment": [{"seq": "Q1", '
                '"question": "q", "decision": "d"}], "questions": '
                '[{"qid": "q1", "title": "t", "context": "c", '
                '"evidence": "wireframe", "options": [%s]}]}' % opts)

    for name in ('prelaunch-a', 'prelaunch-b'):
        write(WORK / (name + '.html'),
              '<!DOCTYPE html><html><body>%s</body></html>' % name)
    # The live-remote case probes against this fixture server.
    fixture = subprocess.Popen(
        [sys.executable, '-m', 'http.server', '8795',
         '--bind', '127.0.0.1', '--directory', str(WORK)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    cases = [
        # The loader rejects a missing static page at spec-load time; both
        # gates refuse before the port binds.
        ('a missing static page',
         spec_with(['missing-a.html', 'missing-b.html']), True, None),
        # Only the pre-launch gate probes remote urls: the loader accepts
        # the spec, then the gate refuses before the port binds.
        ('a dead remote url',
         spec_with(['http://127.0.0.1:9/x.html', 'prelaunch-a.html']),
         True, 'pre-launch'),
        ('valid static pages',
         spec_with(['prelaunch-a.html', 'prelaunch-b.html']), False, None),
        # A LIVE remote url must be ACCEPTED: the probe once crashed on a
        # missing urllib.request import and refused every remote option,
        # dead or alive - this case pins the accept path, not just the
        # refuse path.
        ('a live remote url',
         spec_with(['http://127.0.0.1:8795/prelaunch-a.html',
                    'prelaunch-b.html']), False, None),
    ]
    for name, spec_text, should_fail, needle in cases:
        spec_file = WORK / ('prelaunch-%s.json'
                            % name.replace(' ', '-'))
        write(spec_file, spec_text)
        proc = subprocess.Popen(
            [sys.executable, '-B', str(serve), '--spec', str(spec_file),
             '--round', '90', '--port', '8791', '--static-root', str(WORK),
             '--answers', str(WORK / 'prelaunch-answers.json'), '--no-open'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding='utf-8', errors='replace')
        try:
            out = ''
            served = False
            deadline = time.time() + 20
            while time.time() < deadline:
                line = proc.stdout.readline()
                if not line:
                    break
                out += line
                if '[OK] serving' in line:
                    served = True
                    break
            if should_fail:
                rc = proc.wait(timeout=30)
                err = proc.stderr.read()
                check('prelaunch refuses to start on %s' % name,
                      rc == 2 and '[ERR]' in err
                      and (needle is None or needle in err.lower()),
                      'rc=%s' % rc)
            else:
                check('prelaunch serves on %s' % name, served)
                m = re.search(r'\[OK\] serving (\S+)', out)
                if served and m:
                    body = urlopen(
                        m.group(1).rstrip('/')
                        + '/static/prelaunch-a.html?annotate=1',
                        timeout=5).read().decode('utf-8', 'replace')
                    want = ['grill-ann-toggle', 'grill-ann-save',
                            'grill-ann-return', 'grill-ann-proto',
                            'grill-tool-box', 'grill-tool-arrow',
                            'grill-tool-eraser', 'grill-ann-undo',
                            'grill-ann-redo', 'grill-ann-toolbar-top']
                    missing = [i for i in want if i not in body]
                    check('served annotate page carries every toolbar '
                          'button', not missing, str(missing))
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
    if fixture.poll() is None:
        fixture.terminate()
        try:
            fixture.wait(timeout=5)
        except subprocess.TimeoutExpired:
            fixture.kill()


def error_contract_checks():
    # The error reporting contract: every script reports failures with an
    # [ERR] marker line plus a JSON error object on stderr and a nonzero
    # exit code, so the orchestrating model can repair the input in one
    # round-trip; every script is documented in scripts/manifest.json.
    # AGENTS.md owns the rule. The annotator's top tools bar buttons follow
    # the console's button style: icon at the m size class, real disabled
    # state styled, keyboard focus visible.
    manifest = read(SCRIPTS / 'manifest.json')
    agents = read(SKILL / 'AGENTS.md')
    check('AGENTS.md carries the error reporting contract',
          '## Error reporting contract' in agents
          and '[ERR]' in agents
          and 'scripts/manifest.json' in agents)
    check('AGENTS.md checklist indexes the error reporting contract',
          '- [ ] Error reporting' in agents)
    check('manifest documents the [ERR] marker shape',
          '[ERR] marker line' in manifest)
    for name in ('gen_xlsx.py', 'audit_sections.py'):
        script = SCRIPTS / name
        if not script.exists():
            check('%s exists' % name, False, str(script))
            continue
        result = subprocess.run(
            [sys.executable, '-B', str(script)],
            capture_output=True, text=True, encoding='utf-8',
            errors='replace', timeout=30)
        check('%s reports failures with the [ERR] marker' % name,
              result.returncode == 2 and '[ERR]' in result.stderr,
              (result.stderr or '')[:160])
    src = read(SCRIPTS / 'serve_decision.py')
    check('annotator styles the top tools bar like the console',
          '#grill-ann-toolbar-top button {' in src
          and '.tool-ic { width: 15px' in src
          and '#grill-ann-toolbar-top button:disabled' in src
          and '#grill-ann-toolbar-top button:focus-visible' in src)


def live_checks(html):
    import importlib.util
    try:
        have_pw = importlib.util.find_spec('playwright.sync_api') is not None
    except ModuleNotFoundError:  # parent package missing: find_spec raises
        have_pw = False
    if not have_pw:
        check('playwright installed (needed for --live)', False)
        return
    page = WORK / 'alignment-layout.html'
    write(page, html)
    drive_page(page.as_uri(), 'live-file.png', 'file')
    server_checks()
    answers_flag_check()
    session_token_check()


def main():
    static_checks()
    html = render_checks()
    watcher_session_checks()
    server_guard_check()
    self_exit_check()
    annotate_checks()
    gen_spec_checks()
    validate_artifact_checks()
    audit_fix_checks()
    baseline_checks()
    probe_gate_checks()
    real_behaviour_checks()
    dock_structure_checks()
    version_parity_checks()
    gen_verify_checks()
    prelaunch_checks()
    error_contract_checks()
    if LIVE:
        live_checks(html)
    print('---')
    if failed:
        print('[ERR] %d failed: %s' % (len(failed), ', '.join(failed)))
        return 1
    print('[OK] all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
