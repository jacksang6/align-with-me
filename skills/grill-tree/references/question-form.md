# Question form and evidence standard (shared by every branch)

One question form and one evidence standard for every branch. Each tree file defines only its own preamble that goes before the first question of a round: the design tree uses an alignment table (references/design-tree.md), the logic tree uses an ASCII tree in a `text` fence (references/logic-tree.md), the UI branch serves console cards (references/uiux-tree.md). The question block below has the same structure in every branch.

## Delivery

- Non-UI questions go in the message body with clickable choices in the question tool. The whole frontier of the round goes out as ONE batch in a single question-tool call. The rendered template appears in the message body, and the options also appear as clickable choices in that call.
- UI questions go out as decision-console cards carrying the same structure — never plain-text asking for a UI decision. The launch, notify and completion contract lives in references/uiux-tree.md. The console is the answering channel; the question tool is only the notify-and-wait channel.
- The console page language follows the session language: the spec author sets the page `lang` field to the session language every round. Every fixed string on the page (buttons, hints, toolbar names) renders from the script's built-in copy table — never authored ad hoc in the spec.

## Options

- Labels are A, B, C in the question body. Exception: console cards number options 1, 2, 3 and the digit keys 1-9 pick them. A question offers 2-3 options. The decision cell in any table holds the option text only, never the letter.
- Options are sorted by probability, descending. The recommended option is the one marked `➡️ Recommended Answer`.
- In the template, ✅ marks the recommended option row; 🟡 and 🟤 are plain probability-order dots, not quality judgements.
- Each option has Reason, Example, Pros, Cons.
- Implementation support is probed, never assumed: an option that depends on an API, a platform capability, or existing project code reaches the user only after the agent has probed that support — searching the user's knowledge base first (an existing research document is cited and linked as the probe evidence), then probing the real environment for what the knowledge base lacks (file:line, command output, or captured reference). A capability with no verified support never becomes a choice: the option is dropped, or presented as blocked with the missing capability named. The probe result is written to a reference document — into the user's knowledge base when one exists, so research accumulates — and becomes the option's basis line, and the confirmed decision's paired criterion verifies through the probed support — designing what the environment cannot back is a violation.

## Real data only (hard rule)

- Every Explanation bullet and every Example line uses real data from the task: a real row, a real file, a real command output, a real past decision, a real log line. Never invent a scenario, a number, a name, a row, or a result.
- Never fabricate, "illustratively" tweak, or estimate a cell — in the markdown tables, in every sheet of a generated .xlsx, and in every rendered capture. If the data is not in context, dispatch a sub-agent to find it; a missing number means the question goes pending, never a made-up one.
- If no real example exists, say so in the Explanation, state what probe would produce one, and mark the question pending.
- Probabilities and estimated effort are the only estimates allowed in the question block. Each option line carries its one-line basis in parentheses after the label.
- When data or rendering is missing, state the degradation in the round that proposes the options, put it to the user as a question, and continue only after agreement. Never degrade silently, never explain after the fact.

## Explanation protocol (assume no familiarity with jargon)

The user may not be an engineer: every question must be answerable without reading any docs or knowing any jargon. These are hard rules — violating any one means the question is not done:

1. **Translate every term of art.** Any jargon in the current domain (technical or business: database, finance, manufacturing, medical...), either replace it with everyday language or define it in one plain sentence at first use. No arrow chains (`A → B`) in prose explanations — one idea per sentence, short sentences. This ban covers prose only: tree drawings and log detail values are drawings/data, and arrows are required there by the logic-tree rules.
2. **Consequence first, mechanism second.** The first line of every option states an observable outcome ("do this twice and the result is identical"). Implementation goes on the second line, in plain language, one sentence.
3. **Real before/after comparison is mandatory.** Show two side-by-side tables: rows **before** and rows **after**, every cell real under the Real data rule above. If the question needs a change scenario, use a change that really occurred in the data (an old snapshot vs current rows, a row that actually changed); if no real change exists, say so and ask the user how to proceed — never invent one. Whenever a question involves a before-vs-after change, also attach the before/after .xlsx of the evidence attachment rules below.
4. **Show the real output rows.** When a question is about what gets recorded or produced (logs, checklists, snapshots, status tables, output files...), draw the exact rows each option would write — with real column names and real values — instead of describing them ("a delete would be recorded").
5. **Quantify consequences.** When an option affects scale, compute the magnitude from the task's real numbers: unit size × frequency = total (rows, records, money, people, duration — whichever is real here). Users decide on magnitudes, not concepts.
6. **Re-explain protocol on "I don't understand".** Never repeat the same wording or swap synonyms. Change the approach: pick one real row and walk the mechanism step by step — what happens at each step, which row appears at the end. Then continue with the round; if the user still does not follow, walk it again with a different row.
7. **Mechanism questions get a numbered walkthrough up front.** When a question is about how something works (a pipeline, a calculation, a flow between systems), the Explanation includes a numbered step-by-step walkthrough (1. 2. 3.) carried by one real row or one real set of rows from the task's data — don't wait for the user to say "I don't understand" before switching to this form.

