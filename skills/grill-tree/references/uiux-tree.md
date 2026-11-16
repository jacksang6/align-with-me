# UI tree (UI and UX rounds)

This protocol governs evidence, acceptance criteria, and the decision console for everything the user sees and touches. UI and UX do not build a third tree: both follow the design tree's decision process (references/design-tree.md), routed here by SKILL.md. The protocol is host-, platform-, and domain-agnostic; between hosts only the design-token list and the supported width/language lists change.

## Round preamble

UI and UX rounds walk the design tree's process (references/design-tree.md), not a separate one: frontier discipline, the four round header lines (audit line, answer-back checklist, agreed list, criteria checklist), confirmation closure, and criteria pairing at confirmation all apply. The UI lens never swallows decisions or logic: an alignment answer that settles a trade-off (approach, architecture, parameters) opens a design-tree round for that decision before it is realized, and an answer that carries procedural logic (if/then, state changes, flows, calculations) opens a logic-tree round — one round runs one tree, the audit line counts both trees every round, and realization waits until the spawned round confirms. The alignment surface is the console page itself: every console spec carries `topic` and `alignment` — one row per question asked so far in this tree, decided rows filled with their chosen option text, this round's rows linked by `qid` and filled in live as cards are answered. A spec without alignment rows is incomplete: the user must see the whole tree state at the top of every round's page, and the header lines ride the notify message of the launch contract.

**Layout means the region map, drawn as a wireframe**: which regions exist and what each region holds. A wireframe is the skeleton — outlined boxes for regions, each box labelled with the region's role (what goes there), placeholders standing in for content. It carries **no concrete content and no visual styling**: no real data rows, no colours, no typography — it shows what a region does, not what it looks like. But it is drawn on the **real page canvas at true viewport size**: regions carry their true sizes and proportions, because the 1:1 principle starts at the wireframe — a wireframe that shrinks the canvas or its regions into a small frame is wrong, no matter how pretty. The wireframe is a schematic, like the trees' `text` fences — **not the artifact**: the production-mirror rules below govern the artifact and do not apply to the S1 wireframe. A layout option is stated as that wireframe (a `text` fence of boxes, or a full-size skeleton capture), never as prose about look and feel, and never as a styled page with real content. A region's purpose carries semantic assumptions: the logic model its skeleton presupposes — how selections combine, when they take effect, what the region counts. S1 names them per region; one that changes the skeleton opens a logic sub-round (routed to the logic tree) before the frame is confirmed. The layout never rests on an unstated premise.

| Stage | Aligns | Input | Confirmed output | Exit condition |
|---|---|---|---|---|
| S1 Whole page | Design principles, the layout as a region wireframe (which region holds what) plus region positions and size classes, each region's semantic assumptions (the logic model its skeleton presupposes — how selections combine and when they apply), overall colour system, global interaction conventions | Confirmed reference baseline | Principle items, region wireframe (labelled boxes) with its region table, colour table, semantic assumptions, global interaction items | The user confirms every item, and every semantic assumption is confirmed or answered in a logic sub-round |
| S2 Block | What each block is for and what it contains (no element detail, no interaction) | S1 output | One content entry per block | Every block is confirmed |
| S3 Element | Each element's component, text, icon, and element-level interaction (the element's own immediate behaviour; cross-element scenario flows go to S4) | The S2 entry of its block | Element list with interaction items | Every element of every block is confirmed |
| S4 Interaction | A combed scenario inventory first: every scenario the interface serves — who, with what goal, in which context; convenience first, each scenario must help the user close its loop — with happy paths and edges (empty, overlong, duplicate, failure) named before any option is authored. Then each scenario's interaction contract: how the interface feeds back at every step — trigger, immediate feedback, state change, recovery and end states; keyboard parity, reduced-motion parity. Each scenario also walks the state machine: every non-ideal state carries a display contract (state display contracts under Round rules). The inventory also combs the agent layer: every scenario where the agent initiates or participates — surface problems, assist the fix, deepen the analysis, remind proactively, self-learn from corrections — is a scenario of its own (agent participation contracts under Round rules). Crosses elements: a flow spanning several confirmed elements belongs here, not in S3 | The S3 element list | One combed scenario list, each scenario with its contract (trigger → feedback → state change → recovery), its state contracts, its agent-participation contract where applicable, and parity items | Every scenario in scope is confirmed |
| S5 Visual sweep | The composed page audited against the four visual principles: contrast, repetition, alignment, proximity. The host project's own UI/UX standard — its style guide, design tokens, component and feedback conventions — is a hard acceptance baseline when it exists: the artifact conforms to it, verified on the deployed environment; with no project standard, the confirmed reference baseline governs. The standard is referenced, never copied in | The S1-S4 outputs | A four-principles audit round; each finding paired and decided | Every finding is resolved |

