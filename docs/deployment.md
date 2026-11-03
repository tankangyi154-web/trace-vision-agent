# Vercel 个人免费项目部署

本页保留首版静态样例/轻量API的部署草案，未获得本轮上线授权。新首页需要本机YOLO/PyTorch与FFmpeg执行上传推理，不能把下面的静态Vercel方案当作上传功能已上线。当前仅本地交付；如果以后公开部署，需先选择独立CPU推理服务与临时存储/清理，或将上传功能限于本机。不购买GPU或云服务，也不在本轮部署。

当前配置目标是 Vercel Hobby：单个 FastAPI 项目，Vue 构建产物通过 FastAPI frontend 声明提升到 CDN。不需要购买服务器、付费计划、域名或公网数据库。访问者无需登录或提交 API Key。

## 账号与配置（仅项目自己的凭据）

1. 登录自己的 [GitHub](https://github.com/login) 和 [Vercel](https://vercel.com/login) 个人账号。
2. 在 [DeepSeek 开放平台](https://platform.deepseek.com/api_keys) 创建 API Key，在本机 `.env.local` 的 `DEEPSEEK_API_KEY` 填入。不要提交到 Git，不要粘贴聊天。默认 `LLM_PROVIDER=deepseek`、`LLM_MODEL=deepseek-flash`、`DEEPSEEK_BASE_URL=https://api.deepseek.com`。如平台模型名称变化，以实际可用列表为准，重跑真实工具调用验收。
3. 在 [Upstash Console](https://console.upstash.com/redis) 创建免费 Redis，取 REST URL 与具有写权限的 REST TOKEN，填入同名 `UPSTASH_REDIS_REST_URL` 和 `UPSTASH_REDIS_REST_TOKEN`。不要选择付费套餐或开启付费升级。
4. 将源码建立成独立 GitHub 公开仓库。Vercel Import 该仓库，Root Directory 选项目根，不是 web/；Framework 选择 FastAPI，Build Command 已在 vercel.json 中定义。不单独重写全部路径到 index.html。
5. Vercel 项目环境变量分别添加 DeepSeek key、provider/model、Upstash URL/token、APP_MODE=production、SESSION_QUESTION_LIMIT=5、DAILY_QUESTION_LIMIT=50。不上传 `.env.local`，不设置任何 `VITE_*_KEY`。预览与生产建议分别使用独立 Redis 或不同额度前缀（当前v1前缀，因此不可误认为预览额度隔离）。
6. 发布生产。检查 Deployment Protection / Vercel Authentication 的生产访问策略，确保自己的公开生产 URL 可在未登录无痕窗口访问。不要把受保护预览 URL 当公开体验 URL。

可选百炼：`LLM_PROVIDER=qwen`、`LLM_MODEL=qwen-plus`、`DASHSCOPE_API_KEY`、`DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1`。

## 发布后必须实际验证

- 无痕窗口 GET /api/health，确认 production、模型名及 live_agent 状态。
- 三个场景原始/标注视频可播放；图片可加载；选择区域/阈值实际重算；事件/证据时间跳转有效；375px 无横向溢出。
- 用项目 API 真实完成“进入区域A的目标”“哪个驻留最久”“生成报告”和一次连续追问。检查工具记录、引用、真实token；模型/网络延迟在实际运行后记录。
- 同request_id并发提交只占一次额度；跨实例/重启额度仍保留；全站额度耗尽/存储不可达时实时入口报明原因，静态视频、统计、报告仍可用。
- 不把开发代理抽检当独立人工评测，不宣称未经测量的mAP、IDF1或性能提升。

## 当前行为和限制

模型缺Key时health明确live_agent=false。生产缺Redis不会回退内存或SQLite；未知执行状态不自动重试、不自动返还可能已经消耗的额度。模型API超时单次22秒、整问78秒、函数90秒，每问最多3次模型和5个工具。实际冷启动/地域连通性需线上测试，本地构建不证明线上可用。

日额度按Asia/Shanghai日期保存。无登录会话令牌24小时过期；每日全站额度保护仍独立生效。会话额度并不等于每个人限额，清浏览器能创建新会话，但不能绕过全站每日额度。生产Redis会话/请求/history最多保留24/48/24小时，不接入第三方用户追踪。本地SQLite调试记录保留在被Git忽略的work/local.sqlite3，不承诺同样的自动清理。

官方参考（2026-10-31读取）：[Vercel FastAPI/CDN](https://vercel.com/docs/frameworks/backend/fastapi)、[Python Runtime](https://vercel.com/docs/functions/runtimes/python)、[Hobby](https://vercel.com/docs/plans/hobby)、[DeepSeek Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)、[LangGraph](https://docs.langchain.com/oss/python/langgraph/overview)、[Upstash REST](https://upstash.com/docs/redis/features/restapi)。
