# grill-tree: maintainer rules

These rules bind every agent that edits this skill. Read this file before any change.

## Where things live

- `SKILL.md`: entry point and round router. The router table names the class, the tree, the round preamble and the channel for each round. It also owns the round launch gate.
- `references/question-form.md`: the shared question form, evidence standard and delivery gate for every branch. Change them here, nowhere else.
- `references/design-tree.md`: design-tree round preamble (alignment table), drawing grammar, round mechanics (incl. the neutral challenge) and the acceptance-criteria pairing, plus its Round gates.
- `references/logic-tree.md`: logic-tree round preamble (ASCII tree in a text fence) and the .xlsx rule, plus its Round gates.
- `references/uiux-tree.md`: stages, production-mirror evidence rules, console flow and the criteria pool, plus its Stage gates, the state display contracts, the agent participation contracts and the unified design principles module. Add one entry per confirmed decision.
- `references/doc-tree.md`: the doc round rules (diff-block rounds) and its Round gates.
- `scripts/serve_decision.py`: spec loader, renderer and local server for the decision console.
- `scripts/manifest.json`: machine-readable console contract. It must stay valid JSON.
- `scripts/gen_xlsx.py`: builds the logic-tree .xlsx attachment.
- `scripts/gen_function_spec.py`: renders the design-time function spec page from decisions data (the page's only writer).
- `scripts/validate_artifact.py`: audits a generated artifact page (icon coverage, dividers, dock structure, Title Case, motion, token consistency, behaviour, append-only baseline, round-close coverage gate, version parity) and gates serving: the artifact server starts only after the validator passes.
- `scripts/gen_verify_script.py`: generates the per-version deployment regression script (version parity + baseline + a click-through skeleton that refuses to pass until filled); the generated script is committed with the version tag.
- `scripts/annotate_image.py`: draws numbered evidence boxes on a console capture (SVG output).
- `scripts/check_skill.py`: maintainer checks. Run it after every change.

## Routing lives in one place

- When and why to read a reference file is decided only by the router table in `SKILL.md`. Reference files carry no "when to read", "use when", or trigger sentences of their own; a copy drifts out of sync with the router.
- A reference file opens with its title, then its content. Scope notes that describe what the file governs (not when to read it) may stay.
- Before adding a trigger sentence to any reference file, add or change the matching router row in `SKILL.md` instead.

## One meaning, one home

- A rule that more than one file uses lives in exactly one home: `SKILL.md` owns routing, `references/question-form.md` owns question form and evidence content, `scripts/manifest.json` owns script behaviour. Every other file carries a pointer, never a copy.
- Before adding a paragraph, search the skill for its meaning; if it exists, link to it instead of writing it again.
- Session residue never ships: wording such as "needs confirmation", "not defined" or "proposed" is resolved or dropped before a change lands. A rule enters the skill only as settled.

## Tree files share one skeleton

- Every tree reference (`design-tree.md`, `logic-tree.md`, `uiux-tree.md`, `doc-tree.md`) opens with an H1 title `# <Tree> (<classes> rounds)` and uses exactly four H2 sections, in this order: `## Round preamble`, `## Round rules`, `## Evidence`, `## Round closing`.
- Branch-specific material sits as H3-or-deeper subsections (branch-named) under Round rules.
- `references/question-form.md` is exempt: it is the shared standard, not a tree.
- check_skill.py enforces the skeleton; a restructure writes the failing check first (RED), then the files (GREEN).

## Script owns behaviour (no duplicate descriptions)

- Behaviour that a script or the manifest already implements (console keys, auto-advance, lightbox, toast, answers file format, input field names, exit codes, output shape) is documented only in `scripts/manifest.json` and the script's own header. Reference files point to the manifest instead of restating it.
- A reference file keeps only the rules an agent must follow that no script can enforce: when to call a script, what to put in a round, the judgement rules.
- Before writing a behaviour line into a reference file, check the manifest and the script header. If they already say it, write a pointer instead.
- A script's docstring keeps usage, modes and the error shape only; behavioural detail lives in the manifest alone.
- Behaviour changes go into the script and the manifest first. Then run `python -B scripts/check_skill.py`.

## Error reporting contract

- Every script reports failures the same way: one `[ERR] <title>` marker line, then a JSON error object on stderr (`error.errors[]` where the shape applies), and a nonzero exit code. The orchestrating model repairs the input from that payload in one round-trip.
- Every script is documented in `scripts/manifest.json` (purpose, args, output contract, exit codes). A script without a manifest entry is a violation; an undocumented error shape is a violation.
- An error the model can repair never surfaces as a bare failure page or a silent fallback: validation fails at load time with a corrective fix, before anything reaches the user.

## Maintainer checks never open a browser

- Every launch of `serve_decision.py` from a maintainer check passes `--no-open`, so no decision page pops up in the user's browser. check_skill.py enforces this.

## UI decisions go in five stages

- An interface decision runs in order: whole page (S1), block (S2), element (S3), interaction scenarios (S4), visual sweep (S5). The Stages table in references/uiux-tree.md is the only place the order and the per-stage definitions live; check_skill.py requires its S1-S5 rows. A later stage is not drawn until the earlier one is confirmed.
- A greenfield interface walks all five in order; a refinement — a confirmed artifact already exists — enters at the change's scope with the baseline confirmed (entry rules: references/uiux-tree.md, Two entries).
- The function spec is design-time and never implemented into production: on a generated artifact it rides as a "Function Spec" tab (toggling function-spec.html, "Function Spec (Aligned)"); in refinement it stays a standalone function-spec.html beside the real page.
- The artifact page carries the design-time dock — design preview, function spec, decision log, version ladder — collapsed by default; the dock and its tabs never enter the production mirror.
- Elements enter the artifact as their own 1:1 fragments — drafted first, confirmed, then appended into the cumulative page; confirmed regions are never regenerated (references/uiux-tree.md owns the rule).
- The version ladder keeps one entry and one snapshot per confirmed round, so the artifact's growth stays replayable and every append is diffable against its neighbour.
- Deterministic interface standards (icons, dividers, Title Case, dock structure, motion, token consistency) are script-controlled: `scripts/validate_artifact.py` audits a generated artifact page, and the artifact server starts only after the validator passes.
- Every interactive operation carries a micro-to-medium motion styled after the host system's native motion first, nothing heavier than medium; reduced motion disables it. Every UI/UX criterion is verified on the deployed environment with a browser-automation or computer-control tool; a verify method naming only a local machine never passes.
- Implementation support is probed, never assumed: options depending on an API or existing code reach the user only after that support is verified — searching the user's knowledge base first, then the real environment — and the probe result becomes a reference document the function spec cites; an S3/S4 decision without probe or evidence refuses generation.
- The UI lens never swallows decisions or logic: an alignment answer that settles a trade-off opens a design-tree round, and an answer carrying procedural logic opens a logic-tree round, before it is realized.
- The artifact is the production 1:1 high-fidelity prototype, not a mockup: every control is wired to real behaviour, every displayed state reads the real data source, and sibling surfaces agree.
- Every S3/S4 option is the whole current artifact copied 1:1 with the candidate applied — never an isolated fragment page; the winner appends mechanically without a re-confirmation round.
- The round close (every S2-S5 round) appends the confirmed element, re-captures the page, writes the version ladder entry and snapshot, syncs the function spec, and commits and pushes with the version tag — verified by the deterministic coverage gate (spec, probe and ladder types), so an aligned-but-unwritten decision is refused. Implementation branches from any tagged version in parallel; Version parity holds: the deployed build's version tag equals the prototype's tagged version, checked by the generated per-version verify script.
- S2 carries no interaction. Interaction belongs to S1 (global conventions), S3 (single-element behaviour) or S4 (cross-element scenario contracts); check_skill.py requires the S2 row to say so.
- Every stage runs as full design-tree rounds; the walk never pauses between stages, and S4 opens with a combed scenario inventory (convenience first) before any option is authored. check_skill.py pins both.

## Generality (no case-specific rules)

- Skill rules are domain-agnostic. A rule states a general behaviour. Its wording never uses a specific product, event, persona, or data example.
- Project principles live in that project's own docs. The skill may refer to them as optional input, but never copies them in.
- Test before adding a rule: would it still hold for a different project? If not, it does not belong in the skill.
- A user's own words may source a rule in the project file. In the skill, the rule is written in general terms only.
- The skill is a general-purpose skill for any scene. Every rule must hold without any named product, vendor, tool, or event. Use "a generator", "a validator", "a record" instead of specific names.
- Conditions are stated as triggers ("when the interface is generated"), never as a project's situation.
- Examples in references use placeholders (`[column_name]`, `<gloss>`, "the entity the user tracks"), never real field names or business dimensions from a project.

## Paths (never break)

- Skill files never contain an absolute path, a drive letter, a user name, a persona name, a session name, or a machine-specific folder.
- Find the skill from the script's own location: `Path(__file__).resolve().parents[1]`.
- Find the home folder with `Path.home()`. The skill lives at `~/.claude/skills/grill-tree`.
- Find temp space with `tempfile.gettempdir()`. Never hard-code `/tmp` or a user temp folder.
- Image paths and answer files come from the spec or the command line, never from a constant. The temp folder is the default answer path only when `--answers` is omitted.
- Docs and examples use placeholders without drive letters, for example `images/a.png`.

## Language and encoding

- Every skill file is English only: zero CJK characters. Write a Chinese label in code as `\uXXXX`. Chinese spec data is fine, but it lives outside the skill.
- Markdown files use CRLF line endings. Check after every edit.
- Python: pass `encoding='utf-8'` to `open`, `json`, `subprocess` and write calls. Status markers are ASCII only: `[OK]`, `[ERR]`, `[WARN]`, `[INFO]`, `[SKIP]`.

## Shell and edits

- Never inline Python that contains backticks, `$`, or nested quotes in a PowerShell string: the shell eats them. Write the script to a file with the write tool and run it with `python -B`.
- Use the edit tool for targeted changes. Never run two edits on the same file in parallel: they race.
- Always run Python with `-B`, so no `__pycache__` folder appears in the skill.

## Console spec and behaviour

- The console page language follows the session language: the spec author sets the page `lang` to the session language every round; fixed copy renders from the script's built-in table, never authored ad hoc in the spec.
- Spec text has no bare `<...>` placeholders in user-visible text.
- `lang` and `topic` are top-level fields. `prob_label` belongs to each question.
- An alignment row with a `qid` links to a card on the page, and its `decision` must be null. A row without a `qid` is prior-round history and stays static.
- The renderer owns the bullet marks and the Reason, Example, Pros and Cons leads. It strips the same markers when the author writes them.
- A timer that fires later captures its target index when it is scheduled. Any state change cancels the pending timers.
- While the lightbox is open it owns the keyboard. Escape closes it.
- Reduced motion disables every transition.
- A rendered option carries both its boxed capture and its live url; the loader refuses to serve a rendered spec that misses either.
- Verify before it serves: serve_decision.py runs deterministic pre-launch checks (every option url openable; the annotator toolbar complete in the injected page) and refuses to start with an [ERR] payload - the port never binds and the browser never opens on failure.
- Spec validation is a one-shot error-list loop: the [ERR] payload carries every issue at once as error.errors[] ({loc, type, msg, fix}); the agent repairs the whole list and retries once, never one issue at a time.

## Safety

- No script writes an answers file on its own. Only the user's Submit writes one.
- No test clicks Submit. Tests render pages to local files and never POST.

## Gates

- After any change under `scripts/` or `references/`: `python -B scripts/check_skill.py` must end with `[OK] all checks passed`.
- After any change to the console UI or its JavaScript: also run `python -B scripts/check_skill.py --live`.
- If a check fails, fix the cause. Never weaken a check to make it pass.
- If a discovery mirror of this skill exists (a second skills folder the host scans), copy every changed file to it in the same change and verify with a recursive diff before reporting the change done. The copy this file lives in is canonical.
- `check_skill.py` also fails on user names, persona names, and session words.

## Checklist gates

- Script gates check what a machine can check. What only a reader can check (structure, spirit, no drift) passes through a checklist walk: after any change, before claiming done, re-read this file, walk the list below, and show every item ticked in the closing message.
- Tick an item only after re-verifying it in the actual files just changed. A tick without a fresh verification is a failed gate; an unticked item blocks the change.
- The list indexes the sections of this file; it adds no rules of its own.
- Runtime gates use the same ritual: each reference carries its tick-list at the point of use; a round launches only with its launch gate ticked and closes only with its close gate ticked.

- [ ] Routing lives in one place: the SKILL.md router owns when-to-read; no reference carries trigger sentences.
- [ ] One meaning, one home: no rule restated; other files carry pointers, not copies.
- [ ] Tree files share one skeleton: H1 + four fixed H2 slots; branch material sits branch-named underneath.
- [ ] Script owns behaviour: console behaviour lives in the manifest and script headers; references point, never restate.
- [ ] Error reporting: scripts fail with an [ERR] marker line plus a JSON payload on stderr; every script has its manifest entry.
- [ ] Generality: every new rule holds for a different project; no product, event, persona, or session example.
- [ ] Paths never break: no absolute path, drive letter, user or session name; temp/home resolution only.
- [ ] Language and encoding: zero CJK in skill files, CRLF markdown, utf-8 writes, ASCII status markers.
- [ ] Console spec and behaviour: the manifest and script still own every key, timer, marker and field the change touches.
- [ ] Maintainer checks never open a browser: every scripted launch passes --no-open.
- [ ] Safety: no script writes an answers file on its own; no test clicks Submit.
- [ ] UI decisions go in five stages: order and per-stage definitions live only in the Stages table of uiux-tree.md.
- [ ] Deterministic standards are script-controlled: the validator audits the artifact page and the artifact server starts only after it passes.
- [ ] Support-probe before options: knowledge base first, then the real environment; probe results become reference documents the function spec cites.
- [ ] Round close commits: append, re-capture, ladder entry + snapshot, spec sync, commit/push/tag with the generated verify script — all gate-verified before the next round.
- [ ] Every UI/UX criterion verifies on the deployed environment with a browser-automation or computer-control tool.
- [ ] The design-time dock (four tabs) never enters the production mirror; interactive operations carry micro-to-medium motion.
- [ ] Session residue never ships: wording is settled; this file stays a principles file, never turn it into a change log.

## Changing the skill

- Align each change first: show a before/after diff with the reason and the pros and cons. Apply only after the user says yes.
- Any change a check can pin — script, reference, or this file — writes the failing check first (RED), then the change (GREEN).
- Round notes that critique the console itself are tool feedback: fix the tool in the same session (RED then GREEN), then mirror.
