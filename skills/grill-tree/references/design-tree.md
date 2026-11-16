# Design tree (Role and trade-off rounds)

The design tree maps every decision and the branches hanging off it. Role and trade-off questions walk this tree; procedural logic goes to the logic tree (references/logic-tree.md); UI and UX rounds follow this tree's decision process under the evidence rules of references/uiux-tree.md.

## Round preamble

Before the first question of a round, the design tree opens with an alignment block: a bold heading `**<topic> Design Tree**`, then one table with one row per question already asked in this round. Columns are Seq, Question, Decision. Seq is Q1, Q2, ...; a decided row shows ✅ and the chosen option text; an open row shows ⏳ Pending.

```
**<topic> Design Tree**

| 🔢 Seq | ❓ Question | 📌 Decision |
|---|---|---|
| Q1 | <question title> | ✅ <chosen option text> |
| Q2 | <question title> | ⏳ Pending |
```

The open question's block follows the shared question form and evidence standard in references/question-form.md.

## Round rules

### Style

**Bullet-first**: everything enumerable is a numbered list (1. 2. 3.) or bullets — explanations, criteria, bases, risks, options, multi-item cells. One item per line; a paragraph carrying more than one piece of information is a violation. Multi-item table cells break items with `<br>` + bullet markers. Tables, lists, and the two trees are the default carriers; prose walls never are. (This relaxes the no-decoration instinct: the decision table and the logic tree are functional structure, not decoration.)

### Term contract

**Naming extension (when a session names physical columns or tables; otherwise skip)**

1. **Columns are always wrapped in square brackets**: `[column_name]` — in logic-tree fields, decision tables, bullets, criteria, and Fail lines. The bracket marks "this is a landed column name"; every mention maps 1:1 to the real column the user will write against. Never translated, never reworded.
2. **SQL exemption**: inside an actual SQL statement (```sql fence or the SQL lines under a 🧮 step), columns follow SQL syntax — plain names, no brackets. Brackets are communication markup, not SQL.
3. **Table names**: physically fully qualified in `schema.table_name` format; backticks in markdown prose and tables, plain inside fences. Never translated or shortened.
4. First mention may pair a session-language gloss with the physical name: "<gloss>" `[column_name]` — after that, physical form only.
5. Business terms follow the session's glossary where one exists; physical names have exactly one written form.

### Drawing grammar (decisions and non-procedural tasks)

The design tree renders as a lightweight ASCII tree (one ```text fence, indentation + connectors) — the logic tree's fixed-width name column and guide-column alignment rules do NOT apply here.

**Fields per node — fixed order**:

| Icon | Field | Content |
|---|---|---|
| 📌 | Task line | `D<id>` + decision name + status |
| 🎯 | Trigger | The decision question — a precise predicate: what must be decided and when it is on the frontier |
| 🧮 | Logic | The numbered options with the landed choice marked `← agreed`; when a decision touches data, full SQL hangs under its step (same full-artifact and executable-SQL rules as the logic tree) |
| 📤 | Output | What the decision settles — the consequence |
| 🧪 | Acceptance criteria | Numbered items 1, 2, 3…, one item per line; `C<n> (<tag>): criterion — verify: <method>` (canonical criteria format); every node carries at least one — cross-node criteria go into the checklist only |
| 🧾 | Evidence | The concrete artifact the AI must issue to prove this item complete — command output, screenshot, file path, diff, query result set |
| 🚨 | Fail | What happens when the decision is changed or rejected → downstream re-opens |
| ⏱️ | Estimated time | Cost to implement the decision |

No 🔎 Filter and no 🔑 Join key in the design tree; no per-node 🚪 Exit — the tree closes with one bottom exit line. Data-source detail lives in the logic tree only: when a decision's logic touches data, the logic-tree node it spawned carries the 🗄️ Data source field.

**Status labels** (same set as the logic tree): ✅ agreed / ⏳ open / 🚧 blocked (reason) / 🔁 awaiting re-confirmation / ❌ rejected. The audit line's counts agree with the icons.

Skeleton (placeholders legal only in draft previews; confirmed nodes carry real values):

