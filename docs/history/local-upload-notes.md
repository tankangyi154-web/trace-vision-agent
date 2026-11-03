# 旧版本地升级记录（归档）

以下保存原分发包的开发记录，不代表当前分发包携带私密配置。当前入口和运行方式以根 README 为准。

# 视迹 Trace · 图片与短视频助手

上传自己的图片或短视频→手动填写或选择1—3种物体→开始分析→看标注画面和简短总结→继续提问、补找新物体。Vue 3 + FastAPI + LangGraph；本机真实DeepSeek已配置。

**默认首页支持真实上传并重新运行检测。** 普通用户无需理解区域、阈值、目标内部编号或模型配置。技术案例和评测收进“项目原理”。本轮只交付本地版本，没有部署公网。

工作台先上传、后指定物体；预览与标注结果保留在同一画面区，右侧完成简短统计和追问。证据缩略图可放大或定位视频。消息区独立滚动，阅读旧回答时不强拉到底；手机在画面/问答之间切换，保留播放器和阅读位置。恢复的历史不标成新回答。

## 当前本地升级

打开 [本地助手](http://127.0.0.1:8000/)，选择文件并手动填写或选择1—3种常见物体，再点“开始分析”。留空不运行。手填支持中英文、逗号分隔和常用叫法（如轿车→汽车），回车或点击添加后显示真实识别类别；不支持的名称就地提示，不伪装成未检出。范围取决于现有权重的80种COCO类别，不是YOLO架构只能支持80类；任意文本提示需要另外接入开放词汇模型。列表可辅助搜索多选，“用示例体验”和专用API已移除。后续直接问“再找一下卡车”，系统在同份素材上实际补检、合并标注并保留旧目标编号；每条问题最多新增3种，累计范围可以超过3种，已查过的类别复用结果。

图片支持JPG/PNG/WebP≤10MB、≤2000万像素；短视频支持MP4/MOV/WebM≤30MB、≤20秒。视频按5fps抽样检测/跟踪并生成可播放的标注视频，单次最多100帧，不静默把超长视频截断当作完整分析。

上传文件放入独立的 `work/uploads/{UUID}`，不进入Git或公开样例；原输入在首次处理后删除，私密规范化副本与结果在最后一次分析后约30分钟清理，也可主动删除；相应聊天记录同步清理，已调用额度不退回。副本只供本机补查，不提供下载接口。追问使用当前素材工具，数量/单位/类别/时间由工具组成完整中文事实，模型选择事实并补充解释，不能把类别数改写成车辆数。原图、视频及私密访问链接不发给文本模型。

本机已准备CPU视觉环境和固定权重；普通API依赖不含PyTorch。新机器的准备方法见[上传处理说明](docs/local-media.md)。当前入口不需要Vercel或Upstash授权。之前固定T001复核和三场景区域事件仍可从“项目原理”打开；其历史验证见[证据复核记录](docs/evidence-review-validation.md)。

## 保留的技术能力与边界

- 三段有来源的真实视频：船舶进入、道路驻留、夜间观测边界。真实 YOLO11n + ByteTrack 输出，原始/标注视频、轨迹、事件、截图可相互定位。
- 五个只读工具：`search_events`、`get_track`、`calculate_dwell`、`get_evidence`、`retrieve_rules`。中文规则 BM25 检索与片段引用，时间由程序计算。
- LangGraph 有界工具循环，服务端历史按场景/区域/阈值隔离；引用未检索证据时拒绝展示。最多3次模型/5次工具，不自动重试付费请求。
- 每会话5问、全站每日50问；Upstash Lua原子预留、幂等请求和持久化状态，SQLite只供本地。真实token计量；网络不确定时标明用量可能不完整。
- 6帧/13参考框开发抽检与夜间漏检案例，**由开发代理辅助标注、未独立人工复核**。不提供泛化mAP/IDF1、硬件速度或未经跑测的提升。

## 本地运行（无需任何Key即可播放及分析）

环境：Python3.12，Node24（Node22+也满足Vite要求，未在本机测），npm11。

PowerShell，项目根目录：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
npm --prefix web ci
npm --prefix web run build
Copy-Item .env.example .env.local # 仅第一次，已有配置不要覆盖
.\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000 --no-access-log
```

打开 [本地工作台](http://127.0.0.1:8000)，或执行 `scripts/start.ps1`。开发热更新：API同上，在另一个终端 `npm --prefix web run dev`，浏览器访问5173。前端/api代理至8000。

真实模型：在被Git忽略的`.env.local`填`DEEPSEEK_API_KEY`后重启API。默认DeepSeek官方`deepseek-flash`非思考模式。无需将Key提供给访客。生产实时问答还需要Upstash REST配置；详见[部署说明](docs/deployment.md)。

若Windows受限环境的默认TEMP不可写，在当前终端先执行：

```powershell
New-Item -ItemType Directory -Force work/tmp | Out-Null
$env:TEMP=(Resolve-Path work/tmp).Path
$env:TMP=$env:TEMP
```

## 相关验证

```powershell
.\.venv\Scripts\python.exe -m pytest -q
python -m unittest discover -s evals -p test_evaluate.py
npm --prefix web run build
```

测试中明确使用合成单元输入及注入模型响应，不代表线上模型已接通。真实模型和公网验收分别记录在交付状态中，不由测试PASS替代。

## 处理自己的视频

公开网站不接收上传；本地单独安装视觉环境，按[视觉复现说明](docs/vision.md)运行`vision/process.py`。模型版本/权重、视频来源SHA256、处理配置和完整依赖均已锁定。使用自己有权处理及公开的素材。

## 结构与设计

原理页只显示当前本地上传的实现摘要。源码与复现入口提供本版本的关键文件及运行文档下载；尚未提供公开仓库。实现核对顺序：`vision/analyze_media.py`（检测、跟踪与补查）→`api/media_tools.py`（媒体查询、数量与证据绑定）→`api/agent.py`（有界工具调用与回答校验）。历史区域事件的统计口径位于`api/domain.py`。

详细上传边界与临时文件管理见[本地处理](docs/local-media.md)，完整数据约定见[契约](docs/contracts.md)，配置及额度、幂等和部署要求见[部署](docs/deployment.md)。这些是运行说明，不表示当前已经公开部署。

历史案例入口：[区域事件工作台](http://127.0.0.1:8000/#experience)、[观测缺口复核](http://127.0.0.1:8000/#investigation)。这些公开视频案例已预先完成视觉处理，与当前首页对上传素材重新运行检测的流程分开。复现及判定边界见[视觉说明](docs/vision.md)与[证据复核记录](docs/evidence-review-validation.md)。视频跟踪编号不代表唯一物体身份；驻留只累计实际有效观测，不推断缺失时段。

| 目录 | 职责 |
| --- | --- |
| web/ | Vue工作台、评测、实现说明、公开媒体 |
| api/ | 确定性事件、BM25、Agent、额度与API |
| vision/ | 本地YOLO/ByteTrack处理与复现 |
| data/ | 真实轨迹场景和示例区域规则 |
| evals/ | 有边界说明的抽样参考标注与评测 |
| docs/ | [设计](docs/design.md)、[契约](docs/contracts.md)、[计划](docs/plan.md)、[素材](docs/sources.md)、部署 |

开源基础：YOLO11n、ByteTrack、LangGraph、Vue、FastAPI。项目实现工作：归一化场景契约、可核查事件计算、证据索引、规则检索、有界工具编排、引用验证、额度幂等及交互工作台。没有声称自行训练基础检测器。

相机移动、漏检、ID断裂、边界抖动均影响事件。未标定的视频不能给出航速、实际距离、身份、损伤或真实违法结论。初始已在区域内不计进入；缺失观测不计驻留；截断区间是已观察时长下界。

## 许可

项目代码采用 AGPL-3.0-or-later，以与所使用Ultralytics框架/模型的公开许可相适配。各开源组件保留其各自许可。视频、剪辑、证据截图及相关媒体衍生物采用来源声明的CC BY-SA4.0，不改为代码许可。见[素材与许可](docs/sources.md)、`web/public/media/ATTRIBUTION.txt`、LICENSE与THIRD_PARTY_NOTICES.md。

公开URL、真实模型验证、录屏及浏览器证据以最终交付记录为准；本README不宣称本地构建就是上线。
# 历史说明

本文记录旧实现。当前完成结果已改为[本机识别记录](../local-records.md)，不再自动到期，直到主动删除。

