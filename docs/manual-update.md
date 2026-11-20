# 手动更新包：掘金 / 知乎 补「UI 分支真本事」小节

> 掘金编辑器在自动化 Chrome 里无法挂载（SPA 白屏），知乎编辑器合成粘贴会复制内容 —— 两处都请手动补。图片在本仓库 `docs/images/` 下，上传用各编辑器的图片按钮。

## 要追加的小节（两平台通用，贴在「真正的差异：UI 决策控制台」小节之后）

```markdown
## UI 分支的真本事：线框证据 + 标注回传

问到 UI/UX 不止发卡片。每个选项自带**线框图或真实截图**，控制台自动画好红色证据框，标出决策落点 —— 你看到的是「决策落在哪个分区」，不是一段文字描述：

【图一：docs/images/console-wireframe.png】

你还可以直接在**真实页面上标注备注** —— 画框、写批注、点「保存并替换」，你的标注替换该选项的证据随答案回传：

【图二：docs/images/console-annotate.png】

Design / Logic / UI-UX / Doc 四棵树 + 通用问题表，不同类型的问题走各自的证据标准。
```

## 操作步骤

### 掘金

1. 打开已发文章 → 你的头像下拉（或文章操作菜单）→ 编辑
   （直链 https://juejin.cn/post/7710139371357700123/edit 在自动化浏览器里白屏，你自己的浏览器没问题）
2. 光标放到「真正的差异」小节末尾（四种问题 之前）
3. 贴上面的 markdown 小节（去掉两行【图】占位）
4. 工具栏图片按钮 → 上传 `docs/images/console-wireframe.png` → 拖到第一段后
5. 再上传 `docs/images/console-annotate.png` → 拖到第二段后
6. 点发布 → 弹窗确认（分类/标签沿用已保存的）

### 知乎

1. https://zhuanlan.zhihu.com/p/2107249492860874864/edit
2. ⚠️ 知乎编辑器加载草稿时**旧图可能显示为空位**（之前实测丢图）—— 发布前检查「真正的差异」小节的图还在；丢了就重传 `decision-console.png`
3. 光标放到「真正的差异」小节末尾，贴小节文字（知乎吃富文本粘贴：先在本机渲染成 HTML 再贴，或直接打字）
4. 工具栏「图片」→ 上传两张图，插在对应位置
5. 点发布

## B站（同前）

编辑器已开好（全文+标题+三个占位标记）：https://member.bilibili.com/platform/upload/text/new-article
在三个 `【图一/二/三占位】` 标记处，用工具栏图片按钮分别插入：

- 图一 → `docs/images/decision-console.png`
- 图二 → `docs/images/console-wireframe.png`
- 图三 → `docs/images/console-annotate.png`

插完删掉占位文字，点「发布」。
（B站上传被公司代理挡，自动化插图全是碎图，所以必须手动）
