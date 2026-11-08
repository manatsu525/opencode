# 官方 OpenCode 后端 + 自定义移动端前端部署

后端固定为 anomalyco/opencode **v1.19.5 官方发布二进制**，不修改或编译后端源码。前端来自本 fork 的 `manatsu/v1.19.5`，包含 Mermaid/图片查看器及移动端修复。目标机无需安装 Bun、Node 或整个仓库。

## 范围与安全

- 完整安装面向 **Ubuntu/Debian + systemd**，ARM64、AMD64。自动识别架构；AMD64 默认选 baseline，避免 AVX2 假设。`OPENCODE_X64_VARIANT=standard` 可显式选择优化版。资产选择器也识别 musl，但完整安装器不支持 Alpine/OpenRC，不能将“能选 musl 资产”误认为支持所有发行版。
- `deploy/official-v1.19.5.sha256` 固定 GitHub 官方不可变发布资产的 SHA256 digest；本地提供的后端压缩包也必须匹配。前端压缩包必须显式给出可信 SHA256。
- **按部署者明确要求，官方后端以 root 运行、默认所有工具权限自动允许**（`permission` 的 `*` 及已知项全部 `allow`），包括 bash、编辑、联网、外部目录、doom_loop；这是可执行整台主机操作的高风险配置。保留内存/CPU 限额，但移除后端文件系统和权限沙箱。web / 登录 gate 分别用独立 `opencode-web`、`opencode-auth` 非特权用户；独立 nginx 进程/配置/PID/日志。**不修改主 nginx、octo、其配置、证书私钥或工作目录**。
- 后端仅监听 `127.0.0.1:4096`，由 HTTPS `:8558` 代理。HTML 显示移动端登录表单，成功签发 **一年**的 `__Host-opencode_session` Cookie（Secure/HttpOnly/SameSite=Lax/Path=/；服务端只保存随机令牌摘要及到期时间，不保存原始令牌或密码）。API 未登录 401；静态 assets、manifest、favicon 可公开读取。SSE/WebSocket 同样经过 Cookie gate，nginx 仅在服务端注入后端 Basic 头；后端仍启用同一用户名/密码。正确的 Basic 请求保留用于运维兼容；浏览器缓存的 Basic 在访问 HTML 后自动换 Cookie。官方 v1.19.5 支持 `OPENCODE_SERVER_USERNAME`，无需修改后端。
- **每次真正安装/重装都重新询问登录用户名/密码**；初次安装生成独立 **3650 天（约十年）** 自签名 IP/DNS 证书；重装时证书剩余不足 3285 天（约九年）会先备份旧证书/私钥，再重发 3650 天证书，否则保留原证书。provider.env、已有数据和配置的其他字段保留（权限默认覆盖为 allow）。不把秘密写入前端、命令行参数或输出。
- 服务默认工作区 `/var/lib/opencode/workspace`，不复用 octo 的 `/home/octo/workspace`。为保留已添加项目，root 后端仍使用 `HOME=/var/lib/opencode` 和原 XDG 路径，不迁移/重置数据库；没有 `ProtectHome` 限制。自定义工作区可以用现有目录；外部目录必须预先存在并授权，新安装器不会擅自 chown 其他应用的目录。
- `autoupdate:false` 和 `OPENCODE_DISABLE_AUTOUPDATE=1` 禁止自动升级。默认仅启用 `opencode-go`，不自动选择或虚构模型。
- 安装/验证只做版本、健康、目录、模型目录等非生成性检查，不发聊天请求、不消耗模型推理。

## 准备前端发布包

建议在本 fork 发布独立标签 **v1.19.5-manatsu.1**，上传：

- `opencode-web-v1.19.5-manatsu.1.tar.gz`
- `opencode-web-v1.19.5-manatsu.1.tar.gz.sha256`
- `opencode-deploy-v1.19.5-manatsu.1.tar.gz`（完整部署脚本，无需构建工具）
- `opencode-deploy-v1.19.5-manatsu.1.tar.gz.sha256`
- 中文发布说明 `RELEASE_NOTES.zh-CN.md`

默认安装器从 `https://github.com/manatsu525/opencode/releases/download/v1.19.5-manatsu.1/` 下载部署包、前端包和各自 SHA256，校验后执行/安装。此 release 已发布；后续更新需重新构建并同时替换上述四个包/校验文件，避免旧脚本与新前端混用。tar 根目录必须直接包含 `index.html`、`assets/`；`FRONTEND_BUILD.json` 记录前端源码 commit。每个新包的精确源码 SHA 以 `FRONTEND_BUILD.json` / `deploy/DEPLOY_BUILD.json` 为准。

自己构建时，在构建机（而不是生产 VM）使用仓库指定的 Bun 版本：

