# 固定局部视觉复核 worker

该 worker 只接受绝对 `--output` 路径，且必须在项目 `work/` 子目录。模型、源视频、目标、帧窗口、ROI、阈值和类别不能由外部请求改变。完成结果不可覆盖；API 使用独立UUID作业目录。

```powershell
work/vision-env/Scripts/python.exe vision/review_gap.py --output C:\absolute\project\work\reviews\UUID
work/vision-env/Scripts/python.exe vision/validate_review.py --output C:\absolute\project\work\reviews\UUID
python -m unittest discover -s vision -p test_review_gap.py
```

固定案例：harbor / T001，原始10fps展示片段的124—130帧，共7帧（12.4—13.0秒）。检测前检查源视频和权重SHA256；基线JSON另存运行时SHA256。123与131帧的真实基线框并集向四边扩0.05，裁至画面；再按像素左上取floor、右下取ceil。结果同时记录归一化计划ROI、实际像素裁剪范围和有效ROI。裁剪归一化框用实际像素范围映回全图，避免把裁剪图坐标当全图坐标。

仅使用现有YOLO11n、CPU4线程、imgsz960、conf0.25、NMS IoU0.5、boat类别8。无网络、密钥、URL或自动下载路径；不降低阈值补救，不换模型，不按结果调参。逐帧解码确认原始帧位置，仅这7帧运行推理。每帧保留原图、ROI裁剪、全图框叠层和完整检测JSON；未通过门控和无检测的帧同样保留。模型打印转到stderr，stdout只输出实际阶段JSONL，另存`stages.jsonl`。全部完成后以同目录临时文件和原子重命名产生`result.json`。

每个候选要求：与123帧框及131帧框的IoU分别≥0.2、框中心在区域A内。对通过门控的候选按两侧IoU的较小者排序，前两名差小于0.1视为歧义而拒绝。接受观测标记`source=review, association=geometric_candidate`，不向原轨迹写入、不插值。输出中的接受是几何假设，不是同一目标身份或物理连续性证明。

首次实际运行保留在`work/initial-review/`：7帧都有检测，6帧通过门控，126帧未通过（与两侧框IoU约0.1604/0.0911）。接受帧为124、125、127、128、129、130。未解帧仍必须展示，不能只凭统计容忍规则能连通就声称缺口完全解决。本机含模型加载耗时约3.91秒，不代表跨机器或实时问答延迟。

定点校验不重新跑推理：固定源/模型/基线SHA、帧号和时间、逐帧原图及裁剪的相同JPEG重编码字节、全部检测门控复算、所接受观测引用、JSONL计数与结果汇总、原文件未变。单元测试覆盖实际裁剪偏移、两侧重叠、区外中心、近分候选歧义、空检测、固定真实源和输出路径约束。

## 浏览器兼容播放副本

`/media/harbor/playback.webm` 是独立的VP9无损播放副本，供浏览器兼容验证使用；原始取证源和worker输入仍是`original.mp4`。从原MP4直接编码，`libvpx-vp9 -lossless 1 -pix_fmt yuv420p -row-mt 1 -deadline good -cpu-used 4 -fps_mode passthrough`，未缩放、改fps或插帧，也未重跑视觉推理。副本保留169帧、10fps、16.9秒、960×540，大小36,085,689字节。使用同一本地OpenCV5.0.0逐帧解码BGR比较，169帧全部逐像素一致，最大通道差0；原/副本解码BGR拼接SHA256均为`0926c7c46182c980e5a3f7cc3c3fa69016af2fd587f47570d802765e1567faf5`。这项比较不承诺每种浏览器解码器输出相同。

源MP4 SHA256仍为`48acaf2024ca892a133c31b238742f8f76d6cef76188e33dc01904e15a600376`，副本SHA256为`e59b18b5844d94352245ca9a06a1c352112e9d523eb7bbba588964dd574c9289`。同目录`playback.json`记录编码、源/副本哈希、帧信息、逐像素检查与`for_evidence:false`。媒体仍按`/media/ATTRIBUTION.txt`中的CC BY-SA 4.0署名许可分发。是否解决具体Chrome播放问题由实际浏览器验证另行记录，不能用离线解码通过代替浏览器播放成功。
