当前分享版的轻量问答已通过Sites Worker独立部署，见[分享版服务](../docs/shared-agent.md)。下面的Docker模板仍只用于可选服务器部署，未在本机实际运行Docker。

# 部署文件（尚未部署）

当前交付以本地使用为主。本目录只提供可审查的部署入口，没有创建服务器、购买资源或发布公网地址。当前机器没有 Docker，以下容器构建与 Linux 运行尚未实测；Windows 便携版与离线案例包的实测结果见 `docs/local-delivery.md`。

## 公开案例服务

在安装了 Docker Engine / Compose 2.24.0或更新版本的主机，从项目根目录运行（可选`env_file`使用[官方required配置](https://docs.docker.com/reference/compose-file/services/#env_file)）：

```sh
docker compose build showcase
docker compose up -d showcase
curl http://127.0.0.1:8080/api/health
curl http://127.0.0.1:8080/api/presets
```

默认阶段为 `showcase`：提供前端、三个已完成案例、类别/编号筛选及证据回看。不开上传，不装检测环境，不配置模型密钥。主机仅绑定回环地址；以后需要发布时再配置域名、HTTPS反向代理与实际服务器预算。静态离线包也可单独托管。

## 私有 CPU 分析服务

```sh
cp deploy/server.env.example deploy/server.env
docker compose --profile analysis build analysis
docker compose --profile analysis up -d analysis
curl http://127.0.0.1:8081/api/health
```

首次构建会下载锁定依赖、模型并验证 SHA；CPU 图在本机短测通过且更快时才启用。启动再运行真实画面自检；未通过时仍可看三个案例，但禁用上传。未填写供应商密钥时仍可上传识别，新的自由问答关闭。模型费用由使用者自行配置的账号承担。

该入口只供本机、SSH 隧道或受控的私有网络使用。目前上传凭据属于持有者凭据，不具备完整的公网账号认证体系；**不要将 `analysis` 端口或反向代理直接开放到公网**。公开实时上传还需要账号认证、任务配额、对象存储、持久工作队列和实际并发压测，不能把改成 `0.0.0.0` 当作完成线上化。

记录与SQLite分别放在 `trace-records`、`trace-state` 命名卷；不要覆盖整个 `/app/work`，否则会遮住已安装的识别环境。删除容器不删除命名卷；`docker compose down -v` 会删除识别记录，备份前不要执行。

服务器健康接口不暴露私钥。`.dockerignore`排除本地密钥、工作目录和识别记录；`deploy/server.env`也被Git忽略。部署前需在实际Linux主机执行构建、健康检查、单文件识别、重启恢复、资源占用及访问隔离检查，不能将本地Windows成绩当作线上延迟承诺。

构建使用[Docker官方多阶段方式](https://docs.docker.com/build/building/multi-stage/)，前端构建工具不留在运行阶段。