## Degraded path when data is unavailable

When the environment has no data for a question (no access to the system, or the target table is greenfield and does not exist yet): comparison tables may be given at the structural level and labelled as such; the .xlsx is deferred and becomes a named backfill item (an acceptance criterion or an external gate); mechanism walkthroughs use the expected row shape instead of a real row.

## Measured impact and the evidence .xlsx

Every option carries its **measured impact**:

- Show % and absolute count paired in one cell (`59.1% (308/521)`). A bare % hides scale; a bare count hides share.
- Impact numbers come from probes, queries, or files already in context. Never estimate or invent them. A missing number means: dispatch a sub-agent to measure it and mark the question pending.
- State the measuring caliber in one bullet under the table.
- The only permitted estimate is estimated effort (`~30min`, per option: implementation + validation, plus recurring runtime cost when it applies), with its basis in one bullet under the table. Genuinely zero is written `0 (caliber-only ruling)`.
- Break rows down by the entity the user tracks when impact differs across them. A per-entity table beats one blended global row.
- Every decision question carries a **re-check bullet**: how the impact numbers get re-checked after the round (which probe re-runs, which output is diffed, which query).
- When the user says "I don't understand", add a file before adding more prose.

The evidence .xlsx rules (naming scheme: `grill-Q<N>-<topic>.xlsx`, clickable full path in the question body):

- **Before/after case** (Explanation protocol rule 3): a real, openable .xlsx with at least three sheets — "Before", "After", and "Rows this option writes" (the first two carry the affected table's real columns; the third carries the destination's real columns) — filled with the task's real columns and real row values under the no-fabrication rule.
- **Option-choice case**: a real .xlsx with sheets Candidates (options side by side), Measured (per-entity numbers), and Notes (caliber, denominator, data nature), produced via `scripts/gen_xlsx.py` — never a hand-built file. Missing data means: probe first and mark the file pending.
- Design-tree rounds have no .xlsx by default; the two cases above apply whenever they occur. Logic-tree rounds always require the option-choice .xlsx.
- List the options as the decision table in the body, and repeat them as short clickable labels in the question tool (`A: <label>`). The recommended option is the first row, with its reasoning in one sentence.
- The decision table, the measured impact, and the .xlsx are the evidence standard carried inside the template below (its 💡 and 📊 hold them).

## Template

```
❓ **Q<N>** - **<question title>**: <question body, which may contain multiple paragraphs and multiple choices>

💡 **Explanation**
- <real example from the task>
- <intent of the question in plain language>


📊 **Options (sorted by probability)**
A. 65% ✅ <Option A> (<one-line basis>)
   - Reason: <why this option is likely>
   - Example: <real example from the task>
   - Pros:
      1. <pro>
      2. <pro>
   - Cons:
      1. <con>
      2. <con>

B. 25% 🟡 <Option B> (<one-line basis>)
   - Reason: <why this option is likely>
   - Example: <real example from the task>
   - Pros:
      1. <pro>
      2. <pro>
   - Cons:
      1. <con>
      2. <con>

C. 10% 🟤 <Option C> (<one-line basis>)
   - Reason: <why this option is likely>
   - Example: <real example from the task>
   - Pros:
      1. <pro>
      2. <pro>
   - Cons:
      1. <con>
      2. <con>

➡️ **Recommended Answer:** 65% ✅ <Option A>
```

- The 💡 block is never dropped. If a bullet does not apply, write one line saying why.
- Mechanism questions (how something works, a flow between systems) get a numbered walkthrough (1. 2. 3.) inside the Explanation, carried by real rows or real data.

## Delivery gate

Tick every item before an ask goes out. The items verify the sections above; they add none.

- [ ] 2-3 authored options plus the write-in; disagreeing with every option is a first-class answer.
- [ ] Real business data only; a no-render round declares itself degraded.
- [ ] Plain language a novice can decide with; one ask surface per decision.
- [ ] Measured impact quantified; a table-shaped decision ships the generated .xlsx, never a hand-built file.
- [ ] Capability-dependent options carry a probe: the supporting API or code path was confirmed in the real environment before the ask; unsupported options are dropped or blocked, never offered as choices.
- [ ] Every probe result lives in a reference document the function spec cites; every confirmed answer reached the function spec and the version ladder — verified by the coverage gate, not by memory.
