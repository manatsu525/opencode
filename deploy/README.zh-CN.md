# 官方 OpenCode 后端 + 自定义移动端前端部署

后端固定为 anomalyco/opencode **v1.19.5 官方发布二进制**，不修改或编译后端源码。前端来自本 fork 的 `manatsu/v1.19.5`，包含 Mermaid/图片查看器及移动端修复。目标机无需安装 Bun、Node 或整个仓库。

## 范围与安全

- 完整安装面向 **Ubuntu/Debian + systemd**，ARM64、AMD64。自动识别架构；AMD64 默认选 baseline，避免 AVX2 假设。`OPENCODE_X64_VARIANT=standard` 可显式选择优化版。资产选择器也识别 musl，但完整安装器不支持 Alpine/OpenRC，不能将“能选 musl 资产”误认为支持所有发行版。
- `deploy/official-v1.19.5.sha256` 固定 GitHub 官方不可变发布资产的 SHA256 digest；本地提供的后端压缩包也必须匹配。前端压缩包必须显式给出可信 SHA256。
- 独立 `opencode`、`opencode-web` 系统用户；独立 nginx 进程/配置/PID/日志。**不修改主 nginx、octo、其配置、证书私钥或工作目录**。
- 后端仅监听 `127.0.0.1:4096`，由 HTTPS `:8558` 代理。所有前端和 API 请求要求 HTTP Basic 登录，后端本身也启用同一密码。用户名 `opencode`。
- 初次安装生成独立随机密码、自签名 IP/DNS 证书；重装保留密码、证书、provider.env、已有配置和数据。不把秘密写入前端、命令行参数或输出。
- 服务默认工作区 `/var/lib/opencode/workspace`，不复用 octo 的 `/home/octo/workspace`。`ProtectHome=true` 防止读取其他用户的 home。自定义工作区请用 `/srv/...` 等非 home 路径；外部目录必须预先存在并授权，新安装器不会擅自 chown 其他应用的目录。
- `autoupdate:false` 和 `OPENCODE_DISABLE_AUTOUPDATE=1` 禁止自动升级。默认仅启用 `opencode-go`，不自动选择或虚构模型。
- 安装/验证只做版本、健康、目录、模型目录等非生成性检查，不发聊天请求、不消耗模型推理。

## 准备前端发布包

建议在本 fork 发布独立标签 **v1.19.5-manatsu.1**，上传：

- `opencode-web-v1.19.5-manatsu.1.tar.gz`
- `opencode-web-v1.19.5-manatsu.1.tar.gz.sha256`

当前仅准备文件，尚未自动创建 release 或上传。tar 根目录必须直接包含 `index.html`、`assets/`；`FRONTEND_BUILD.json` 记录前端源码 commit。现有包的 UI 源码为 `e528c9f28f118aa87f77ff2a77cfb80c8d593196`。

自己构建时，在构建机（而不是生产 VM）使用仓库指定的 Bun 版本：

```sh
bun install --frozen-lockfile --ignore-scripts
# 只构建前端，绝不运行后端 build 脚本
env -u SENTRY_AUTH_TOKEN -u SENTRY_ORG -u SENTRY_PROJECT bun run --cwd packages/app build
tar -czf opencode-web-v1.19.5-manatsu.1.tar.gz -C packages/app/dist .
sha256sum opencode-web-v1.19.5-manatsu.1.tar.gz > opencode-web-v1.19.5-manatsu.1.tar.gz.sha256
```

不要打包 `.env`、真实 auth.json、密码或私钥。发布后可从本 fork 的 release 页面下载到目标机，再运行下列命令；安装器故意不使用尚未发布的 URL，也不盲目信任 latest。

## 安装

下载/校验前端后，将本目录脚本一并复制到目标机。把 SHA256 换成发布包的实际可信摘要：

```sh
sudo bash deploy/install.sh   --host YOUR_IP_OR_DOMAIN   --frontend-archive /path/to/opencode-web-v1.19.5-manatsu.1.tar.gz   --frontend-sha256 YOUR_64_HEX_SHA256
```

若 `opencode-ui-demo` 正在占用 8558，加 `--replace-demo`。只停止旧演示服务，保留其目录/fixtures/备份。安装器会验证新后端和 nginx 配置，再切换监听；切换失败会尝试恢复旧演示。

官方后端默认从 GitHub 下载。若目标机下载失败，可在已登录的构建机执行，然后 scp：

```sh
gh release download v1.19.5 --repo anomalyco/opencode   --pattern opencode-linux-arm64.tar.gz --dir ./release
# AMD64 默认使用 opencode-linux-x64-baseline.tar.gz
sudo bash deploy/install.sh ... --backend-archive /path/to/opencode-linux-arm64.tar.gz
```

`--port`、`--backend-port` 可改非特权端口；拒绝占用 octo 使用的 8557/8088/8090。`--workspace` 可改为预先授权的目录。`--dry-run` 只显示计划。`DESTDIR=/tmp/test-root` 仅生成/测试安装文件，不修改真实用户、systemd 或防火墙，绝不是生产安装。

