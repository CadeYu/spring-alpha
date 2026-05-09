# Spring Alpha UI Guidelines

## 目标

本文档定义新版 Spring Alpha 的 UI 方向。MVP 的界面目标是像专业金融研究工作台，而不是营销页或开放聊天产品。

## 产品体验原则

- 第一屏应直接进入研究工作流。
- 用户通过 task cards 选择任务，不输入自由 prompt。
- Dashboard 信息密度要高，但结构要清晰。
- Evidence、citation status 和 degraded state 必须可见。
- Agent progress 应体现研究过程，但不能展示原始 chain-of-thought。

## MVP 页面结构

```text
┌────────────────────────────────────────────────────┐
│ Ticker selector        Model / Provider / Settings │
├────────────────────────────────────────────────────┤
│ Task cards                                           │
│ [Latest Earnings] [Business Drivers] [Cash Flow]    │
├────────────────────────────────────────────────────┤
│ Agent progress                                      │
│ Facts -> Filing -> Evidence -> Validation -> Report │
├────────────────────────────────────────────────────┤
│ Research dashboard                                  │
│ Thesis | Metrics | Drivers | Cash Flow | Evidence   │
└────────────────────────────────────────────────────┘
```

## Task Card 规则

- 每张卡只表达一个明确研究任务。
- 不使用自由输入框替代 task card。
- 卡片文案应短，解释应放在 tooltip 或辅助区域。
- 当前选中任务必须有清晰视觉状态。

## Evidence Trail 规则

Citation status 使用保守状态：

- `supported`
- `partial`
- `missing`
- `unverified`

每条 evidence 至少展示：

- Filing type.
- Filing date.
- Section.
- Short snippet.
- Citation status.

## Agent Progress 规则

默认产品界面展示 trust summary，不直接展示 raw trace。

可展示：

- Source status.
- Evidence count.
- Citation coverage.
- Filing type、filing date、section 和 short snippet。
- Human-readable degraded or unavailable reason。

不可展示：

- Raw chain-of-thought.
- Provider private prompts.
- Hidden scratchpad.
- Provider key.
- Full prompt payload.
- Full filing text.
- Raw `AgentEvent` JSON.
- Raw `planner_context` fields.
- Tool budget、step budget 和 fallback counter，除非在内部 debug panel。

内部 debug panel 可展示：

- Phase.
- Tool name.
- Status.
- Latency.
- Decision summary.
- Coverage summary.
- Degraded reason.

## Dashboard 规则

- 财务指标优先使用表格、折线图、柱状图和 waterfall。
- 业务驱动使用紧凑列表或 evidence-backed insight cards。
- 不用大面积装饰性渐变、空洞 hero 或营销式布局。
- 研究界面应支持扫描、比较和复核。

## MVP 视觉语气

目标风格：

- Professional.
- Dense but readable.
- Evidence-first.
- Calm.
- Fast to scan.

避免：

- Chatbot-first layout.
- Marketing landing page as the main app.
- Decorative card nesting.
- Unverifiable AI claims.
