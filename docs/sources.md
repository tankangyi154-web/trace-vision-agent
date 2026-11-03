# 素材、权重与许可

2026-11-03首页更换为白天多类别、真实夜间与交错行人三个Pexels视频。新素材的作者、原始链接、Pexels许可、处理方式和核对范围见[三个新示例](prepared-examples.md)，逐文件摘要在`data/presets/*.json`。下面的CC BY-SA说明仅适用于保留的历史场景。

本项目不使用原公司网页、账号、雷达、视频、代码或业务数据。下列文件均来自可公开复用的 Wikimedia Commons；来源页在 2026-10-31 核对。派生视频、截图继续按 **CC BY-SA 4.0** 提供，引用时请保留作者、来源链接、许可链接及改动说明。素材许可不代表作者认可本项目。

| 场景 | 原文件与作者 | 来源许可 | 本项目改动 |
| --- | --- | --- | --- |
| 水道里的船舶 | [Follow the waves.webm](https://commons.wikimedia.org/wiki/File:Follow_the_waves.webm)，Myousry6666 | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) | 移除音频、等比缩放、10fps重采样、H264编码；标注版增加真实检测框和片段内目标编号，统计区域由页面按需显示 |
| 城市道路的车流 | [Jalan Kuching traffic, Kuala Lumpur (240110).webm](https://commons.wikimedia.org/wiki/File:Jalan_Kuching_traffic,_Kuala_Lumpur_(240110).webm)，*angys* | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) | 同上 |
| 夜间交通的观测边界 | [Cars Passing by at Night.webm](https://commons.wikimedia.org/wiki/File:Cars_Passing_by_at_Night.webm)，Maximilian Schönherr | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) | 同上 |

原文件下载地址、字节数、SHA256 记录在 `vision/sources.lock.json`。打包的视频和 JSON 的源文件 SHA256 记录在各场景 `processing` 中。所谓“原始视频”指无检测叠层的展示转码版，不是摄像机原编码文件；没有修改场景内容或轨迹。

检测使用 Ultralytics 发布的 **YOLO11n COCO 预训练权重**，未重新训练。官方 [v8.3.0 权重制品](https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt) 的 SHA256、大小和版本固定在 `vision/model.lock.json`。框架与权重按官方 [AGPL-3.0 许可](https://github.com/ultralytics/ultralytics/blob/v8.3.231/LICENSE) 使用。本项目代码遵循主仓库声明；公开视频及其派生媒体保留自己的 CC BY-SA 4.0 许可。

跟踪使用 Ultralytics 8.3.231 集成的 ByteTrack，配置在 `vision/bytetrack.yaml`；方法原始论文：[ByteTrack: Multi-Object Tracking by Associating Every Detection Box](https://arxiv.org/abs/2110.06864)。本项目没有将开源检测器、跟踪器或基础模型称为个人原创。

个人实现范围包括：可复现的本地处理脚本、数据契约、画面区域与驻留规则、观测中断边界、事件/证据索引、确定性工具、规则检索、Agent预算和引用检查、前端体验、评测与部署整理。
