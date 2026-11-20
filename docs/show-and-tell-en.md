# Show & tell: align-with-me — a decision-tree grilling skill built on your grilling primitive

Hi Matt and everyone 👋

I built [align-with-me](https://github.com/jacksang6/align-with-me) — a small repo that extends the grilling discipline from this repo into a **decision-tree shape**, and adds a local **decision console** for UI/UX rounds.

**What it does**

- `/grill-tree` interviews you in rounds, mapping your plan as a decision tree: every decision branches into the decisions that hang off it, and each round only asks the questions whose prerequisites are settled. Every option carries a probability and a recommendation.
- UI/UX decisions don't go through plain text: the skill launches a local decision console (`serve_decision.py`) — one card per decision, options sorted by probability, keyboard-first (1-9 / arrows / Enter), every option carries a rendered capture of the post-change state.
- It closes by handing the confirmed plan to the `/ask-matt` → `/to-spec` → `/to-tickets` → `/implement-spec` chain from this repo, so it depends on `mattpocock/skills` being installed first.

**Why a tree, not a checklist**

The checklist-shaped interview asks questions in a fixed order. Real design decisions don't have a fixed order — the answer to "does this feature ship public by default" changes what needs asking about the publish flow. The tree re-computes the askable frontier after every answer, so nothing gets asked before its prerequisites exist.

**Try it**

```bash
npx skills@latest add mattpocock/skills -a <agent>
npx skills@latest add jacksang6/align-with-me -a <agent>
```

Then run `/align-with-me` (the orchestrator, pairs the interview with `/domain-modeling`) or `/grill-tree` standalone.

MIT licensed, small and meant to be hacked on. Feedback welcome — especially on the routing table (design/logic/UI/doc branch forms) and the console's evidence rules.

Thanks for the grilling primitive — `/grilling` is the engine this whole thing runs on.
