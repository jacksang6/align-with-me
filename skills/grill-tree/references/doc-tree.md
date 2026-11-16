# Doc tree (Doc rounds)

## Round preamble

Doc rounds walk the design tree's process too (references/design-tree.md) — the audit line and the criteria discipline apply — as an overlay on the design tree, never instead of it. Above the diff block: the real file path and the section heading the change belongs to.

## Round rules

1. Read the real file first. Copy every removed line exactly.
2. One section per round, unless the user asks to review several sections together. Show it as a diff block: `-` = current text, `+` = proposed text.
3. Under the block: Reason, Pros, Cons (question-form template, references/question-form.md).
4. Choices in the question tool: Apply, Adjust, Skip.
5. Apply only after the user says yes. Then run the file's gate (`check_skill.py` for skill files).

### Round gates

Tick every item before the round closes. The items verify the rules of this file; they add none.

- [ ] Real file read first; every removed line copied exactly.
- [ ] Diff block shown with Reason / Pros / Cons.
- [ ] Applied only after the user said yes; the file's gate ran after applying.
- [ ] One neutral challenge spoken at close (what the new wording breaks).

## Evidence

The diff is the before/after evidence. The .xlsx rules of the evidence standard (references/question-form.md) do not apply.

## Round closing

End each round with one neutral challenge: what the new wording breaks.