Every stage S1-S5 runs as full design-tree rounds: the walk through references/design-tree.md never pauses between stages. Each stage re-applies the round mechanics at its own scope — frontier discipline, the four round header lines, criteria pairing at confirmation, and its own closing sweep. The stage changes the scope, never the process.

### Two entries (greenfield and refinement)

The stages are lenses; what already exists decides which lenses a session walks. Routing is two-layer: SKILL.md routes the class here, and this tree routes itself by entry before any round opens.

**Entry routing.** The entry is judged from the context — does the target surface exist as an implemented page or a confirmed artifact? The judgment is automatic, never a round question of its own; genuine ambiguity becomes the scope round's first question.

| Context detection | Entry | Lenses |
|---|---|---|
| The target exists as an implemented page or a confirmed artifact | Refinement | The scope round picks the lens (S1/S2 region, S3 element, S4 scenario, S5 sweep) |
| No implemented page or confirmed artifact exists | Greenfield | All five, in order |


1. **Greenfield entry** — no confirmed artifact exists. The session walks all five stages in order, and a later stage is not drawn until the earlier one is confirmed.
2. **Refinement entry** — a confirmed artifact already exists (a shipped interface, or a prototype whose walk closed). Its current state is the baseline: every stage the baseline already settles counts as confirmed. The session opens with a **scope round** that names the surface the change touches, then works the change at its own lens — a layout change works the affected region with the S1/S2 lens; an element change works the S3 lens; an interaction change works the S4 lens (trigger → feedback → state change → recovery, the state display contracts, keyboard and reduced-motion parity, the agent layer where it participates); a visual polish sweeps the touched surface with the S5 lens. Surfaces the change does not touch stay confirmed; the refinement itself never re-opens them. The annotation view behaves identically in both entries: opening it carries the AI evidence boxes and the same toolbar, and every annotation action works the same way.

**The prototype round (when words cannot say it).** Refinement annotating has a ceiling: the user can mark what is wrong but cannot always say what the change should be, and a written annotation never shows what the result looks like. When the user cannot express the change in words, they request a generated prototype from the annotate page; the agent answers with a prototype round on that scope:

**Scope ask.** A prototype request starts with one scope question, asked once, in the session's language and novice terms: rebuild every prototype from the first stage, prototype only the marked part, or fold the change into the confirmed prototype (the default — the confirmed page copied 1:1 with the change applied, this section's existing contract). The question tool carries the ask; a console round opens only after the scope is answered. Nothing is generated until it is answered.

- Each variant is a real rendered page: the confirmed real page copied 1:1 with the change applied, so the user sees the result, not a description of it.
- Every prototype page carries a header tab row (the variant letters and the function spec) so the variants and the spec flip in place.
- The annotation view stays entry-uniform on the prototype pages, and the AI evidence vocabulary (move, icon, color) applies to the variants the same way.
- Any user feedback regenerates only the commented variant and the agent re-confirms it in a new round; the agent never assumes it understood the intent. Uncommented variants stay as they are.
- After a variant is confirmed, the change is implemented 1:1 into the real page. Prototype pages and the function spec are design-time pages: they never enter the production mirror.

A stage is one or more rounds. Its scope fans out into as many rounds as the scope needs — blocks, elements, scenarios (one combed scenario may need its own round). A stage exits on its exit condition, never on a round count.

