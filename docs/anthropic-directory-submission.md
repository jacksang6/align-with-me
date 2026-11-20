# Claude 官方插件目录提交 — 表单填写内容

> 提交入口：https://claude.ai/directory/manage （需登录 Claude 账号）
> 仓库：https://github.com/jacksang6/align-with-me
> ⚠️ 图标单向门：icon.png 随首次提交固化，之后不可更换 —— 现在的图标已 validate 通过。

## Plugin repository URL

```
https://github.com/jacksang6/align-with-me
```

## Plugin name

```
align-with-me
```

## Short description（目录列表一句话，~100 字符内）

```
Alignment-first grilling: tree-shaped interview rounds (design/logic/UI/doc) with a local decision console for UI decisions.
```

## Full description（详情页）

```
Get aligned with your agent before a single line of code is written.

/align-with-me composes two skills:
- /grill-tree interviews you in rounds, mapping your plan as a decision tree - every decision branches into the decisions that hang off it, and each round only asks the questions whose prerequisites are settled. Options carry probabilities and recommendations; nothing is asked before it can be answered.
- /domain-modeling turns settled decisions into shared docs (glossary, ADRs) as you go.

UI/UX decisions run through a local decision console: one card per decision, options sorted by probability, keyboard-first (1-9 / arrows / Enter), and every option carries a rendered capture of the post-change state - never a text description of it.

Four branch forms route every round: design (roles, trade-offs), logic (if/then, state changes, with .xlsx evidence), UI/UX (the decision console), doc (diff-based rounds).

The confirmed plan hands off to the /ask-matt -> /to-spec -> /to-tickets -> /implement-spec chain from mattpocock/skills, which must be installed first.

MIT licensed. Small, composable, meant to be hacked on - see AGENTS.md for the maintainer rules.
```

## Category

```
Engineering
```

## Keywords / tags

```
alignment, grilling, decision-tree, spec, domain-modeling, interview
```

## Website / homepage

```
https://github.com/jacksang6/align-with-me
```

## Support / issues URL

```
https://github.com/jacksang6/align-with-me/issues
```

## License

```
MIT
```

## 提交前检查单

- [x] `.claude-plugin/plugin.json` 存在且 validate 通过（零警告）
- [x] `.claude-plugin/icon.png` 1024×1024 方形 PNG（首次提交后固化）
- [x] `.claude-plugin/marketplace.json` 存在（marketplace 通道同样可用）
- [x] LICENSE（MIT）
- [x] README 含安装说明与截图
- [ ] **等 Snyk 重扫**：skills.sh 上 align-with-me 的 Snyk WARN（W011）源于 /reverse-engineer-anything 引用，该引用已在 commit a74598f 移除 —— 建议重扫转绿后再提交，或提交时在备注里说明
- [ ] 提交后在 claude.ai/directory/manage 关注审核状态

## 建议提交时机

Snyk 审计是 skills.sh 侧的定期扫描（上次 2026-11-18）。触发因素已移除，但扫描有周期。**不阻塞提交**（Anthropic 目录的审核是独立的安全扫描），只是如果希望万无一失，等 skills.sh 上 WARN 转 PASS 再提，页面截图更干净。
