# Logic tree (Logic rounds)

The design tree settles _decisions_ (choose A or B). A second tree settles **procedural logic** — anything that runs as steps: pipelines, scripts, calculations, derivations, branching behavior, state changes, update flows, batch jobs, workflows, migration routines. The test: if it contains an if/then, a loop, an ordered sequence of steps, or a state change, it is procedural logic and goes on the logic tree — when in doubt, tree it. Prose is banned for procedural logic; render it as an explicit tree.

## Round preamble

Logic rounds walk the design tree's process (references/design-tree.md) — frontier discipline, round mechanics, paired criteria — as an overlay on the design tree, never instead of it. The message body carries three pieces: the logic tree itself (one ```text fence, the icon contract below), a markdown decision table, and a real xlsx attachment produced by scripts/gen_xlsx.py — never a hand-built file (evidence standard: references/question-form.md).

## Round rules

### Logic scan — draft the tree yourself

Building the logic tree is your job. The user describes in prose; you extract. Walking the branches of an existing tree is not the skill working — the tree must first exist, and drafting it is always yours, in every round, from the user's own words.

**When**: before round 1, and again after every user reply. Scan ALL input — the opening message, every answer, every side remark ("oh, and if X fails, just skip it"), every attached document.

**What counts as a procedural fragment** (draft a node for each):

- a conditional rule (if / then / unless / only when / otherwise)
- an iteration (each / every / loop / retry / until)
- an ordered sequence (first / then / after that / before)
- a state change (create / submit / queue / move / delete / publish)
- a calculation or derivation (any value computed from other values)
- a hand-off between actors or systems (A does X, then B does Y)

**How**: for every fragment, draft the node card(s) — id, trigger as a precise predicate, action, output, cost, one real firing example — and present them as node confirmations (confirm / change / kill) in the same round. Never ask "should we build a logic tree?" or "what are the steps?": hand over draft nodes. A casual fragment gets the same card as a headline feature. A fragment you cannot yet state as trigger/action/output is drafted as a split candidate with the unknown named — not skipped, not smoothed into prose.

**Draft skeleton exception**: alongside the logic-tree audit line you may show a draft skeleton of the tree, every node marked pending and attached to the question that will settle it. It is never submitted for approval, and every node still gets its individual card confirmation — the skeleton previews, it does not pre-confirm.

**Visible**: every round opens with the logic-tree audit line (round format in references/design-tree.md, Round mechanics). A round with no procedural logic in the input writes that explicitly — the audit line is the audit trail that nothing was missed.

**Full-artifact rule**: any SQL, code, config, command, or prompt cited in a node, a criterion, or a test is quoted in full — no `...` elision, no half statements. Too long for the card → verbatim into the doc anchor, and the card links it.

**Executable-SQL rule** (when a node or criterion contains SQL): every SQL statement in a node, criterion, or test is executable as written against the real schema —

- FROM / JOIN / INTO name **physical tables**: the real table names as they exist in the database — never a logical name, an alias standing in for a table, or a CTE shorthand.
- Columns are **physical column names** of those tables, as landed/declared in the target store; business labels appear only as explicit `AS` output renames, never in place of the physical name.
- A table or column that does not exist yet is a **named unknown**: written as an explicit placeholder tied to the node that will create or confirm it, and asked about when it blocks — an invented plausible-sounding name is a violation.
- The full statement comes first; per-clause commentary follows if needed. Fragments ("and the rest of the columns") and pseudo-SQL are violations.

### Node rules

- Every node has a unique id (L1, L1.1, L1.1.1...) and renders in the **icon field contract** (drawing grammar, below). Trigger / action (logic step) / output (📤) are the core trio: if a node cannot state all three, it is not understood yet — split it until it can.
- The tree states its **entry** (what event or input range kicks it off) and its **exit** (what is produced once the whole tree has run, including the total written).
- A node must be falsifiable: given an input, the tree says exactly which branch fires and what comes out.
- **No guessed attributions.** Every leaf must be a deterministic rule grounded in a mechanism fact (a real table, a real check) — never a "probably / likely / some kind of" cause. Where data contradicts the extraction, don't soften it into a plausible story: add an explicit exception node that flags for human investigation.
- **State the cost and the order.** Cost lives in ⏱️ Estimated time (<IO cost> in parentheses); where order matters (first hit wins), the `↓ miss` connector writes the evaluation order explicitly.
- **Branches vs sequences are drawn differently — and arrows live on the structure, not in the text.** Mutually exclusive cases are tree branches (├─ └─). Plain sequences connect with `↓`. Ordered decision chains connect with `↓ miss` — first-hit-wins only; never label a plain sequence or a failure as miss (failures live in the 🚨 Fail field, pointing at their 🚪 exit). Never glue hit/miss arrows into the sentence text — the sequence must read off the connector lines alone.

### Three confirmation stages

Align node by node, then review the assembled tree — three stages:

1. **Node walk.** Every rule in the tree is confirmed with the user individually — one node per confirmation: present the node's icon-contract block (all twelve fields with real values) plus its real-data example, and get an explicit confirm / change / kill. Only confirmed nodes may be drawn into the tree; never show a partially unconfirmed tree and ask "is this right?". Confirming a node confirms its block's `acceptance` items — all enter the criteria checklist together, each numbered item as its own C<n>. A blanket reply never substitutes for a presented node: any node whose block the user has not seen is presented and confirmed first, even when the user instructs you to skip ahead — the skip request goes on the answer-back checklist with a named delivery point. Container nodes (loop heads, chain containers) may be confirmed together with their first child, but the block must state the container's trigger and iteration predicate explicitly.
2. **Layered assembly.** Build the tree layer by layer out of confirmed nodes: layer N+1 is drawn only from nodes whose upstream is confirmed. When the user changes a node, "downstream" is positional: in an ordered chain (first hit wins), every later check is downstream of an earlier one, because its effective input is "the earlier checks missed". Mark all downstream nodes as awaiting re-confirmation and re-walk them in order.
3. **Final review.** When the last node is confirmed, assemble the final tree and present the complete tree for one review — order, branches-vs-sequences drawing, cross-node consistency, entry/exit closure — and get the user's explicit approval before freeze. This final review is the **only** permitted whole-tree presentation: it is legal precisely because every node in it is already individually confirmed, and it never licenses showing unconfirmed nodes in tree form. Any change raised at final review re-opens the affected nodes and everything positionally downstream; after the re-walk, the assembled tree goes through the final review **again** before freeze. Freezing stamps **traceability anchors**: every node's doc anchor (the node card / ADR / column comment that records it) is filled at freeze; its code anchor is recorded as a planned location (planned file / module / function, or TBD + plan while implementation hasn't started) and backfilled as soon as the implementing code lands, at which point the anchor sweep is re-verified. The implementing code carries a comment citing the node id (e.g. `// L2.2.1 — see logic tree`), and the doc records the node id — so tree, code, and docs trace to each other in both directions. If implementation later moves a node's location, update the anchor on the tree in the same change.

### Logic tree icon contract (icon field contract — drawing grammar)

To keep the tree's shape stable across runs, every logic tree follows this drawing grammar: one ```text fence — monospace is what makes the alignment work; never re-render it as free markdown (proportional fonts destroy it). The tree is a zero-translation preview of the artifacts it freezes into (node cards, constants, or equivalent artifacts where one exists). A tree's language follows the session language.

**Layout rules**:

1. Task line: `├─ 📌 <Level> <Task name>` with the name column fixed width and the status column starting at a fixed offset (generous gap) — statuses align vertically across branches.
2. Body lines: guide column + 4 spaces prefix; field icons all start at the same column; the last node's guide column is a space placeholder.
3. Connectors: see the branches-vs-sequences rule above (├─/└─ mutually exclusive branches, `↓` plain sequence, `↓ miss` first-hit chains only).
4. Multi-condition logic marks AND / OR explicitly; mixed conditions group with parentheses; 🧪 verify items default to AND (every item must pass).

**Field contract per node — fixed order, one icon per field**:

| Icon | Field | Content |
|---|---|---|
| 📌 | Task line | Level id + task name + status |
| 🎯 | Trigger | Trigger condition (AND/OR combinations explicit; precise predicate, vague qualifiers banned) |
| 🗄️ | Data source | Exact tables this node operates on, one per line, each `schema.table_name` with its role (`-- read` / `-- read/write`); non-data nodes write `none (reason)` |
| 🧮 | Logic | Steps 1, 2, 3; full SQL hangs under its step, indented inside the branch |
| 🔎 | Filter | Filter 1/2/3… one per line + AND/OR between filters (isomorphic to the node card's Filter field where one exists); if none, write "none (reason)" |
| 🔑 | Join key | 1, 2, 3…; every key must cite its source: key column written as `[col]`, source written as `-- table: <fully qualified physical table name>`; in-memory key `-- source: L<n> output (shape)`; if none, write "none (reason)" |
| 📤 | Output | Data shape (exact rows / counts where applicable) |
| 🧪 | Acceptance criteria | Numbered items 1, 2, 3…, **one item per line**; each item is a deterministic criterion + verification method (command/query/reconciliation); each item enters the Criteria checklist as its own C<n> once confirmed; cross-node criteria go into the checklist only |
| 🧾 | Evidence | The concrete artifact the AI must issue to prove this node's work complete — command output, screenshot, file path, diff, query result set |
| 🚨 | Fail | Failure handling: retry / degrade / raise → points at 🚪 Exit |
| ⏱️ | Estimated time | `<duration> (<IO cost>)` — duration is the primary information, IO in parentheses; placed after Fail as the node's closer |
| 🚪 | Exit | [exit A/B/C] explicit closure; separate exit for contradictions |

**Status labels**: ✅ user-confirmed / ⏳ pending / 🚧 blocked (reason) / 🔁 awaiting re-confirmation (downstream nodes after an upstream change) / ❌ rejected.

Skeleton (placeholders are legal ONLY inside this skeleton and draft skeletons; every name, field, and value in confirmations and explanations comes from the task's real data):

```text
[entry]<what event / input range kicks the tree off>
│
├─ 📌 L1 <Task name>          ⏳ pending
│    🎯 Trigger: <precise predicate — data, no vague qualifiers>
│    🗄️ Data source:
│       1. <schema.table_name> -- read
│    🧮 Logic:
│       1. <step>
│       2. <step>
│       3. SQL as follows:
│          <full executable SQL — physical table + column names, plain syntax>
│    🔎 Filter:
│       Filter 1: <[column] predicate>
│       Filter 2: <[column] predicate>
│       Between: AND
│    🔑 Join key:
│       1. <purpose> key: ([col], [col]) -- table: <physical_schema.table>
│       2. <purpose> key: [col] -- source: L1 output (shape)   ← in-memory key, cites the upstream Level
│    📤 Output: <data shape — exact rows / counts>
│    🧪 Acceptance criteria:
│       1. <deterministic criterion — verify: <method>>
│       2. <deterministic criterion — verify: <method>>
│    🧾 Evidence: <artifact the AI issues to prove completion>
│    🚨 Fail: <failure handling: retry / degrade / raise → 🚪 exit>
│    ⏱️ Estimated time: ~<duration> (<IO cost>)
│   ↓
│
└─ 📌 L2 <Task name>          ⏳ pending
     🎯 Trigger: L1 completed
     🗄️ Data source: <schema.table_name> -- read/write
     🧮 Logic:
        1. <step>
     🔎 Filter: <…>
     🔑 Join key:
        1. <purpose> key: [col] -- table: <physical_schema.table>
     📤 Output: <data shape>
     🧪 Acceptance criteria:
        1. <criterion — verify: <method>>
        2. <criterion — verify: <method>>
     🧾 Evidence: <artifact the AI issues to prove completion>
     🚨 Fail: reconciliation mismatch = a contradiction that should not happen → human investigation → 🚪[exit C: separate exit for contradictions]
     ⏱️ Estimated time: ~<duration> (<IO cost>)
     ……🚪[exit B: <tree-exit closure — total produced, how it is counted>]
```

### Node confirmation (one question per node; a layer may share one round)

The ask wraps the node's icon-contract block (status ⏳ pending — the deliverable; no decision-table template, no per-node .xlsx) in the round template (references/question-form.md): ❓ names the node, 💡 carries the block with its real firing example, 📊 lists confirm / change / kill probability-sorted, ➡️ recommends one; Pros/Cons state what confirming locks in (downstream nodes unlock, acceptance items enter the criteria checklist) against what change/kill re-opens (downstream re-confirmation, criteria withdrawn). Nodes in the same layer, whose upstream is already confirmed, may be asked in one round as numbered items; each item is still confirmed or changed on its own. The ask uses the round framing (numbered item in the round, the answer-back checklist, the agreed-list restatement) and the Explanation protocol's plain-language and real-data rules (references/question-form.md). The block carries all twelve fields with real values (a not-yet-existing table or column stays a named unknown tied to the Level that will create it), plus:

- real firing example: <one real row or row-set from the task's data that makes this node fire, with real values>
- acceptance (numbered items, one per line):
  1. <deterministic criterion — given <input>, the node fires and produces exactly <output>; verify: <test/check>>
  2. <next criterion — verify: <method>>
- evidence: <the concrete artifact the AI will issue when this node's work is done — command output, screenshot, file path, diff, query result set>
- code anchor: <planned file / module / function — TBD until the design settles; backfilled when the implementing code lands>
- doc anchor: <node card / ADR / column comment / doc section where this node will be recorded>

- The question block follows the round template in references/question-form.md (probability-sorted options).
- Novice mode: every table column and every domain term gets a one-line plain-language note backed by a real example, so a non-expert can decide without outside knowledge.

### Round gates

Tick every item before the round launches and again before it closes. The items verify the rules of this file; they add none.

- [ ] Logic scan ran on all input (every message, side remark, attachment); a round with none writes the zero explicitly.
- [ ] Every procedural fragment drafted as a node card; no "should we build a tree?" ask.
- [ ] Every node states trigger / action / output; no vague qualifiers, no guessed attributions.
- [ ] SQL and cited artifacts quoted in full, executable, physical names.
- [ ] One node = one confirmation; no partially unconfirmed tree shown (the draft skeleton excepted).
- [ ] Every node downstream of a change marked 🔁 and re-walked in order.
- [ ] Freeze only after final review; traceability anchors stamped; the .xlsx comes from scripts/gen_xlsx.py only.

## Evidence

- Every node that fires on data carries a real-data example of itself firing (same no-fabrication standard as references/question-form.md).
- The round's .xlsx comes from scripts/gen_xlsx.py per the manifest contract; a hand-built file is banned.
- Everything else follows the shared evidence standard in references/question-form.md.

## Round closing

The logic tree closes under the design tree's closing contract — paired acceptance criteria, the five-category coverage sweep, and session closing (references/design-tree.md). A frozen tree carries its traceability anchors (Three confirmation stages, stage 3); if implementation later moves a node's location, update the anchor on the tree in the same change.
