# EVERSTEAD 成果站 · 设计规范

> 提炼自 [ui-skills](https://github.com/ibelick/ui-skills)（Moses/ibelick，269 条 skill），
> 已过滤掉 Tailwind / React 专属条目，只保留**纯 CSS 可执行**的部分。
> 适配本站约束：纯静态 HTML + 内联样式、零外部依赖、GitHub Pages 国内直连。

改站、做一页通、写新页面前对照本清单。

---

## 0. 技术约束（不可违反）

- **零外部依赖** —— 不引 CDN、不装构建工具，一切内联或本地文件
- **不引框架** —— 不用 Tailwind / React / Vue，写原生 CSS
- 新增第三方库前先问：能否用 30 行原生 CSS 实现？能则不引
- 中文字体栈：`'Microsoft YaHei','PingFang SC',sans-serif`；数字用 `var(--mono)` + `tabular-nums`

---

## 1. 动效（最高频踩坑区）

| 规则 | 原因 |
|---|---|
| **禁止 `transition: all`**，必须指名属性 | `all` 会让浏览器监听所有属性变化，触发无谓重排；也让意图模糊 |
| 只动 `transform` / `opacity` | 这两者走合成层，不触发重排重绘 |
| 禁止动 `width`/`height`/`top`/`left`/`margin`/`padding` | 触发布局抖动 |
| 交互反馈 **≤ 200ms** | 超过就感觉迟钝；本站用 `.15s ~ .25s` |
| 入场用 `ease-out` | 立即响应；`ease-in` 显得拖沓 |
| 不写自定义缓动曲线 | 除非明确需要，用标准关键字即可 |
| 循环动画离屏要暂停 | 省电、省 CPU |
| 必须尊重 `prefers-reduced-motion` | 无障碍要求 |

```css
/* ✅ 正确 */
transition: color .2s, border-color .2s;

/* ❌ 禁止 */
transition: all .2s;
```

---

## 2. 交互反馈

- **可点击元素必须有 `:active` 按压反馈**
  ```css
  .btn:active{transform:scale(.97)}
  ```
  （记得把 `transform` 加进 `transition`，否则按压无过渡）
- `:hover` 只改 `color` / `border-color` / `background-color` 这类不需要重排的属性
- 可键盘聚焦的元素要有可见焦点样式（`:focus-visible`）
- 纯图标按钮必须带 `aria-label`
- **破坏性操作**（删除、覆盖、推送）要有二次确认

---

## 3. 排版

| 规则 | 用法 |
|---|---|
| 标题加 `text-wrap: balance` | 多行标题避免末行孤字 |
| 正文加 `text-wrap: pretty` | 避免段落孤字 |
| **数字一律 `tabular-nums`** | 表格、KPI、净值对不齐就靠它 |
| 不擅自改 `letter-spacing` | 除非设计明确要求 |
| 密集区域用 `truncate` / `line-clamp` | 防止撑破布局 |

```css
h1,h2,h3,h4{text-wrap:balance}
p,li{text-wrap:pretty}
.num{font-variant-numeric:tabular-nums}
```

---

## 4. 布局与层级

- 用固定间距标尺（4/8/12/16/24/32px），不随性写 `13px`、`27px`
- 网格优先：`display:grid; grid-template-columns:repeat(auto-fill,minmax(...))`
- 方块元素用等宽等高写法（`width`+`height` 同步），避免一边固定一边自适应
- **z-index 用固定档位**，不写魔法数字：
  ```
  1  内容浮起
  10 局部浮层（下拉、tooltip）
  100 导航栏
  1000 全屏遮罩 / 模态
  ```
- 固定定位元素要留安全区（移动端刘海屏）

---

## 5. 配色

**成果站自有配色**（深空底 + 青紫科技感）：

| 变量 | 值 | 用途 |
|---|---|---|
| `--bg` | `#03060c` | 页面底 |
| `--panel` | `rgba(10,20,38,.55)` | 玻璃卡片 |
| `--line` | `rgba(56,189,248,.16)` | 分割线（弱） |
| `--line-strong` | `rgba(56,189,248,.45)` | 分割线（强/悬停） |
| `--cyan` | `#22d3ee` | 主强调 |
| `--blue` | `#3b82f6` | 次强调 |
| `--violet` | `#8b5cf6` | 点缀 |
| `--text` | `#e2ecf7` | 正文 |
| `--muted` | `#7d92ad` | 次要文字 |

**公司品牌色**（涉及对外/工作产品时叠加，见 `品牌规范-中邮资管/`）：

| 名称 | HEX | 用途 |
|---|---|---|
| 标准金 | `#D29B0E` | 强调色；**不作大面积底色** |
| 深色 | `#231815` | 深底 |
| 辅助棕 | `#876D4B` | 次要 |
| 辅助钢 | `#898C8E` | 次要 |
| 辅助灰 | `#BBBBBB` | 次要 |
| 白 | `#FFFFFF` | 底色 |

> 深色底上的金色要提亮（用 `--zy-gold-on-dark`）。
> CMYK / PANTONE 是印刷口径，屏显一律用 RGB / HEX。

**禁忌**：默认不用紫渐变 + 发光特效堆砌（典型"AI 味"来源）；强调靠留白和层级，不靠特效。

---

## 6. 无障碍

- 正文对比度 ≥ 4.5:1，大字 ≥ 3:1
- 触控目标 ≥ 44px（移动端）
- 键盘可完成所有操作，焦点不能丢
- 图片给 `alt`，装饰图给 `alt=""`
- 不用颜色作为**唯一**信息载体（涨跌用红绿时也要带 +/- 符号）

---

## 7. 自检清单

改动站点的样式后，逐条打勾：

- [ ] `grep -rn "transition: *all" --include="*.css" --include="*.html" .` 结果为 0
- [ ] 新增的可点击元素都有 `:active`
- [ ] 动了 `transform` 的元素，`transition` 里含 `transform`
- [ ] 标题有 `text-wrap: balance`
- [ ] 数字区域有 `tabular-nums`
- [ ] 无横向溢出（`scrollWidth <= clientWidth`）
- [ ] 控制台无报错、无失败请求
- [ ] 移动端（≤400px）不塌不挤
- [ ] 涉及品牌呈现的，色值取自 `品牌规范-中邮资管/`

---

## 8. 双胞胎文件坑 ⚠️

本站存在**同一份 CSS 在两个位置**的情况：

```
zhongyou-theme.css              ← 被 1 个文件引用（根目录）
radar-site/zhongyou-theme.css   ← 被 3530 个雷达页引用（副本）
```

**改根目录那份不影响雷达站**。修改这类文件时必须两份同步：

```bash
cp zhongyou-theme.css radar-site/zhongyou-theme.css
diff -q zhongyou-theme.css radar-site/zhongyou-theme.css   # 确认一致
```

> 2026-09-22 已踩坑：只改了根目录一份，3530 个雷达页仍是用旧样式。

---

*最后更新：2026-09-22*
