# 历史场景预处理

本文件说明三个历史公开视频样例的离线生成，不是当前首页上传流程。真实图片/短视频上传使用[本地素材处理](local-media.md)，临时结果不会写入本文件描述的公开媒体目录。

视觉阶段在本地实际运行；公开网站只读取产生的轨迹和媒体，不启动 YOLO/PyTorch。轨迹中每条 sample 来自真实检测/跟踪输出，没有补写合成轨迹或在漏检期间插值。最短轨迹过滤为 3 个观测帧。

## 环境与复现

Python 3.12，CPU PyTorch 2.6.0 / torchvision 0.21.0，Ultralytics 8.3.231，YOLO11n，ByteTrack。全部传递依赖保存于 `vision/requirements.lock.txt`，权重有单独 SHA256 锁。下载与依赖安装需要网络；处理阶段不需要任何模型 API 密钥。

```powershell
python -m venv .venv-vision
.venv-vision/Scripts/python -m pip install -r vision/requirements.txt
python vision/download_sources.py
python vision/download_model.py
.venv-vision/Scripts/python vision/process.py --all
.venv-vision/Scripts/python evals/evaluate.py
```

下载模型脚本只访问官方 GitHub 公开制品，不使用其他项目的账号或文件。源视频留在忽略的 `work/video-sources/`，展示转码版输出到 `web/public/media/{scene}/`。数据 JSON 输出到 `data/scenes/`。重新处理前建议备份已有派生产物，以便比较。

## 处理和时间

输入解码后等比缩放至960像素宽，转为10fps CFR/H264/yuv420p、无音频、faststart。模型输入640，置信度0.25、NMS IoU0.5，CPU4线程。时间统一为展示片段的 `frame/fps`，不使用源文件的拍摄时间。每个场景重新初始化跟踪器，ID仅在该片段内有效。

证据在每0.5秒以及每条轨迹首尾保存真实画面。证据记录实际帧时间；查询返回最近可用证据时不能声称截图恰好拍在区域边界。标注视频为实际检测框、目标编号与固定画面区域，没有推断目标身份。

区域在画面坐标中定义，镜头平移时不等于地理围栏。驻留表示“在该画面区域内连续被观测的时间”，不代表静止。ByteTrack可保留短时丢失轨迹，但同ID恢复仍是跟踪假设。中断不自动证明遮挡；无法判定时保留不确定性。

## 处理自有视频

复制 `vision/custom.example.json`，根据有权使用的素材填写来源、许可和区域；只在本地运行：

```powershell
.venv-vision/Scripts/python vision/process.py --input my-video.mp4 --scene-id custom --config my-metadata.json
```

公开站不提供上传功能。请勿把公司的非公开视频、人员身份、账号或业务数据提交到公开仓库。

## 评测含义

`evals/annotations.json` 保存抽样帧的目视框标注、类别和评测ROI；标注由开发代理辅助完成，尚未独立人工复核，因此它是开发抽检，而非正式人工金标准测试集。`evals/evaluate.py` 将同帧跟踪输出与标注按相同类别和IoU≥0.5一对一匹配，产生真实的小样本框定位精确率/召回率。未运行全量mAP、IDF1、HOTA，不报告这些数字或未经对照的性能提升。

模型耗时是这台机器CPU上的真实本地处理记录，包括首次调用；不能当作线上模型问答延迟。夜间和远处小目标作为失败片段展示。数据集很小且选定了展示素材，不可推广为真实场景的准确率。
