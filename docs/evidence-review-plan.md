# 证据驱动视觉复核 · 当前实施计划

已获用户授权选择并实施唯一主线，替代 upgrade-proposal.md 中待选方案。基线提交 f44fc90 保留；仅本地，不发布、不购买服务。旧analyze正确的缺口处理保留，不包装成新修复。

目标演示：针对 harbor / T001 / 区域A / 12.3—13.1秒疑点窗口，模型查时序→选择局部原帧复检→读取真实结构化检测→程序复算并校验结论；可追问5秒/3秒。

1. [x] 固化case/data/model/config版本及时间事实；连续观测和物理连续结论分开。
2. [x] 有界review worker：原始10fps片段中124—130共7帧，固定ROI+YOLO11n复检，实际图/框/时刻/配置/关联门控保存。不得自动填未知帧。
3. [x] API本地作业状态+前后对照+结构化claim校验；真实Agent增加review_gap工具。缺Key可操作程序复核，但不伪装Agent。
4. [x] 单案例首屏：缺口、双时序、证据对照、实际工具状态、真实追问；旧工作台另一个入口保留。
5. [x] 验证新增边界、源帧/坐标/关联与真实Agent路径；真实DeepSeek三次问答及60.8秒连续操作录屏已保存。

验收事实、失败后修正和未验证范围见[evidence-review-validation.md](evidence-review-validation.md)。公网继续暂缓。

资源：现成CPU视觉环境work/vision-env、vision/weights/yolo11n.pt、harbor/original.mp4及本地SQLite。无需GPU/Upstash/部署账号。

复核结果无改善同样成立：保留真实结果和缺证据结论，不更换参数试到成功。ROI按12.3与13.1秒边界框并集加0.05归一化边距，clip至画面；固定imgsz=960，conf=.25，iou=.5，classes=[8]，device=cpu，最多7帧，不引入新权重。
关联是可复现的几何候选，不是身份识别。只选与两侧框合理重叠且在区域内的唯一候选；歧义不纳入。即使时序按容忍规则连通，也必须单独显示未复核帧和关联假设，不把它称作物理连续证明。