```sh
bun install --frozen-lockfile --ignore-scripts
# 只构建前端，绝不运行后端 build 脚本
env -u SENTRY_AUTH_TOKEN -u SENTRY_ORG -u SENTRY_PROJECT bun run --cwd packages/app build
tar -czf opencode-web-v1.19.5-manatsu.1.tar.gz -C packages/app/dist .
sha256sum opencode-web-v1.19.5-manatsu.1.tar.gz > opencode-web-v1.19.5-manatsu.1.tar.gz.sha256
```

不要打包 `.env`、真实 auth.json、密码或私钥。安装器固定发布标签，不盲目信任 latest；SHA256 防止传输损坏，来源真实性仍依赖受信 GitHub 账号/HTTPS，不能把同站下载的摘要当独立数字签名。

## 安装

发布准备完成后，在新 ARM64/AMD64 Ubuntu/Debian systemd 主机上直接运行（无需仓库、Bun 或 Node）：

```sh
curl -fsSL https://raw.githubusercontent.com/manatsu525/opencode/manatsu/v1.19.5/deploy/install.sh | sudo bash
```

若最小镜像缺少 curl/CA，先 `sudo apt-get update && sudo apt-get install -y curl ca-certificates`。管道入口会自动下载/校验固定 release 的完整 deploy 包，安全解压后运行其中的安装器；不从当前目录盲目 source 脚本。然后从 `/dev/tty` 询问公网 IP/域名（证书 SAN/访问地址）、用户名及两次隐藏密码。标准依赖缺失时通过 apt 安装。自动化可同时设置 `OPENCODE_WEB_HOST`、`OPENCODE_WEB_USER`、`OPENCODE_WEB_PASSWORD`，秘密不要写进命令参数/历史。

已有本地可信包或离线安装仍可显式指定（前端路径与 SHA256 必须同时提供）：

```sh
sudo bash deploy/install.sh --host YOUR_IP_OR_DOMAIN --frontend-archive /path/to/opencode-web-v1.19.5-manatsu.1.tar.gz --frontend-sha256 YOUR_64_HEX_SHA256
```

未指定本地前端时自动下载 release 中的预构建前端及 `.sha256` 并校验，不在目标机编译。`OPENCODE_RELEASE_BASE_URL` / `OPENCODE_BACKEND_BASE_URL` 仅供显式选择可信镜像/离线回归；默认分别是本 fork 固定 release 和官方 v1.19.5 release。官方二进制始终额外匹配仓库固定摘要。覆盖部署包镜像代表信任其可执行脚本，切勿用不可信镜像。

若 `opencode-ui-demo` 正在占用 8558，加 `--replace-demo`。只停止旧演示服务，保留其目录/fixtures/备份。安装器会验证新后端和 nginx 配置，再切换监听；切换失败会尝试恢复旧演示。

官方后端默认从 GitHub 下载。若目标机下载失败，可在已登录的构建机执行，然后 scp：

```sh
gh release download v1.19.5 --repo anomalyco/opencode   --pattern opencode-linux-arm64.tar.gz --dir ./release
# AMD64 默认使用 opencode-linux-x64-baseline.tar.gz
sudo bash deploy/install.sh ... --backend-archive /path/to/opencode-linux-arm64.tar.gz
```

`--port`、`--backend-port`、`--auth-port`（登录 gate 默认 loopback 4097） 可改非特权端口；拒绝占用 octo 使用的 8557/8088/8090。`--workspace` 可改为预先授权的目录。`--dry-run` 只显示计划，不收集密码、不更改安装。`DESTDIR=/tmp/test-root` 仅生成/测试安装文件，不修改真实用户、systemd 或防火墙，绝不是生产安装。

默认检查/复用已有 `opencode-ui-demo` 或 `opencode-web` 注释的同端口 iptables 规则，否则只添加一条带 `opencode-web` 注释的 TCP ACCEPT，并记录所有权。仅当 netfilter-persistent 正在使用时保存。`--no-firewall` 跳过；UFW、其他防火墙和 OCI 云安全列表仍由管理员确认。安装器不调用 OCI API。

首次访问自签名 HTTPS 会有证书警告。接受前请通过 SSH 比对公开证书指纹：

```sh
sudo openssl x509 -in /etc/opencode/tls/cert.pem -noout -fingerprint -sha256
```

证书固定默认 3650 天；余期不足约九年时，安装器会把旧证书和私钥保存在 `/opt/opencode/backups/tls-*` 的 root-only 目录再更换，其他证书/尤其 octo 不会被读取或覆盖。更换自签证书后手机可能需要重新接受信任警告。