```text
[Design]<the goal the tree delivers>
│
├─ 📌 D1 <decision name> ⏳ open
│    🎯 Trigger: <the decision question>
│    🧮 Logic:
│       1. <option> ← agreed
│       2. <option>
│    📤 Output: <what this settles>
│    🧪 Acceptance criteria:
│       1. C<n> (<tag>): <criterion> — verify: <method>
│    🧾 Evidence: <artifact the AI issues to prove completion>
│    🚨 Fail: <changed / rejected → downstream re-opens>
│    ⏱️ Estimated time: ~<duration>
│   ↓
└─ 📌 D2 <decision name> ⏳ open
     …
│
……🚪[exit: <tree-exit closure — what done means for the whole tree>]
```

### Round mechanics

Every round opens with four header lines, then the question blocks:

```text
Design tree: <n> agreed / <m> open / <b> blocked (+<k> added) — Logic tree: <n> confirmed / <m> pending / <b> blocked (+<k> added) — counts must agree with both trees' status icons. No procedural logic in this round's input = write the logic-tree zero explicitly (e.g. `Logic tree: 0 confirmed / 0 pending / 0 blocked (+0 added)`); a round with no open design branch yet writes the design-tree zero the same way. An omitted audit line is a violation.
📋 **Answer-back checklist**: <one line per open item — question → answered, or sub-agent + named delivery point>. (Round 1: "empty — nothing raised yet.")
📋 **Agreed list**: <one line per agreed decision — short id + the decision in one sentence>. (Round 1: "none yet.")
📋 **Criteria checklist**: <one line per paired criterion — C<n> (<tag>): criterion — verify: method — status>. (Round 1: "empty — no decisions confirmed yet.")
```

A round may contain several questions: each question repeats the full block (❓ through ➡️ **Recommended Answer** with Pros/Cons); the four header lines appear once at the top of the round. The final-tree review (logic-tree stage 3) is presented as its own block after the 📋 lines — not inside a ❓ Explanation.

When a direct instruction and your recommended option conflict, never silently pick one: put the conflict on the frontier — the instruction's consequence (shown with evidence) and the recommendation — and let the user resolve it.

**Neutral challenge.** Every round pairs the proposal with a neutral challenge: the agent argues against its own design (misuse, edge cases, cheaper alternatives, what the change breaks) and surfaces the findings before the user decides.

**Answer-back checklist.** Every question or challenge the user raises gets an explicit reply before the next round's questions go out — either a direct answer, or a stated commitment to dispatch a sub-agent and deliver the result at a named point. Keep a checklist of the user's open questions and review it at the start of every round; a user question is never silently dropped, deferred without a named delivery point, or answered only in passing.

**Confirmation closure.** Track every decision's status: proposed, agreed, or awaiting re-confirmation. Restate the agreed list briefly at the end of each round. If the user opens a new topic while a confirmation is still pending, close that confirmation first in the next round before exploring the new topic. Once the final acceptance-criteria round has begun, it runs to completion — no other topic opens until the user explicitly confirms or rejects, and any frontier questions the user's answers open wait for the round after the confirm/reject. (A tree change raised during the acceptance round goes on the answer-back checklist and opens a re-confirmation round after acceptance closes.)

### Round gates

Tick every item before the round launches and again before it closes. The items verify the rules of this file; they add none.

Launch:

- [ ] Audit line present; counts agree with both trees' status icons; zeros written explicitly.
- [ ] Answer-back checklist reviewed; no user question silently dropped or deferred without a named delivery point.
- [ ] Agreed list restated; a pending confirmation closes before any new topic opens.
- [ ] Every option block carries the full question-form structure (❓ 💡 📊 ➡️ with Pros/Cons).

Close:

- [ ] Every confirmed decision and node has its criterion drafted at confirmation time, never reconstructed later.
- [ ] Five-category coverage sweep closed; every N/A carries a written reason.
- [ ] Every confirmed item maps 1:1 to a deterministic criterion with its verify method.
- [ ] External gates and consistency sweeps stated in the same deterministic form.
- [ ] The proposal carried its neutral challenge before the user decided.

## Evidence

The Explanation protocol, its degraded path, and the measured-impact and .xlsx standard live in references/question-form.md. The design tree adds no evidence rules of its own beyond that standard.

## Round closing

### Paired acceptance criteria — the criterion lands with the decision

