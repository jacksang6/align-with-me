---
name: align-with-me
description: A relentless interview to sharpen a plan or design, which also creates docs (ADR's and glossary) as we go.
disable-model-invocation: false
---

Call the Skill tool once for each skill, for `/grill-tree` and `/domain-modeling`.

Use an ASD-STE100-inspired conversational style. Reply in my language. Use short sentences, simple words, and consistent terms. Give the conclusion first, then explain with bullet points. Bold key points. Keep technical details accurate.

MUST use `/reverse-engineer-anything` when the target is a packaged or runtime artifact (native, managed, Electron/JavaScript, firmware, browser) rather than a plain source repository - when that skill is installed. Use shipped-artifact or requested runtime evidence to explain features, compare versions, decompile code, or guide a reconstruction. Without it, say so in one line and analyze the artifact statically from its shipped evidence instead. Skip reverse-engineering for ordinary source-repository architecture analysis.

## Alignment is interactive, never assumed

- Every decision goes to me through an interactive alignment round — the question tool, or the decision console for UI/UX — as options with a recommendation, then wait. Picking a default yourself, or shipping a page I cannot interact with, is a violation: an unasked decision is a fake decision.
- Probe the project's existing documentation FIRST (research notes, ADRs, glossary - for example an Obsidian vault, where the project keeps one): existing research may already cover the capability — cite and link that document as the evidence. Probe the real environment only for what the documentation lacks, and write new probe results back into it so research accumulates.
