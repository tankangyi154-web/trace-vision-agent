# Video Event Agent Implementation Plan

> For agentic workers: use executing-plans for integration and bounded parallel implementation where independent modules have agreed contracts. Follow test → failure → implementation → verification for behavioral code.

**Goal:** 招聘访客可以公开体验有真实证据的视频事件分析及受控实时 Agent。
**Architecture:** 本地视觉预处理，线上轻量确定性工具 + LangGraph；前后端同源 Vercel。
**Tech Stack:** Vue3, TypeScript, Vite, FastAPI, LangGraph, Qwen, Upstash, YOLO, ByteTrack。
**Spec:** docs/design.md；**Contract:** docs/contracts.md。

## Global constraints

仅本独立目录；不访问其他项目或凭据；不购买服务；密钥仅服务端。无虚构视觉/评测/Agent结果。每会话5问、每日50问；最多3次模型和5次工具调用。不得以本地构建冒充公开上线。

## Review focus

1. 请求重放、重复点击、并发和重启不能绕过全站限额。
2. 初始化就在区域内、边界、丢帧和结束截断不能误算进入或时长。
3. 模型返回不存在的证据或工具参数错误时不展示虚假引用。
4. 未配置模型/Redis、超时和API错误时保留可用的本地分析。
5. 手机宽度、视频跳转及会话上下文切换正确。

## Task 1: 数据契约与真实视觉包

Files: docs/contracts.md, vision/*, data/scenes/*, evals/*, docs/sources.md。
- [x] 固化 Scene/Track/Event/Evidence/API 契约。
- [x] 写本地处理与评测，验证真实视频源/许可；锁定依赖与权重SHA。
- [x] 实际运行三片段；检查帧、事件和截图；生成真实评测及失败案例。

## Task 2: 确定性API闭环

Files: api/domain.py, api/catalog.py, api/tools.py, api/index.py, api/tests/*。
- [x] 先测进入/初始化/中断/驻留、时间与引用、参数边界。
- [x] 实现场景、事件、轨迹、证据、BM25规则和导出接口。
- [x] 运行 pytest，确认媒体及JSON一致。

## Task 3: 可体验工作台

Files: web/src/*, web/package.json, web/vite.config.ts。
- [x] 实现响应式视频/对话工作台、时间线、证据及报告导出。
- [x] 实现算法评测及实现说明，真实状态、失败降级、可访问操作。
- [x] 类型检查、构建、浏览器桌面与375px验证。

## Task 4: 实时Agent与持久化额度

Files: api/agent.py, api/store.py, api/config.py, api/tests/*。
- [x] 先测原子额度、幂等复用、内容冲突、跨实例及失败状态。
- [x] LangGraph工具循环、模型/工具预算、上下文限制、引用校验和token记录。
- [x] SQLite仅供本地；生产缺Redis时拒绝实时调用。无Key时关闭入口。
- [ ] 有模型配置后验证实际调用；否则记录具体阻塞和用户设置入口。

## Task 5: 交付与部署

Files: README.md, vercel.json, requirements.txt, .env.example, docs/deployment.md, outputs/*。
- [x] 锁依赖、许可、CI、本地启动脚本及安全环境变量模板。
- [x] 独立审阅，修复具体缺陷后运行相关检查。
- [ ] GitHub仓库及Vercel发布（已有明确授权；缺账号时保留可部署版本）。
- [ ] 公开URL及无痕访问、手机验证、简短录屏、交付状态。

2026-10-31 用户追加安排：先交付本地版本，稍后授权上线。当前不创建/推送公开仓库、不继续Vercel发布。代码支持DeepSeek，真实Key与Upstash公网验收后续完成。已完成本地录屏、手机及无登录独立浏览器会话测试；公网URL/冷启动仍未验证。
