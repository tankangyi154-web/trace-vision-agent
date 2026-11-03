# 浏览器上传与 Agent 体验部署包

本包准备好了带访问口令的完整网页入口，尚未部署到服务器。已验证云端访问隔离、浏览器问答身份和24小时清理的 Python 测试；本机没有 Docker，未完成 Linux 镜像构建、证书签发或服务器推理测速。不能把 Windows 本机成绩当成服务器性能。

建议先用 Linux x64、4核CPU、至少12GB主机内存、30GB可用磁盘做邀请体验；容器最多使用4核/8GB，识别任务由现有队列串行处理。该规格是部署起点，不是速度保证。内存更少或不同CPU需要另行调整与实测。首次构建需要联网下载锁定的CPU依赖和模型，校验失败会停止构建。

## 部署

1. 将域名解析到服务器，开放80/443端口。应用的8000端口不对外映射。
2. 安装 Docker Engine 与 Compose 2.24或更新版本，完整解压本包。
3. 在项目根目录执行（将域名换为自己的）：

```sh
python3 deploy/configure_cloud.py --domain trace.example.com
docker compose --env-file deploy/cloud.env -f deploy/compose.cloud.yaml up -d --build
docker compose --env-file deploy/cloud.env -f deploy/compose.cloud.yaml ps
```

访问 `https://trace.example.com`。用户名 `trace`，访问口令在仅本机保存的 `deploy/cloud.env` 内。把网址和访问口令发给受邀HR即可；对方无需下载安装。Caddy 根据域名自动配置 HTTPS，参见[官方说明](https://caddyserver.com/docs/automatic-https)。域名未正确解析或端口未开放时，不要绕过证书警告。

## 上传与问答

上传、真实检测和编号跟踪均在服务器运行。每个浏览器独立保存问答身份，不会让所有访问者共用同一个安装身份。供应商密钥继续保存在既有问答云服务中，本包不包含或要求填写供应商密钥。限额仍是全站每日100次、每月1000次，每个匿名浏览器身份总计10次；清理浏览器身份可重置个人身份，这不是实名账号额度。

服务器记录使用命名卷保存，完成记录保留24小时或由用户提前删除；本地Windows版仍保持手动删除前一直保存。云端界面会明确显示暂存服务器。已用暂存超过4GiB时拒绝新上传，正在运行的少量任务可能暂时超过此阈值；这不是精确磁盘硬配额。请定期检查磁盘空间。仅用于少量受邀体验，未做大规模公网并发验收。

本模板保留现有每文件200MB/2分钟限制和有限等待队列。长视频CPU检测可能超过视频本身时长。分享前应实际测试：三个案例、自己的图片/短视频、问答、两个浏览器记录隔离、刷新恢复、重启恢复、24小时清理和所选服务器内存峰值。没有通过时不应宣称已上线可用。

## 维护

```sh
docker compose --env-file deploy/cloud.env -f deploy/compose.cloud.yaml logs --tail 100 trace
docker compose --env-file deploy/cloud.env -f deploy/compose.cloud.yaml restart trace
docker compose --env-file deploy/cloud.env -f deploy/compose.cloud.yaml down
```

`down`保留卷；不要添加`-v`，否则记录和证书会删除。不要把 `cloud.env` 上传到 GitHub。不要直接对外发布旧的私有 `analysis` 端口。