Write-in contract: a write-in answer is feedback, never a stage exit. The agent applies the custom answer across the whole artifact first, then re-asks the item with the applied answer rendered as an authored option — the user sees the real result and confirms an authored option before the item closes. A write-in at any stage re-opens every stage from S1, each marked awaiting re-confirmation: a custom answer changes the premise the confirmed stages rest on, so the walk restarts from S1 and closes stage by stage, every stage on an authored confirmation. This re-open-all rule is the greenfield rule: in the refinement entry a write-in re-opens only the scopes its content touches, and untouched surfaces stay confirmed.

**Self-check before ask.** Every UI task runs its own scripted browser verification before any user-facing ask: the page loads, no page errors fire on the console, and the interactions the round depends on actually work. An artifact that fails its self-check never reaches the user — fix it first; asking the user about a broken artifact is a violation.

**Realization gate.** A stage's confirmed output is realized in the artifact before the next stage's round launches: S1's confirmed frame is built as the artifact's real skeleton at true sizes, and every later stage builds on the artifact that embodies all confirmed decisions so far. Every capture follows the decisions — a capture whose context redraws or contradicts a confirmed stage is stale evidence: realize first, re-capture, re-ask. The realization is real, never a mock: from the moment a stage's output is implemented, the production-mirror rules govern it.

**Novice-first design.** All scenario and interface design assumes a user who has never heard of an agent: no agent vocabulary in copy, explanations speak in the user's own scenario terms, labels stay standardized yet phrased for the scenario. Design from the professional viewpoint, and spend that rigour on the user's three costs: understanding — a feature is graspable with little mental effort; mental effort — the hierarchy is clear, what belongs to what reads off the structure; operation — configuration written from the user's viewpoint, zero technical terms, in the spirit of the best minimal-settings designs. Minimal is cognitive, not stripped: every feature and every affordance (icons and visual elements included) stays.

### Design principles

One home for the principles every round and stage applies at its own scope. Each line is an index; the detailed contract stays where it lives.

