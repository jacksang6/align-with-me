---
name: grill-tree
description: Grill the user relentlessly about a plan, decision, or idea until a shared understanding is reached. Use whenever the user wants to stress-test their thinking, compare approaches or trade-offs, work out a procedure or if/then logic, design a page or interface, align on, review, or change anything UI/UX, revise an existing document, or change anything visible on an existing page, prototype, mockup, or interface (add, move, restyle, or remove elements) - including requests phrased as a discussion, an alignment ask, or a direct edit request. Visible UI/UX matters run the UI tree round with its decision console before any edit. Also use for any grill trigger phrase, even if the user never says the word.
disable-model-invocation: false
---

## Overview

Interview the user relentlessly until you reach a shared understanding. Map this as a **decision tree**: every decision branches into the decisions that hang off it. The tree takes one of four branch forms — design, logic, UI, or doc — routed by the table below.

Before the first round, read `references/question-form.md` (the shared question form and evidence standard; every branch uses it), `references/design-tree.md` (the session spine), and the reference file of the branch the round belongs to. Every round of every branch walks the design tree's process — frontier discipline, round mechanics, the audit line, paired criteria, the closing sweep — grilling every aspect of the tree relentlessly; the branch files (logic, UI, doc) are overlays that add their own trees and rules on top, never replacements. Route every round with the table below — it is the only router. One round runs one tree. A scenario that needs both a design tree and a logic tree runs as two rounds, design tree first.

| Class | Routes to | Round preamble | Channel |
|---|---|---|---|
| Role: who takes part, each party's permissions and responsibilities | Design tree (`references/design-tree.md`) — a Role is one decision row on it | Alignment table: Seq, Question, Decision | Question tool |
| Trade-off: choose between approaches, architecture, parameters | Design tree (`references/design-tree.md`) | Alignment table: Seq, Question, Decision | Question tool |
| Logic: if/then, loops, ordered steps, state changes, calculations, hand-offs between actors or systems | Logic tree (`references/logic-tree.md`) | ASCII tree in a `text` fence, plus the `.xlsx` of the evidence standard | Question tool |
| UI: what the user sees — layout, components, visual style, page structure; options that differ only in the presentation layer are UI too | UI tree (`references/uiux-tree.md`) — two-layer routing: the tree routes itself by entry (greenfield or refinement, judged from the context) and by lens | Five stages (S1 whole page → S5 visual sweep); greenfield walks them in order, a refinement enters at the change's scope (the Entry-routing table and Stages table live there); alignment table at the top of the console page | Decision console (`scripts/serve_decision.py`) |
| UX: how the user completes a task — flow, guidance, feedback, collaboration signals. Never the logic tree | UI tree, interaction part (`references/uiux-tree.md`) | Same as UI; every option carries a rendered artifact, or the card declares itself degraded | Decision console; a UX round with no rendered artifact at all falls back to the question tool in the same round |
| Doc: a wording change to an existing text document | Doc tree (`references/doc-tree.md`) | File path and section heading | Question tool, the diff as the option example |

- **Role** is a design decision about who does what. A hand-off step between roles is **Logic**, not Role.
- **UI** is the look and layout. **UX** is the flow a user follows to finish a task. Both route to `references/uiux-tree.md`.

## Asking in rounds

Work the tree in **rounds**. The **frontier** is every decision whose prerequisites are already settled: the questions you can ask _now_ without guessing at answers you haven't heard yet. Ask the whole frontier in one round. Ask it directly with AskUserQuestion: number each question and give your recommended answer. Do not ask for permission to ask, and do not ask whether to start or continue a round. The round itself is the question. Then wait for the user's answers before the next round.

Exception — UI rounds: the decision console (`scripts/serve_decision.py`) replaces the question form as the answering channel; the question tool stays the notify-and-wait channel. Launch, notify and completion rules live in `references/uiux-tree.md`.

The user may not know the underlying concepts. When a term or trade-off is new to them, explain the problem and each option with one concrete example, so they can see the implications. Do not re-explain a concept the user has already confirmed.

Each round the user answers reshapes the tree: settled decisions push the frontier outward and unblock questions that depended on them. Recompute the frontier and ask the next round. A question whose answer depends on another question still open in this round belongs to a _later_ round, not this one.

## Facts and confirmation

Finding _facts_ is your job, never the user's. When a frontier question needs a fact from the environment (filesystem, tools, etc.), dispatch a sub-agent to find it; don't ask the user for anything you could look up yourself. Don't block on it: a running exploration is an unsettled prerequisite, so only the questions downstream of it wait for the sub-agent to report; ask the rest of the frontier now. The _decisions_ are the user's: put each to them and wait.

Do not invent the user's intent or reasoning. When either is unclear, state your reading in one sentence and ask it as a frontier question. Once the user confirms a decision, treat it as settled and move on; do not re-confirm settled details or ask permission to continue.

## Closing

The session is done when the frontier is empty, every branch of the design tree is visited, the logic tree is fully confirmed, the criteria checklist is closed, and nothing is left silently assumed. Present the closing plan once and ask the user to confirm it; do not act on the plan before that confirmation. This gate covers the closing plan only. It never gates a round.

After the user confirms the proposed plan, invoke `/ask-matt` to assess the task and recommend the most appropriate execution path. Quote the `/ask-matt` assessment in the session before you present the options.

Then present the following options, clearly marking `/ask-matt`'s recommendation and briefly explaining why:

```
1. **Run the complete delivery workflow**  
   Invoke `/to-spec` → `/to-tickets` → `/implement-spec`.

2. **Implement with engineering quality controls**  
   Invoke `/to-spec` → `/implement-spec`.
```

Do not proceed until the user selects an option.

## Round gates

Tick every item before the round launches. The items verify the rules above; they add none.

- [ ] Route matched against the router table: class, routes-to, channel.
- [ ] This round's branch reference and references/design-tree.md read in this session.
- [ ] The spine binding restated: this round walks the design tree's process.
- [ ] Channel chosen per the router row: the decision console for UI decisions, the question tool elsewhere.