正式域名可替换 `/etc/opencode/tls/cert.pem` 和 `key.pem` 为可信证书，再 reload `opencode-web`；注意之后重装也会按上述余期规则替换短期证书，使用外部证书管理时请自行备份并协调该行为。保留 root:opencode-web 所有权，私钥 0640、TLS 目录 0750。不要改变 octo 原证书的权限。

## 登录响应头与跨域检查

登录/退出 location 使用 `Referrer-Policy: same-origin`，避免浏览器表单 POST 在 no-referrer 下产生 `Origin: null` 导致 403；应用其他响应仍保持 no-referrer。登录 gate 不放宽 Origin 校验，null 和其他来源仍拒绝。

nginx 的 location 一旦定义任何 add_header 就不再继承 server 的整组 add_header，因此模板复用完整响应头集合：登录页仍包含 CSP、nosniff、DENY、no-store 与认证升级 Set-Cookie。其他 location 没有局部 add_header，正常继承。上游登录 handler 返回的真正 Set-Cookie 仍正常透传。

## 密码与 OpenCode Go

- 每次安装/重装都从 **`/dev/tty`** 询问用户名（回车默认 `admin`）、隐藏输入密码及再次确认。密码不能为空或全空白，确认不一致会重新询问；**不提供空密码沿用旧值**，避免误沿用旧登录。普通运行即使已安装也仍会询问。用户名限 1–64 位 ASCII 字母/数字或 `_ . @ -`，不能含 Basic auth 分隔符冒号；密码允许空格、引号、反斜杠、`$` 等可打印字符，但不能含换行/控制字符。env 文件采用兼容 Ubuntu 20.04 systemd 的字面转义，程序读取时会还原，勿把文件里的转义符误当成密码。
- 无 TTY 时必须同时提供非空 `OPENCODE_WEB_USER`、`OPENCODE_WEB_PASSWORD`，否则在下载/改动登录前明确失败。两个变量一起提供时是显式自动化模式，不询问；只提供一个或空值也会失败。不要把密码明文写进命令参数、脚本仓库或 shell 历史。可通过 CI 的秘密环境变量注入，交互式提前设置时可用：

```sh
export OPENCODE_WEB_USER=admin
IFS= read -r -s -p "Installation login password: " OPENCODE_WEB_PASSWORD < /dev/tty
printf '\n'
export OPENCODE_WEB_PASSWORD
sudo --preserve-env=OPENCODE_WEB_USER,OPENCODE_WEB_PASSWORD bash deploy/install.sh ...
unset OPENCODE_WEB_USER OPENCODE_WEB_PASSWORD
```

- 提问只读取 `/dev/tty`，不会读取脚本 stdin；支持无配套文件的 `curl | sudo bash`。入口自动下载完整部署包和校验文件，不需要预先下载 helpers。高级用法 `OPENCODE_DEPLOY_DIR` 可显式指定已校验的本地完整脚本目录。首装/重装管道提问均有 PTY 回归测试。