Acceptance criteria are never mass-produced at the end. The moment a design decision is confirmed (the user's answer lands) or a logic-tree node is confirmed, you draft its paired criterion — deterministic and self-checkable — and present it in the very next round as a numbered line: `📌 C<n> (<tag>): <criterion> — verify: <method>`. The user confirms or changes it like any other item; confirmed criteria enter the 📋 Criteria checklist with their tag and stay visible in every following round.

Pairing is universal: every confirmed decision and every confirmed node gets at least one criterion, trivial ones included (a label decision pairs with "the label renders exactly <text> in every supported language"). A criterion is written at confirmation time, from the confirmed wording — never reconstructed later from memory.

**Five-category tags.** Every criterion carries exactly one tag; the tags are the coverage sweep's checklist. A decision that touches several surfaces tags its criterion by what the check verifies (an approval loop's user-visible feedback → `interaction`; its enforcement invariant → `qa`):

1. `logic` — every logic-tree node fires as declared. Per leaf: one given-input → exact-output case. Ordered chains: one case per leaf PLUS cases proving the first-hit-wins order. Exception/fallback nodes: a firing case. Boundaries: empty set, single item, maximum, tie. No case rests on "probably".
2. `qa` — every real-world failure state the deliverable touches is handled and tested: auth/permission expiry, network error, timeout/rate limit, conflict, downstream store unavailable, invalid input rejected with an actionable error, retry/idempotency on writes, test-data cleanup back to zero.
3. `uiux` — the criteria pool in references/uiux-tree.md (width, language, design tokens, accessibility, forbidden content, automated scan where possible).
4. `interaction` — every interactive element behaves: hover affordance, click + keyboard paths, focus in/out, pending/loading state, success and failure feedback visible to the user, undo/redo on reversible edits, click-outside/Esc semantics.
5. `functional` — each capability works end-to-end on real data: create → read-back matches, update → persists, delete → gone, filter → correct subset, export → opens and is usable; verified in the real target system, not only in the app's own state.

At the final acceptance round the **coverage sweep** walks all five categories against every confirmed decision and node: a category either contributes its missing criteria (drafted and confirmed on the spot) or is marked `N/A — <reason>` (an N/A may cover a whole category or a named sub-scope — state which). A category skipped without a written reason is a violation.

### Final acceptance round

At the end, the final acceptance round **consolidates — it does not generate**: (1) restate the complete criteria checklist, every C<n> with its tag and verification method (all already user-confirmed); (2) run the five-category coverage sweep and propose only the criteria the pairing missed, each confirmed on the spot; (3) mark every non-applicable category `N/A — <reason>`; (4) present the consolidated list — a ❓ title, a short background, each criterion as a numbered line stating what it checks and how it is verified, then confirm / reject as the AskUserQuestion options with your recommendation. The full decision-table template does not apply to this round. Do not proceed until the user explicitly confirms them. Every criterion must be **deterministic and self-checkable**: it states the input, the operation, and the expected result precisely enough that a check either passes or fails — no "reasonable", "appropriate", "as needed", no judgment calls at verification time. Each criterion also states **how** it is verified (the command, the query, the inspection to run), not just what is verified. Coverage is one-to-one:

- Every confirmed design decision and every confirmed node maps to at least one checklist criterion — the sweep verifies this 1:1; a confirmed item without a criterion is a sweep failure.
- Every logic-tree node maps to a mechanical check or a test case: given a stated input, node L<id> must fire and produce exactly the stated output (ordered chains get a case per leaf, plus cases proving the first-hit-wins order).
- Every logic-tree node's traceability anchors are checkable: the code anchor location exists and carries the node-id comment, and the doc anchor location records the node — a sweep verifies each anchor mechanically.
- Every observable side effect named in an output (a notification, an alert, an external write) gets a criterion that verifies it mechanically — channel, target, and success check included. A side effect that cannot be verified this way goes back to the tree and is made precise first.
- External gates and consistency sweeps (below) get criteria of the same deterministic form: the named feedback either has arrived or has not; each listed artifact either matches the new name/structure or does not.

If a criterion cannot be written in this form, the underlying decision or node is not yet precise enough — go back and re-align it instead of shipping a vague criterion. Two closure duties are covered in the same deterministic form. (1) **External gates**: if the plan waits on feedback from outside this session (a review, a sign-off, an approval), the criteria name whose feedback, on which artifact, and what stays untouched until it arrives — then the session stops cleanly instead of dangling. (2) **Consistency sweeps**: any decision that renames or restructures something (a field, a table, a node card, a document) carries a sweep item listing every affected artifact, so all of them are updated together and nothing is left stale.

### Session closing

The design-tree session also needs: every logic-tree node explicitly confirmed (re-confirmed after any upstream change), every confirmed decision and node carrying its paired criterion, and the five-category sweep closed with N/A reasons written.