默认检查/复用已有 `opencode-ui-demo` 或 `opencode-web` 注释的同端口 iptables 规则，否则只添加一条带 `opencode-web` 注释的 TCP ACCEPT，并记录所有权。仅当 netfilter-persistent 正在使用时保存。`--no-firewall` 跳过；UFW、其他防火墙和 OCI 云安全列表仍由管理员确认。安装器不调用 OCI API。

首次访问自签名 HTTPS 会有证书警告。接受前请通过 SSH 比对公开证书指纹：

```sh
sudo openssl x509 -in /etc/opencode/tls/cert.pem -noout -fingerprint -sha256
```

正式域名可替换 `/etc/opencode/tls/cert.pem` 和 `key.pem` 为可信证书，再 reload `opencode-web`；保留 root:opencode-web 所有权，私钥 0640、TLS 目录 0750。不要改变 octo 原证书的权限。

## 密码与 OpenCode Go

- 登录用户名：`opencode`。
- 随机登录密码文件：`/etc/opencode/server.env`，root:root 0600。只通过受信 SSH/本机安全查看，勿粘贴到聊天或日志。不要把 API key 放在这个文件里。
- Go 提供方 ID：`opencode-go`，官方目录 URL 为 `https://opencode.ai/zen/go/v1`；其环境变量为 **OPENCODE_API_KEY**。
- 目前没有用户 key，安装器不发明、不复用别的 key。填写 root-only 文件：

```sh
sudoedit /etc/opencode/provider.env
# 取消注释并填写一行：OPENCODE_API_KEY=<你的真实 OpenCode Go key>
sudo chmod 600 /etc/opencode/provider.env
sudo systemctl restart opencode.service
```

只用模型列表/官方连接页面验证，**不要让自动部署测试发送 prompt**。`provider` 列表“connected”表示发现凭据，不等同于远端验证 key 有效或余额足够。添加后在 UI 选择真实可用模型，不能把演示模型 ID 当作实际套餐承诺。

也可使用官方 UI/CLI 管理提供方认证。传统 Auth 文件默认是 `~/.local/share/opencode/auth.json`；本部署设置 XDG 后，对应 `/var/lib/opencode/data/opencode/auth.json`，不是 ubuntu 用户的文件。新接口可能通过官方 credential/integration 管理，**不要直接编辑 SQLite**；推荐上述环境文件，避免依赖内部存储格式。只有后台用户应读取自己的认证数据。

## 服务、资源与日志

```sh
sudo systemctl status opencode opencode-web
sudo journalctl -u opencode -u opencode-web
sudo systemctl restart opencode
sudo systemctl reload opencode-web
sudo python3 deploy/verify.py --port 8558
```

backend：MemoryHigh 768M / MemoryMax 1536M / CPUQuota 150%；web：MemoryMax 128M / CPUQuota 50%。后端子进程共享额度。可用 systemd override 按真实任务调整；此限制不是模型上下文限制。数据/工作区在 `/var/lib/opencode`，缓存 `/var/cache/opencode`，前端/二进制 `/opt/opencode`。独立访问日志 `/var/lib/opencode-web/access.log` 只记录 URI，不记录 query 或 Authorization。

HTTPS 首次启用会换浏览器 origin，演示的本地设置/假会话不会迁移；实际后端是空白新状态。Mermaid/图片功能仍在前端；外链图片推荐 HTTPS，防盗链/混合内容失败时显示来源链接。

安装后脚本也保存在 `/opt/opencode/deploy/`；可以直接运行其中的 `uninstall.sh`，不依赖 `/tmp` 或仓库留在目标机。手动上传的 tar/脚本源目录不属于自动删除范围，确认不再使用后自行清理。

## 卸载与恢复旧演示

默认保留真实数据、工作区和密码供重装：

```sh
sudo bash deploy/uninstall.sh --yes
```

永久删除本部署的数据、缓存和凭据，并恢复原演示监听：

```sh
sudo bash deploy/uninstall.sh --yes --purge --restore-demo
```

`--purge` 会删除 `/var/lib/opencode` 内的会话和默认工作区，务必自行备份。不会删除外部工作区、octo、主 nginx、旧演示 `/opt/opencode-ui-demo`、复用的预存防火墙规则或其他共享 apt 包；只删除本安装器自己添加并记录的防火墙规则。旧演示原本未启用开机启动，恢复命令仅 start，不擅自改变其启动策略。

## 测试

```sh
(cd deploy && shellcheck -x install.sh uninstall.sh common.sh)
bash -n deploy/{common,install,uninstall}.sh
python3 deploy/test_deploy.py --frontend /path/to/frontend.tar.gz   --backend /path/to/opencode-linux-x64-baseline.tar.gz --report /tmp/opencode-test.json
```

测试只在临时 DESTDIR 中验证安装、重装、密码/证书不变、备份、卸载/清空、架构选择和路径穿越拦截；AMD64 还实际启动官方 serve 二进制，验证带认证 health 和未认证 401，不发生成请求。它不是“完整 x86 systemd 安装测试”；生产 ARM64 VM 上另做真实 systemd/HTTPS/SSE 验证。