- Cookie 服务状态 `/var/lib/opencode-auth/sessions.json`（专用用户 0600）在服务重启、相同凭据重装后继续有效；改用户名/密码自动作废旧会话。`POST /logout` 可清除此浏览器会话。浏览器清理站点数据、无痕模式或平台主动清理 Cookie 会提前退出，服务端无法强行保证浏览器保留整年。
- 登录配置文件：`/etc/opencode/server.env`，root:root 0600。只通过受信 SSH/本机安全查看，勿粘贴到聊天或日志。不要把 API key 放在这个文件里。
- Go 提供方 ID：`opencode-go`，官方目录 URL 为 `https://opencode.ai/zen/go/v1`；其环境变量为 **OPENCODE_API_KEY**。
- 安装器不会发明、覆盖或复用其他应用的 key；**已有 provider.env 原样保留**。新安装自行填写 root-only 文件：

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
sudo systemctl status opencode opencode-web opencode-auth
sudo journalctl -u opencode -u opencode-web -u opencode-auth
sudo systemctl restart opencode
sudo systemctl reload opencode-web
sudo python3 deploy/verify.py --port 8558
```

backend：MemoryHigh 768M / MemoryMax 1536M / CPUQuota 150%；web：MemoryMax 128M / CPUQuota 50%；登录 gate：MemoryMax 96M。后端子进程共享额度。可用 systemd override 按真实任务调整；此限制不是模型上下文限制。数据/工作区在 `/var/lib/opencode`，缓存 `/var/cache/opencode`，前端/二进制 `/opt/opencode`。独立访问日志 `/var/lib/opencode-web/access.log` 只记录 URI，不记录 query 或 Authorization。

HTTPS 首次启用会换浏览器 origin，演示的本地设置/假会话不会迁移；实际后端是空白新状态。Mermaid/图片功能仍在前端；外链图片推荐 HTTPS，防盗链/混合内容失败时显示来源链接。

安装后脚本也保存在 `/opt/opencode/deploy/`；可以直接运行其中的 `uninstall.sh`，不依赖 `/tmp` 或仓库留在目标机。手动上传的 tar/脚本源目录不属于自动删除范围，确认不再使用后自行清理。

## 卸载与恢复旧演示

默认保留真实数据、工作区和密码供重装：

```sh
sudo bash deploy/uninstall.sh --yes
```

永久删除本部署的数据、缓存、Cookie 会话和凭据，并恢复原演示监听：

```sh
sudo bash deploy/uninstall.sh --yes --purge --restore-demo
```

`--purge` 会删除 `/var/lib/opencode` 内的会话和默认工作区，务必自行备份。不会删除外部工作区、octo、主 nginx、旧演示 `/opt/opencode-ui-demo`、复用的预存防火墙规则或其他共享 apt 包；只删除本安装器自己添加并记录的防火墙规则。旧演示原本未启用开机启动，恢复命令仅 start，不擅自改变其启动策略。

## 测试

```sh
(cd deploy && shellcheck -x install.sh uninstall.sh common.sh)
bash -n deploy/{common,install,uninstall}.sh
python3 deploy/test_auth.py
python3 deploy/test_nginx_headers.py
python3 deploy/test_release.py --frontend /path/to/frontend.tar.gz --backend /path/to/opencode-linux-x64-baseline.tar.gz
python3 deploy/test_credentials.py --frontend /path/to/frontend.tar.gz --backend /path/to/opencode-linux-x64-baseline.tar.gz
# 已安装 ARM/systemd 主机可加 --systemd 检查真实 EnvironmentFile 特殊字符/Unicode/末尾反斜杠解析（sudo 运行，后端和 octo 不重启）
python3 deploy/test_deploy.py --frontend /path/to/frontend.tar.gz   --backend /path/to/opencode-linux-x64-baseline.tar.gz --report /tmp/opencode-test.json
```

发布测试使用本机 HTTP fixture 镜像模拟尚未发布的 release，验证不带参数/无 helpers 的真实 `curl | bash` 默认下载链路、摘要损坏拒绝、临时文件清理，以及 3650 天证书/九年余期换证/私密备份。它不是公开 GitHub release 已上传的证明。

其他测试包含 PTY 隐藏输入、默认用户名、空密码/确认错误、无 TTY 明确失败、显式环境变量与特殊字符、真正的 `curl | bash` 首装/重装提问。另在临时 DESTDIR 中验证安装、重装、显式同凭据幂等、凭据更换且 provider/证书不变、备份、卸载/清空、架构选择和路径穿越拦截；AMD64 还实际启动官方 serve 二进制，验证带认证 health 和未认证 401，不发生成请求。它不是“完整 x86 systemd 安装测试”；生产 ARM64 VM 上另做真实 systemd/HTTPS/SSE 验证。


### 手机图片、上下文与设置

- 上下文圆环在窄屏可点击，弹出 token、上下文占比和费用，支持关闭；桌面保留官方行为。
- 两代设置窗口在 768px 以下使用全屏、顶部横向滚动标签、堆叠的标签/控件以及明确关闭按钮。
- 工具附件 FilePart、Markdown 图片、工具输出中的原图 URL 均复用安全的行内图片和缩放查看器。
- **websearch 可能只返回文章网址，不含图片。** 对明确的 `URL:` 搜索结果和 webfetch 输入网址，本部署额外读取公开网页 OpenGraph/Twitter 图片元数据，并明确标记“来源网页图片预览”；不是模型生成或模型实际返回的附件。无元数据/站点拒绝时不虚构图片，原来源链接仍可打开。前端独立接入其他未安装本 gate 的后端时不具备这一额外预览接口。
- `/image-preview` 只供已登录用户；仅标准 HTTP(S) 端口，拒绝凭据、私网/回环/链路本地/本机地址，DNS 解析后固定实际连接 IP，每次重定向重新校验，不转发 Cookie/Authorization；最多 512KiB HTML、4 个并发、128 条缓存。不改官方后端，不调用模型，不消耗模型生成配额。图片由浏览器直连公开原站，lazy/no-referrer，站点仍可能防盗链或失效。
- DOM 回归命令：`cd packages/app && bun test --conditions=browser --preload ./happydom.ts --preload ./test-browser/solid-dom-preload.ts ./test-browser/mobile-settings-context.test.ts ./test-browser/images-and-mobile-zoom.test.ts`。DOM 夹具不等同真实手机几何截图，仍需真实浏览器验证每个标签、圆环和图片。