**Human-machine principles** (the user's scenario view):

1. Status visibility — what the system is doing and where it stands stays visible; the five states (loading, empty, partial, error, ideal) are its floor (state display contracts).
2. Speak the user's language — copy phrased for the user's scenario, zero jargon; the interface resembles the user's world, not the machine's.
3. User control and freedom — every action is reversible or exitable; there is always a way back.
4. Consistency and standards — like things are expressed alike; labels stay standardized.
5. Prevention over correction — stop an error before it happens; when one slips through, preserve the user's input and offer the guessed fix one click away.
6. Recognition over recall, low mental effort — options and state are visible; a feature is graspable with little mental effort.
7. Flexibility and accelerators — keyboard paths pair with pointer paths.

**Human-agent principles** (agent participation contracts):

8. Intent preview — a consequential action shows its plain-language plan first (proceed, edit, or do it myself); the irreversible always waits for confirmation.
9. Autonomy matches risk — autonomy is granted by the user, never seized by the system.
10. Explainable rationale — "because X, I did Y", human-readable, never a log dump.
11. Confidence signaling — the agent shows how sure it is and how far the claim reaches.
12. One-step dismissal and correction — rejecting or rewriting is one step away; the agent learns from the correction.
13. Audit, undo, escalation — actions leave a trace with a stated undo window; on ambiguity the agent asks instead of guessing.

**Visual and interface principles**:

14. The four visual principles — contrast, repetition, alignment, proximity (every round's lens, the S5 sweep).
15. Visual hierarchy — size, colour and spacing steer the eye; the important is seen first.
16. Novice-first, three costs — assumes a user who has never heard of an agent; designed from the professional viewpoint for the user's understanding, mental effort and operation; minimal is cognitive, not stripped (the Novice-first paragraph owns the full wording).
17. Decoration stripped — nothing that carries neither information nor affordance; a separator is whitespace by default, and a visible divider must be proven by a functional grouping: a repeated entry list (one row per item) is exactly that proof, while between blocks and sections whitespace carries the separation alone (the criteria pool's divider audit is its check).
18. Icon consistency — every title and every button control carries an icon from the interface's single declared icon set; icon style and semantics stay consistent; emoji never serves as an icon.
19. Title Case copy — every heading and every button renders its English copy in Title Case; other scripts are out of scope.
20. Micro-to-medium motion — every interactive operation carries a micro-to-medium transition (a natural slide, fade or scale); nothing heavier than medium; the motion's style follows the host system's native feel first — a natural ease-out slide or fade, spring-light, never showy; reduced motion disables every transition.

Rollback: when any stage changes, every downstream stage is marked awaiting re-confirmation. The direction never flips: a change at a later lens never re-opens an earlier lens's confirmed surface on its own.
Each stage is drawn in the alignment-table-plus-console format of the console flow below, so its decisions are visible before the next stage starts.

## Round rules

### The artifact (two servers, two lifetimes)

The **artifact** is the growing prototype page: ONE cumulative page. It is the **production 1:1 high-fidelity prototype, not a mockup**: every button carries its real behaviour, every interaction runs its real interface (probed per the question form's support rule and implemented for real), and every displayed state reads its real data — a drawn-but-inert control never ships in it. Confirmed elements render in their final state and stay put; each round adds or changes one group of related elements. Every element enters as its own 1:1 fragment — real tokens, true sizes — drafted first, confirmed, then appended into the cumulative page in the same realization step; confirmed regions are never regenerated, and every append re-captures the whole page. Every round's captures show the whole current page, so the user judges the new element in the context of everything already confirmed — never as an isolated fragment. When the artifact is complete, it is the 1:1 production reference.

- The artifact server hosts the artifact. It is long-lived: the user can open it at any time, between rounds included. After the S1 frame is confirmed it is the single source of truth for UI state. The artifact server starts only after `scripts/validate_artifact.py` passes on the page it is about to serve (the manifest owns the validator's contract).
- The console (`scripts/serve_decision.py`) is short-lived: it serves one round and exits by itself once the user submits.
- The console references the artifact — an annotated capture with an Open-in-tab link — and never carries a copy of the UI itself.

### Function spec

The prototype alignment maintains a **function spec**: a living document beside the artifact that records every confirmed UI/UX decision — stage, what was decided, why, and the rules it lands (states, scenarios, contracts). Each confirmed decision enters the function spec in the same change that realizes it in the artifact (the realization-gate moment); the spec and the artifact never drift. The function spec is the written twin the production build reads.

**Format contract.** The spec page has a fixed skeleton, so the production build reads it back without guessing: the replication banner first; then the **Confirmed decisions** table — columns Seq, Stage, Decision, Why, Lands, one row per confirmed decision in confirmation order (Stage names the lens that confirmed it; Lands carries the rules the decision lands — state contracts, scenario contracts, agent participation — plus the structured **Evidence block**: the link to the decision's support-probe document, one to three probe quote lines (file:line or command output), and the confirmed capability name; generation refuses an S3/S4 decision that carries neither probe nor evidence — a decision without implementable evidence is a fake decision); then the **Criteria** section — one line per paired criterion, `C-id (tag): criterion — verify: method`. A section with nothing confirmed yet is omitted, never left empty; the page language follows the session language. The page is generated, never hand-built: the generator script is its only writer (scripts/manifest.json owns its contract).

On a generated (greenfield) artifact the function spec rides as a design-time **"Function Spec" tab** on the artifact page: the tab toggles a panel loading `function-spec.html` — titled **"Function Spec (Aligned)"**, listing every confirmed decision with its stage and decision text, banner "AI replicates production 1:1 from this spec and the prototype HTML; design-time only: never implement this page or this tab" — and the tab and the spec page are never implemented into production: the 1:1 production mirror covers the artifact's own surface alone, and the production build starts from the artifact without the tab. Each confirmed round appends its decisions to the page in the same change that realizes them. In the refinement entry the real page is never decorated with design chrome: the function spec stays the standalone `function-spec.html` beside the real page, opened by URL, under the same never-implement rule.

### The design-time dock

On a generated (greenfield) artifact page the design-time chrome collapses into one **dock**: a floating trigger at the page corner, collapsed by default, opening a panel with exactly four tabs — **Design Preview**, **Function Spec**, **Decision Log**, **Version Ladder**. The Function Spec tab loads the generated spec page; the Decision Log tab loads the generated decision-log fragment (the alignment table: Seq, Question, Decision, status) and the Version Ladder tab loads the generated version-ladder fragment (five fixed fields per round: version tag, change title, driving decision, what changed, snapshot link) — both fragments are written by the generator alongside the spec page from the rounds' alignment and ladder data, never hand-built. The preview area stays pure production: opening the dock, switching tabs and closing it never alter the preview area's DOM or computed styles, and the dock and its tabs are never implemented into production. The **version ladder** runs the artifact's whole life as versions: every confirmed round bumps a monotone version tag and adds one ladder entry carrying the version tag, the change title, the driving decision or user annotation (quoted), and what changed — written in the same change that realizes the round, so the ladder and the page never drift. Each round also keeps the realized artifact state as that round's snapshot (oldest to newest), and the append-only growth check diffs two neighbouring snapshots. The newest version tag rides the dock trigger, never the preview area — the preview area stays pure production, and the ladder with its version banner lives inside the dock only. Every ladder version is archived in version control the moment the round closes: the snapshot, the spec, and the version's verify script — the scripted deployment regression for that version, named after the version — are committed and pushed with the version tag as the commit tag, so implementation can branch from any tagged version and proceed in parallel with later alignment rounds — alignment never blocks development, and development never blocks alignment. The refinement entry keeps the existing rule: the real page carries no design chrome, and the design-time pages stay beside it.

### Console flow (uiux branch)

Router:

| Scenario | Route | Action |
|---|---|---|
| Options exist as rendered artifacts | This console (`serve_decision.py`) | Ask directly, one round per related group of elements |
| Open question, no rendered options yet, or an S1 wireframe round | `/prototype` — **UI branch** | Build switchable variants first (S1: skeleton wireframes, switching outside the page); the variants become this console's evidence |
| Logic / state-model question | `/prototype` — **logic branch** | Single shareable HTML file; never starts this server |

Global-to-detail cadence (hard rule):
1. Layout and framework come first: align the overall frame (regions, hierarchy, layout) before any element detail.
2. Then build progressively: add a related group of elements (or one interaction) per round, on top of the confirmed frame. Judge each group from the human-machine collaboration angle: is it in the right place, does it behave correctly, does it help the user close the loop from discovering a problem to resolving it. Group elements that depend on each other; keep unrelated elements in separate rounds.
3. Each round pairs the proposal with a **neutral challenge** (the design tree's round mechanics own the rule; doc-tree's variant applies to its rounds).
4. The design grows cumulatively from the confirmed frame. Never fill in element details before the frame is confirmed.

Launch, notify, complete (one background task):
- Start the console as the single background task. Never pass `--no-open` outside maintainer checks.
- Read the serving URL from the `[OK] serving` stdout line. When the open fails (the `[WARN]` line), the orchestrator opens the URL and brings it to the foreground itself.
- Once the page is open and in the foreground, notify the user through the question tool that a round waits in the console, and wait (delivery contract: references/question-form.md). When the user answers the notify question, take the round's answers from the server task's output tail (the `[OK] answers ready` line and the JSON after it) — never re-ask, never start a watcher.
- Do not start the watcher and do not parse the session token: on submit the server prints `[OK] answers ready` with the answers and exits 0, and the task-exit notification is the round's completion.
- No submission timeout: the server task waits until the user submits, however long that takes. Pass a bounded timeout only when the user explicitly asks for one.

Card rules (each owned where it lives; this file adds no restatement):

- The answering channel, the never-plain-text rule, the option count, the write-in and one novice-friendly context line per card live in references/question-form.md (Delivery, Options, Explanation protocol).
- Per-option evidence, the boxes overlay and the load-time gate live in the Evidence section below; their machine contract lives in `scripts/manifest.json`.
- Card template structure, icons, console behaviour, input fields, keys and the answers file format are owned by `scripts/manifest.json` and `scripts/serve_decision.py`. Change them there, never here.

### State display contracts (S4)

Every scenario from the combed inventory also walks the interface's state machine: ideal, loading, empty, partial, error. Each non-ideal state is a design surface with its own confirmed contract, never an afterthought. Classify every state along the display layers, then decide per cell:

- **Story layer (the grid)**: one row per scenario (view, create, edit, remove, wait or sync), one column per state. Every non-ideal cell gets a contract.
- **Cause layer**: input (invalid or missing), data (absent, duplicate, conflicting, stale, dependent), connection (offline, timeout), permission or service (unauthorised, quota, down), environment (storage full, unsupported host).
- **Severity layer**: blocking (must resolve before continuing) versus continue-able (a dismissible warning). Severity chooses the presentation weight.
- **Presentation layer**: inline message at the source (validation), transient toast (continue-able), banner (page-level condition), state block replacing the region's content (what happened + why + what to do next + one primary action), modal (severe, must resolve), full page (total failure).
- **Recovery layer**: retry, undo, fix and resubmit, one-click suggested fix, contact, wait and notify. Every state's contract names its recovery path.

Empty is not an error: empty means the load succeeded with nothing to show (first use, cleared, filtered to nothing) and its job is to teach the next step; error means the load failed and its job is recovery. A filter returning nothing is its own state with its own way out.

Message contract for every state's copy: plain language, no codes, no blame; state what happened, why, and what to do next; place the message at the error's source; pair icon, text and colour (never colour alone); validate inline only where a mistake is likely, never on a mere visit. Preserve the user's input through any recovery path; offer the fix when the system can guess it.

Concurrent conditions follow one hierarchy, most severe first: the interface shows the highest-severity condition and never stacks per-element errors into a wall.

### Agent participation contracts (S4)

The combed inventory also covers the agent layer: every scenario where the agent — not the user — initiates or participates. Five participation modes, one scenario each: it **surfaces problems** the user would miss, **assists the fix** with proposals, **deepens the analysis** with reasoning, **reminds proactively**, and **self-learns** from the user's corrections and behaviour. Every agent scenario carries the same interaction contract as any other scenario (trigger → feedback → state change → recovery) plus the agent parity items:

1. **Intent preview**: before a consequential action the agent shows a plain-language plan and a way to proceed, edit it, or do it oneself; irreversible actions always wait for explicit confirmation.
2. **Autonomy level**: per task the user can dial how far the agent may go (observe, propose, act with confirmation, act on its own); the level matches the action's risk.
3. **Confidence**: the agent shows how sure it is and how far its claim reaches; low confidence asks for scrutiny instead of guessing.
4. **Dismissal and correction**: rejecting or rewriting the agent's output is one step away, and the agent learns from the correction.
5. **Audit and undo**: agent-initiated actions land in a visible log with an undo path, and the undo window is stated.
6. **Escalation**: on ambiguity or high stakes the agent asks instead of guessing.

Self-learning stays visible and revocable: what the agent learned is shown, adaptation is gradual, and the user can inspect and reset it.

### Stage gates

Tick every item at the point it guards. The items verify the rules of this file; they add none.

- [ ] Stage advance: the previous stage's confirmed output is realized in the artifact, and this stage's captures follow it — never a redrawn frame.
- [ ] Refinement entry: the baseline is named and the scope round closed before any option was authored; untouched surfaces stay confirmed.
- [ ] Self-check before ask passed: page loads, no page errors, the round's interactions verified by script before the user sees anything.
- [ ] S1: the region wireframe is skeleton-only at true viewport size; every region's semantic assumptions named and confirmed or answered in a logic sub-round.
- [ ] S2: content entries only; no interaction drawn.
- [ ] S3: every visual value from the design tokens; no raw values.
- [ ] S4: the combed inventory (scenario, state machine, agent layer) exists before any option is authored.
- [ ] S5: the four visual principles swept over the composed page.
- [ ] Production mirror: real business data only, no non-production elements, captures boxed, live view one click away; every control is wired to real behaviour (never a drawn mockup).
- [ ] Captures show our artifact, never the user's supplied original; the original is captured only for questions about it.
- [ ] Copy assumes a user who has never heard of an agent; designed from the professional viewpoint for the user's understanding, mental and operational costs; minimal is cognitive (features and icons kept), hierarchy clear, configuration user-viewpoint with zero technical terms.
- [ ] Console: single background task, no --no-open at runtime, notify-and-wait through the question tool, answers read from the task tail, no watcher.
- [ ] Every UI/UX criterion names the deployed environment, the automation tool class, and the pass condition; no verify method names only a local machine.
- [ ] Round close (every S2-S5 round): the confirmed element is appended into the artifact, the whole page re-captured, the version ladder entry and snapshot written, the function spec synced, and the version committed and pushed with its tag — before the next round launches.

## Evidence

Production mirror (hard rules):
1. The artifact mirrors production 1:1 — structure, visuals, copy, and interaction behaviour (every click, keyboard, and state-change path). Production replicates the artifact back the same 1:1: the artifact is the spec, not a sketch.
2. Real business data only, in the artifact and in every evidence capture. Mockup data, altered numbers, and "illustrative" placeholders are forbidden. Greenfield (no real data exists yet) is a declared degradation with a named backfill item — never silent sample data.
3. No non-production elements inside the artifact: no switcher bars, debug overlays, build captions, annotation legends, or implementation metadata. Variant switching stays outside the rendered page (a URL parameter or separate routes). Evidence markers (spec boxes drawn by the console page over the capture) live only on console captures, never in the artifact. The question explains; the artifact is the product.
4. Visual values (colour, font size, spacing, radius) come only from the host's design tokens; a raw value is a failure. The element sits inside the real host surface. An artifact that fails any rule here is not shown as a decision option.
5. Refinement evidence is the real page: when the refinement entry opens on an implemented project, every interactive page and capture opens the real implemented page with the proposed change applied on top (a branch build or a served copy of the real file) — never a rebuilt mockup.
6. Lifecycle: a pre-S1 exploration variant may be throwaway, but any variant shown as an option already follows rules 1-4. The winning variant is folded into the artifact, and these rules govern it from then on; the throwaway stance applies only to losing variants and to logic demos.

Evidence first:
- Stage evidence: an S1 wireframe round carries the variants themselves — switchable skeletons built the `/prototype` way (switching stays outside the page), entering the console as a capture plus an Open-in-tab link (no embedded iframe — one capture per option, the live view one click away). A wireframe self-annotates: its boxes ARE the regions, so capture boxes are not required at this stage. From S2 on, every capture of the real artifact is boxed (the page draws the circles); the live view stays one Open-in-tab click away. An S4 interaction round rides whole-page variant copies: every option links the artifact page copied 1:1 with that option's interaction applied, and its captures are the flow's key states — one boxed capture per state (trigger, feedback, end or recovery).
- Whole-page variant copies (S3/S4 options): every element and interaction option's live url shows the whole current artifact copied 1:1 with the candidate applied — never an isolated fragment page — so the user judges the candidate inside the full confirmed context and the round completes in one console launch. After a variant wins, appending it into the artifact is mechanical and needs no re-confirmation round: the user just saw the exact markup in place.
- Neutral, user-perspective judgement: weigh each design neutrally from the user's point of view, then give the suggestion. Never design from implementation.
- Every option carries a real rendered comparison from the real environment: change one thing, capture that one thing; label each capture with its option; before/after share the same viewport and width. Compare options side by side.
- Capture ownership: captures show **our artifact, never the user's supplied original**. Once the design phase starts, every capture renders this skill's own design at its current confirmed state; a capture of the user's original prototype is a violation. The original is captured and boxed only when the question is about that original itself (asking about something on it), and such a capture is labelled as the baseline, not as our design.
- The reference the user confirmed is the acceptance baseline; changing the reference itself starts a new decision round.
- Freshness: evidence reflects the current code and data; a change voids old captures — re-capture and re-ask, never pass off stale shots.
- The evidence gate is enforced at load time (rendered mode requires both the boxed capture and the live url per option - either half missing is a load error; a degraded card must declare itself and shows the badge). The gate's contract lives in scripts/manifest.json.

Degraded path:
1. When the environment cannot render, use structural comparison: DOM structure, style inventory, component tree — explicitly labelled, which the console badge does.
2. Missing captures or openable pages become named backfill acceptance items: state what gets backfilled and when it counts as done.

Capture routing: platform-design reference, feature replication research, and DOM/token/screenshot evidence come from the environment's structured browser-inspection tools, with ids and provenance on every capture — never ad-hoc scraping scripts. Scripted browser automation stays for what inspection does not cover: driving interactions (clicks, keyboard, submit round-trips) and scripted regression (pixel diffs, --live checks, RED/GREEN assertions).

## Round closing

### Criteria pool (auto-paired on every UI confirmation)

Once a UI or UX decision is confirmed, pair its criteria on the spot; they enter the criteria checklist and are confirmed like any other criteria (pairing contract: references/design-tree.md):

1. The rendered result matches the reference at every supported width.
2. The rendered result matches the reference in every supported language (copy, layout, truncation behaviour).
3. Host design tokens are respected: colours, font sizes, and spacing take token values, never raw values.
4. Accessibility checks pass: labels complete, contrast compliant, focus order correct.
5. Forbidden content is absent: internal ids, secrets, and debug info appear in no rendered result.
6. Automate the scan wherever automation can cover it; manual review covers only what automation cannot, with the review method written down.
7. Every confirmation applies the four visual principles at its own scope — the Design principles module owns the wording.
8. **Deployment mirror check.** Once the confirmed artifact is deployed to the real environment, a scripted browser regression compares the deployed page against the acceptance baseline — the prototype HTML plus its function spec — 1:1: layout geometry, visual values, copy, and every confirmed interaction path, across the supported widths; the comparison is scripted, re-runnable, and any drift fails the check. What automation cannot cover gets a written manual review method (the same split as item 6).
9. **Deployment-verified criteria.** Every UI/UX criterion's verify method names three things: the deployed environment it runs against, the automation tool class (a browser-automation or computer-control tool), and the pass condition. A verify method that names only a local machine never passes; where no deployed environment exists yet, the criterion is a named backfill item (the degraded path rule) — never silently waived.
10. **Icon audit.** Every button and every title carries an icon from the interface's single declared icon set, and the emoji-icon count is zero — audited by script on the deployed page (the validator script owns the machine contract).
11. **Whitespace over dividers.** The artifact page contains zero hr and zero divider-only elements outside a repeated entry list — one row per item, the case the divider provably serves — and outside a criterion-declared functional grouping (the exempted ids are named to the audit) — audited by script; the S5 sweep covers the divider drawings a script cannot parse.
12. **Title Case copy.** Every heading and every button renders in Title Case (English copy; other scripts are out of scope) — audited by script on the deployed page.
13. **Append-only growth.** After each element round, the artifact HTML diff against the previous version-ladder snapshot contains additions only — confirmed regions carry zero changed markup — verified by a scripted diff of two neighbouring snapshots.
14. **Motion audit.** Every interactive operation declares a micro-to-medium transition: the page's stylesheet declares transitions for its interactive elements, every duration stays inside 80-450 ms, easing follows the host system's native motion first (a system-standard ease-out or spring feel), and a `prefers-reduced-motion` rule disables them — audited by script on the deployed page; per-element coverage and easing quality are judged in the S5 sweep.
15. **Token consistency.** Identical element kinds carry identical tokens: one element class declares exactly one background value, and interactive elements take their colours from design tokens (never raw values) — audited by script on the page stylesheet; the host token list owns the allowed values.
16. **Real behaviour audit.** A scripted click-through on the deployed page drives every button and interaction and observes the real state change it promises (a badge increments, a record is written, a panel opens); a control with no observable real behaviour fails.
17. **Real state.** Every displayed value (counts, badges, statuses, timestamps) reads from the real data source at render time; stale, hardcoded, or illustrative values are mockup data and follow hard rule 2. When two surfaces show the same fact, sibling surfaces agree — a mismatch between them is a failure, not a cosmetic bug.
18. **Version parity.** The deployed build's version tag equals the prototype ladder's tagged version — build version and prototype version are the same number; verified by the version's verify script on the deployed page (the scripted regression committed with the tag) and by the version-control tag list, and a mismatch fails the deployment mirror check. Parallel implementation branches from a tagged version; later alignment rounds keep bumping the ladder without blocking the branch.

Pooled by interface kind:
- **Generated interfaces (closed component set).** When the interface is generated from data or model output, its component and card types come from a fixed, closed set. The generator may only pick a type from that set; the validator checks fields against a structured model; the renderer draws only components inside the set. A hand-built interface does not need these rules.
- **Vanished items (no silent removal).** When an item already shown is absent from the latest data, the interface keeps it visible and marked as vanished, with the time and the reason. Only the user's confirmation may close or remove it.
- **High-risk actions (button confirmation).** Any action with an external effect or an irreversible result passes one button confirmation: before confirmation the interface shows the object, the before/after comparison, and the evidence; the action never runs automatically.
