# 官方 OpenCode 后端 + 自定义移动端前端部署

后端固定为 anomalyco/opencode **v2.2.1 官方发布二进制**，不修改或编译后端源码。前端来自本 fork 的 `manatsu/v2.2.1`（官方 v2.2.1 web 应用 + 少量部署相关改动），目标机无需安装 Bun、Node 或整个仓库。

v2.2.1 相对 1.19.5 的部署要点：
- 官方 v2 web 应用原生带 Mermaid、图片预览（可缩放）、文件面板、会话删除、`/goal` 目标模式（输入框左侧显示目标状态）。本 fork 只补：会话列表“⋯”按钮（手机上也能删除/重命名/导出，确认框写明会话名，且**只删对话记录、不删工作区文件**）、“工作区文件”面板（浏览/下载/删除文件和文件夹）、用量面板去掉费用并显示“当前上下文 / 累计总 Token / 缓存命中率”、聊天图片限高（保持比例，点开可看原图）、Mermaid 点击放大、`/files/download` 链接保持为下载链接、停用离线 Service Worker（否则会绕过登录页且在手机上预下载整个前端）。
- 后端 API 全部在 `/api/*` 下；后端只接受固定用户名 `opencode`，登录 gate 对浏览器仍用你设置的用户名/密码，向后端注入 `opencode:<同一密码>` 的 Basic 头。
- **首次启动 v2 会就地、不可逆地迁移数据库**（`migration.v1-v2`），并把旧 `auth.json` 里的服务商凭据导入新的 credential 表。升级前务必完整备份（见下）。
- 单次输出上限：v2 用 `providers.<id>.models.<model>.limit.output` 配置（旧 `provider` 键里只写 limit 的覆盖会被迁移丢弃；`OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX` 在 2.2.1 代码中已不读取）。安装器为 `opencode-go/deepseek-v4.1-flash` 写入 131072（已有用户值不覆盖）；目录里更低的上限（如免费版 32000）仍然生效，v2 另有 256000 硬上限并按剩余上下文收缩。

## 范围与安全

- 完整安装面向 **Ubuntu/Debian + systemd**，ARM64、AMD64。自动识别架构；AMD64 默认选 baseline，避免 AVX2 假设。`OPENCODE_X64_VARIANT=standard` 可显式选择优化版。资产选择器也识别 musl，但完整安装器不支持 Alpine/OpenRC，不能将“能选 musl 资产”误认为支持所有发行版。
- `deploy/official-v2.2.1.sha256` 固定 GitHub 官方不可变发布资产的 SHA256 digest；本地提供的后端压缩包也必须匹配。前端压缩包必须显式给出可信 SHA256。
- **按部署者明确要求，官方后端以 root 运行、默认所有工具权限自动允许**（`permission` 的 `*` 及已知项全部 `allow`），包括 bash、编辑、联网、外部目录、doom_loop；这是可执行整台主机操作的高风险配置。保留内存/CPU 限额，但移除后端文件系统和权限沙箱。web / 登录 gate 分别用独立 `opencode-web`、`opencode-auth` 非特权用户；独立 nginx 进程/配置/PID/日志。**不修改主 nginx、octo、其配置、证书私钥或工作目录**。
- 后端仅监听 `127.0.0.1:4096`，由 HTTPS `:8558` 代理。HTML 显示移动端登录表单，成功签发 **一年**的 `__Host-opencode_session` Cookie（Secure/HttpOnly/SameSite=Lax/Path=/；服务端只保存随机令牌摘要及到期时间，不保存原始令牌或密码）。API 未登录 401；静态 `/assets/`、`/_assets/`、manifest、favicon 可公开读取；`/sw.js` 返回 404。SSE/WebSocket 同样经过 Cookie gate，nginx 仅在服务端注入后端 Basic 头；后端仍启用同一用户名/密码。正确的 Basic 请求保留用于运维兼容；浏览器缓存的 Basic 在访问 HTML 后自动换 Cookie。v2 后端读取 `OPENCODE_SERVER_PASSWORD`（兼容旧名），用户名固定为 `opencode`，无需修改后端。
- **每次真正安装/重装都重新询问登录用户名/密码**；初次安装生成独立 **3650 天（约十年）** 自签名 IP/DNS 证书；重装时证书剩余不足 3285 天（约九年）会先备份旧证书/私钥，再重发 3650 天证书，否则保留原证书。provider.env、已有数据和配置的其他字段保留（权限默认覆盖为 allow）。不把秘密写入前端、命令行参数或输出。
- 服务默认工作区 `/var/lib/opencode/workspace`，不复用 octo 的 `/home/octo/workspace`。为保留已添加项目，root 后端仍使用 `HOME=/var/lib/opencode` 和原 XDG 路径，不迁移/重置数据库；没有 `ProtectHome` 限制。自定义工作区可以用现有目录；外部目录必须预先存在并授权，新安装器不会擅自 chown 其他应用的目录。
- `autoupdate:false` 和 `OPENCODE_DISABLE_AUTOUPDATE=1` 禁止自动升级。不再限制只显示 `opencode-go`：在界面里添加的服务商（含自定义 OpenAI 兼容端点，如 Vercel AI Gateway）都会出现；旧版本写入的 `enabled_providers: ["opencode-go"]` 白名单会在重装时自动删除（其他自定义的 enabled/disabled 设置保持不变）。不自动选择或虚构模型。
- 安装/验证只做版本、健康、目录、模型目录等非生成性检查，不发聊天请求、不消耗模型推理。

## 准备前端发布包

建议在本 fork 发布独立标签 **v2.2.1-manatsu.4**，上传：

- `opencode-web-v2.2.1-manatsu.4.tar.gz`
- `opencode-web-v2.2.1-manatsu.4.tar.gz.sha256`
- `opencode-deploy-v2.2.1-manatsu.4.tar.gz`（完整部署脚本，无需构建工具）
- `opencode-deploy-v2.2.1-manatsu.4.tar.gz.sha256`
- 中文发布说明 `RELEASE_NOTES.zh-CN.md`

默认安装器从 `https://github.com/manatsu525/opencode/releases/download/v2.2.1-manatsu.4/` 下载部署包、前端包和各自 SHA256，校验后执行/安装。此 release 已发布；后续更新需重新构建并同时替换上述四个包/校验文件，避免旧脚本与新前端混用。tar 根目录必须直接包含 `index.html`、`_assets/`；`FRONTEND_BUILD.json` 记录前端源码 commit。每个新包的精确源码 SHA 以 `FRONTEND_BUILD.json` / `deploy/DEPLOY_BUILD.json` 为准。

自己构建时，在构建机（而不是生产 VM）使用仓库指定的 Bun 版本：

```sh
bun install --frozen-lockfile --ignore-scripts
# 只构建前端，绝不运行后端 build 脚本
env -u SENTRY_AUTH_TOKEN -u SENTRY_ORG -u SENTRY_PROJECT bun run --cwd packages/app build
# 发布包不含 source map、sw.js（nginx 对 /sw.js 返回 404）和 _headers
tar -czf opencode-web-v2.2.1-manatsu.4.tar.gz -C packages/app/dist --exclude='*.map' --exclude=./sw.js --exclude=./_headers .
sha256sum opencode-web-v2.2.1-manatsu.4.tar.gz > opencode-web-v2.2.1-manatsu.4.tar.gz.sha256
```

不要打包 `.env`、真实 auth.json、密码或私钥。安装器固定发布标签，不盲目信任 latest；SHA256 防止传输损坏，来源真实性仍依赖受信 GitHub 账号/HTTPS，不能把同站下载的摘要当独立数字签名。

## 安装

发布准备完成后，在新 ARM64/AMD64 Ubuntu/Debian systemd 主机上直接运行（无需仓库、Bun 或 Node）：

```sh
curl -fsSL https://raw.githubusercontent.com/manatsu525/opencode/manatsu/v2.2.1/deploy/install.sh | sudo bash
```

若最小镜像缺少 curl/CA，先 `sudo apt-get update && sudo apt-get install -y curl ca-certificates`。管道入口会自动下载/校验固定 release 的完整 deploy 包，安全解压后运行其中的安装器；不从当前目录盲目 source 脚本。然后从 `/dev/tty` 询问公网 IP/域名（证书 SAN/访问地址）、用户名及两次隐藏密码。标准依赖缺失时通过 apt 安装。自动化可同时设置 `OPENCODE_WEB_HOST`、`OPENCODE_WEB_USER`、`OPENCODE_WEB_PASSWORD`，秘密不要写进命令参数/历史。

已有本地可信包或离线安装仍可显式指定（前端路径与 SHA256 必须同时提供）：

```sh
sudo bash deploy/install.sh --host YOUR_IP_OR_DOMAIN --frontend-archive /path/to/opencode-web-v2.2.1-manatsu.4.tar.gz --frontend-sha256 YOUR_64_HEX_SHA256
```

未指定本地前端时自动下载 release 中的预构建前端及 `.sha256` 并校验，不在目标机编译。`OPENCODE_RELEASE_BASE_URL` / `OPENCODE_BACKEND_BASE_URL` 仅供显式选择可信镜像/离线回归；默认分别是本 fork 固定 release 和官方 v2.2.1 release。官方二进制始终额外匹配仓库固定摘要。覆盖部署包镜像代表信任其可执行脚本，切勿用不可信镜像。

若 `opencode-ui-demo` 正在占用 8558，加 `--replace-demo`。只停止旧演示服务，保留其目录/fixtures/备份。安装器会验证新后端和 nginx 配置，再切换监听；切换失败会尝试恢复旧演示。

官方后端默认从 GitHub 下载。若目标机下载失败，可在已登录的构建机执行，然后 scp：

```sh
gh release download v2.2.1 --repo anomalyco/opencode   --pattern opencode-linux-arm64.tar.gz --dir ./release
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

安装器会放一个独立的短命令 `/usr/local/bin/opencode-uninstall`（与 `deploy/uninstall.sh` 相同，不依赖 `/opt/opencode` 中的其他文件）。手动上传的 tar/脚本源目录不属于自动删除范围，确认不再使用后自行清理。

## 多用户

- 安装时设置的账号是**主账号**（管理员），继续使用原后端 `opencode.service`（4096）、原工作区 `/var/lib/opencode/workspace` 和原聊天记录。
- 管理员打开 `https://<主机>:8558/account`：新建用户（可设为管理员）、重置密码、设/取消管理员、删除用户。所有用户都可在此修改自己的密码和退出登录。主账号不能被别人改密码、降级或删除；不能删除自己。
- 每个其他用户一个独立后端 `opencode-user@<用户名>`（端口 4101 起），**工作目录**（`/var/lib/opencode/users/<用户名>/workspace`）和**聊天记录**（同目录下 data/state）互相独立，缓存也独立；其他一切共享：HOME（`/var/lib/opencode`）、全局配置/技能/MCP（`/etc/opencode`、`/var/lib/opencode/config`）、模型与 Go key、整个文件系统。右侧"工作区文件"面板和 `/files/download` 链接按登录用户解析到各自工作区。
- 共享意味着隔离只是方便而非安全边界：后端都以 root 运行、工具全部允许，任何用户的智能体都能读写整台机器（包括别人的工作区）。只给信任的人开账号。
- 原理：登录 gate（opencode-auth）保存用户（PBKDF2 哈希，`/var/lib/opencode-auth/users.json`），并写出 `instances.json`（用户名→端口）；root 的 `opencode-users-sync.path` 监视它，按需创建目录、`enable --now` 或停止对应后端。nginx 用 auth_request 返回的 `X-Opencode-Port` 把 `/api` 转发到该用户的后端。删除用户时后端停止，目录移到 `/var/lib/opencode/users-deleted/<用户名>-<时间>`（不立即删除，确认不要后手动清理）。
- 每个后端空闲约 150–450 MB 内存，上限同主后端（MemoryMax 1536M）。重装/升级会重启所有用户后端；卸载会一并删除。
- 同一浏览器切换账号后，前端可能记得上一个账号打开过的项目目录；建议不同用户用不同浏览器/设备。
- 旧版本的登录 Cookie 升级后自动归属主账号，无需重新登录。Basic 认证（API 客户端）只接受主账号的安装密码。

## 卸载（默认彻底删除）

任选其一，二者等价：

```sh
sudo opencode-uninstall
curl -fsSL https://raw.githubusercontent.com/manatsu525/opencode/manatsu/v2.2.1/deploy/uninstall.sh | sudo bash
```

终端只问一次 `确定要彻底卸载 OpenCode 吗？… [Y/n]`，直接回车即确认，输入 n 取消（不删除任何东西）。确认后删除：全部 systemd 服务/定时器（opencode、各用户的 opencode-user@*、opencode-users-sync、opencode-web、opencode-auth、opencode-image-cleanup）、`/opt/opencode`（二进制、前端、部署脚本、备份）、`/etc/opencode`（登录凭据、Go key、自签证书、独立 nginx 配置、MCP 与全局规则）、`/var/lib/opencode`（会话和默认工作区）、`/var/cache/opencode`、`/var/lib/opencode-auth`（Cookie 登录）、`/var/lib/opencode-images`（下载的图片）、`/var/lib/opencode-web`（独立 nginx 运行目录和访问日志）、系统用户/组 opencode、opencode-web、opencode-auth、本安装器添加并记录的防火墙规则，最后删除 `opencode-uninstall` 自身。**不可恢复，务必先自行备份会话/工作区。**

- 无交互终端（cron、CI、ssh 不带 -t）时脚本拒绝执行，需显式加 `--yes`：`curl -fsSL …/uninstall.sh | sudo bash -s -- --yes` 或 `sudo opencode-uninstall --yes`。
- 只想移除程序、保留数据/凭据/证书/配置以便重装：`sudo opencode-uninstall --keep-data`。之后要彻底清除再运行上面的 curl 命令。
- 旧参数 `--purge` 仍被接受（现在就是默认行为）；`--restore-demo` 会在卸载后启动旧演示服务（仅 start，不改启动策略）。
- 不会删除：外部工作区、octo、主 nginx 服务、旧演示 `/opt/opencode-ui-demo`、预先存在的防火墙规则、apt 安装的共享软件包（nginx、python3-pil 等），以及 systemd journal 中的共享历史日志。

## 工作区文件浏览、下载与删除

- 右侧面板可浏览**工作区全部文件**（`/var/lib/opencode/workspace`，含子目录、隐藏和 .gitignore 忽略的文件），不依赖 Git：手机端会话页“More...”→“工作区文件”；桌面端右侧面板标签栏的“+”→“打开工作区文件”（命令面板同名命令）。文件夹可逐级进入/返回，支持刷新，每个文件可单独下载；文件和文件夹右侧的垃圾桶可删除。
- 聊天中的同源链接 `/files/download?path=<相对工作区路径>`（如 `[下载 xiangqi.html](/files/download?path=xiangqi.html)`）点开直接下载，不跳转页面、不预览。全局规则 `/etc/opencode/DELIVERY.md` 要求智能体把成品放进工作区并给出这种链接，未经允许不得上传第三方网盘或另起服务。
- 接口由现有登录 sidecar（opencode-auth）提供，经 nginx：`GET /files/list?path=`（JSON）与 `GET/HEAD /files/download?path=`（原样字节流式传输，无大小上限，不改动/不裁剪内容）。必须已登录（Cookie 或 Basic），否则 401；nginx 先做 auth_request，sidecar 自身再校验一次。
- 删除：`POST /files/delete`（JSON `{"path","type"}`）是唯一的写操作；`GET /files/info?path=` 只统计（文件/子文件夹/链接数、总大小，超大目录计数封顶并标注）。确认框写明名称和递归范围（如“2 个文件、1 个子文件夹、1 个链接，共 9 B”）。要求：已登录、`Origin` 与站点完全一致（不可缺省）、自定义头 `X-OpenCode-Files: delete`、`Content-Type: application/json`、浏览器给出 `Sec-Fetch-Site` 时必须是 `same-origin`；GET 永不修改（`GET /files/delete` 返回 405）。不能删除工作区根目录；直接指定的目标是符号链接时拒绝；文件夹内的符号链接只解除链接本身、绝不跟随；全程基于目录 fd 的 `unlinkat`/`rmdir`，目标在确认后被换成其他类型/链接/其他 inode、或跨挂载点时中止（409/403）。
- 路径安全：只接受相对工作区路径；拒绝绝对路径、`..`、反斜杠、控制字符。从工作区根目录 fd 起逐级 `openat(..., O_NOFOLLOW)`，任何一级是符号链接都拒绝（含下载过程中把目录替换成链接的竞态）；最终 `fstat` 只允许普通文件，FIFO/设备/套接字被拒（`O_NONBLOCK` 防阻塞）。列表中符号链接/特殊文件显示但不可下载；单目录最多列 5000 项；非 UTF-8 文件名不显示。
- 响应头：`Content-Disposition: attachment`（ASCII 回退 + RFC 5987 `filename*` UTF-8）、`application/octet-stream`、`nosniff`、`no-store`、`CSP: sandbox`。
- 权限说明：后端以 root 运行，生成文件常为 root 0600，组/ACL 无法覆盖显式 0600 的文件，因此 sidecar 获授 **CAP_DAC_READ_SEARCH**（读/遍历）和用于删除的 **CAP_DAC_OVERRIDE**（不能改属主、setuid 或其他特权）。其可见范围用 systemd 挂载命名空间收窄：系统其余部分只读（ProtectSystem=strict），`/var` 和所有家目录换成空 tmpfs，只把工作区（可写，仅供删除）和 sidecar 自身状态目录绑定回来；`/etc/opencode`（凭据、Go key、证书私钥）、shadow、ssh、sudoers、`/opt/opencode/backups` 等不可访问。代码本身也只从工作区 fd 打开文件。
- 未实现：Range 断点续传、目录打包下载（可让智能体先打包 zip 再给链接）。

## 测试

```sh
(cd deploy && shellcheck -x install.sh uninstall.sh common.sh)
bash -n deploy/{common,install,uninstall}.sh
python3 deploy/test_auth.py
python3 deploy/test_nginx_headers.py
PYTHONPATH=deploy python3 -m unittest test_workspace_files   # 列表/下载/越界/符号链接/竞态/401
python3 deploy/test_release.py --frontend /path/to/frontend.tar.gz --backend /path/to/opencode-linux-x64-baseline.tar.gz
python3 deploy/test_credentials.py --frontend /path/to/frontend.tar.gz --backend /path/to/opencode-linux-x64-baseline.tar.gz
# 已安装 ARM/systemd 主机可加 --systemd 检查真实 EnvironmentFile 特殊字符/Unicode/末尾反斜杠解析（sudo 运行，后端和 octo 不重启）
python3 deploy/test_deploy.py --frontend /path/to/frontend.tar.gz   --backend /path/to/opencode-linux-x64-baseline.tar.gz --report /tmp/opencode-test.json
```

发布测试使用本机 HTTP fixture 镜像模拟尚未发布的 release，验证不带参数/无 helpers 的真实 `curl | bash` 默认下载链路、摘要损坏拒绝、临时文件清理，以及 3650 天证书/九年余期换证/私密备份。它不是公开 GitHub release 已上传的证明。

其他测试包含 PTY 隐藏输入、默认用户名、空密码/确认错误、无 TTY 明确失败、显式环境变量与特殊字符、真正的 `curl | bash` 首装/重装提问。另在临时 DESTDIR 中验证安装、重装、显式同凭据幂等、凭据更换且 provider/证书不变、备份、卸载/清空、架构选择和路径穿越拦截；AMD64 还实际启动官方 serve 二进制，验证带认证 health 和未认证 401，不发生成请求。它不是“完整 x86 systemd 安装测试”；生产 ARM64 VM 上另做真实 systemd/HTTPS/SSE 验证。


### 批量删除会话（v2.2.1-manatsu.3）

- 首页会话列表右上角新增“选择”：进入选择模式后每行出现复选框，点行切换选中而不是打开；底部工具栏显示“已选 N 项”、全选/取消全选、删除、取消，手机和桌面通用。选择模式下不弹行菜单、长按不触发。
- 删除前确认：“删除 N 个会话？只删除对话记录，不删除工作区文件。”，列出最多 5 个标题，超出显示“等 N 个”。
- 正在运行（或收件箱有待处理消息）的会话不会被删除：单个删除不会先停止运行中的会话，所以批量删除选择更安全的做法——跳过并在确认框里说明，删除后它们保持选中。全部选中项都在运行时只给出说明，不提供删除按钮。
- 逐个调用与单个删除相同的接口（并发 2），工具栏显示“正在删除 x/N…”；失败时提示“X 个删除失败”，失败项保持选中可重试；全部成功则退出选择模式。被删会话若已在标签页打开，按单个删除同样的方式关闭标签并离开。
- 测试：`cd packages/app && bun run test:browser`（含 `test-browser/home-session-batch-delete.test.tsx`、`home-session-selection.test.ts`）和 `bun run test:unit`（含 `src/home/sessions/batch-delete.test.ts`）。共享的 `packages/ui/test/solid-jsx.ts` 加了 `autoImportJSX`：Bun 1.4.4 不加时会漏掉 Solid hyperscript 的 jsx 导入，测试里渲染 TSX 组件会报 `jsx_… is not defined`。

### 手机图片、上下文与设置

- 上下文圆环在窄屏可点击，弹出 token、上下文占比和费用，支持关闭；桌面保留官方行为。
- 两代设置窗口在 768px 以下使用全屏、顶部横向滚动标签、堆叠的标签/控件以及明确关闭按钮。
- 工具结果只有两类会显示为行内图片：结构化图片附件（FilePart），以及 image_search 工具自己的输出。bash、webfetch、websearch 等原始输出（报错网页、日志、HTML）里出现的图片网址一律不自动出图——此前 lain.la 报错页里的 `sadlain.PNG` 被误显示即属此类。助手正文中明确写出的 Markdown 图片仍正常显示。
- 搜图按 octo 的实际方式实现：预装免 Key 的 **Bing Images MCP** + 全局“必须遵守”规则。自然图片请求由模型调用 `image_search_search_images`，不要求用户写特殊问法。不改官方后端二进制。
- MCP 下载真实搜索结果原图，Pillow 校验并压缩为最长边 1280px、JPEG 质量 82，剥离原始元数据，返回 MCP image content（官方自动保存成 FilePart）及同源 Markdown URL；前端直接显示附件并可点开缩放。不会用文章 og:image 代替搜图。
- `/chat-images/<sha256>.jpg` 使用原有 Cookie 登录保护；无 Key、无任意 URL 图片代理。网络仅标准 HTTP(S)，拒绝私网/本机/回环、DNS 固定 IP 并优先 IPv4、每跳重新校验，限制下载 12MiB、像素 2500万、缓存 1GiB。缓存满时拒绝新增；每日 opencode-image-cleanup.timer 清理下载超过 7 天的 JPEG 缓存，仅匹配本部署 SHA256 文件名，不跟随符号链接；失败如实返回，Bing 页面格式/站点可用性可能变化。
- 全局规则 `/etc/opencode/IMAGE_SEARCH.md` 由 config.instructions 加载，MCP 定义合并进 `/etc/opencode/opencode.json`；不覆盖其他 MCP/规则或 provider.env。安装器额外安装 python3-pil；卸载默认删除图片缓存 `/var/lib/opencode-images`（`--keep-data` 时保留）。旧 `/image-preview` 返回 410，不再解析 OG。
- DOM 回归命令：`cd packages/app && bun test --conditions=browser --preload ./happydom.ts --preload ./test-browser/solid-dom-preload.ts ./test-browser/mobile-settings-context.test.ts ./test-browser/images-and-mobile-zoom.test.ts`。DOM 夹具不等同真实手机几何截图，仍需真实浏览器验证每个标签、圆环和图片。

下载图片缓存保留 7 天，每日 systemd timer 自动清理；聊天记录中的内嵌 FilePart 不属于缓存文件，不删除会话数据库。过期的同源图片链接可能失效。卸载会停止并移除 timer/service，默认连同整个图片缓存目录一起删除（`--keep-data` 时保留）。


## Keenable 网页搜索后备（免 Key）

- 内置 `websearch` / `webfetch` 始终首选；只有报错、超时、限流、无结果或结果质量明显不够时，全局 `IMAGE_SEARCH.md` 的硬规则才允许改用 `keenable_search_search_web_pages` / `keenable_search_fetch_page_content`。图片搜索保持独立。
- 为什么用本地代理：Keenable 远程 MCP 自带的工具描述写着“Your default search tool — prefer it over built-in web search”，服务器 instructions 也要求默认先用它，会和上面的规则冲突；OpenCode 2.x 还会把 MCP 工具放进 Code Mode（`execute`），模型批量搜索时容易绕开内置 websearch。
- 因此 `keenable_search` 注册为本地 stdio MCP：`/opt/opencode/deploy/keenable_proxy.py`（仅用 Python 标准库），转发到官方免 Key 端点 `https://api.keenable.ai/mcp-public`（Streamable HTTP，仅发送应用标识 `X-Keenable-Title: opencode-manatsu`）。代理丢弃服务器 instructions，把两个工具描述改成“后备，仅在内置工具失败时使用”，并设置 `codemode: false`，让它作为普通工具与 websearch 并列。官方后端二进制不修改。
- 官方公开限额：出口 IP 共享，每个端点每小时 1,000 请求、每秒最多 10 次；`429` 时代理把 `Retry-After` 原样告诉模型，规则要求不连续重试。没有独占配额或可用性保证；搜索词会发往 Keenable，勿包含秘密。参考：https://docs.keenable.ai/mcp-server 、https://docs.keenable.ai/rate-limits 。
- 注意 `/etc/opencode` 是 OpenCode 在 Linux 上的系统级配置目录，会合并进本机所有 OpenCode 实例。
- 安装/重装幂等合并 MCP 与全局规则，保留其他 MCP、权限及 provider.env。卸载默认随 `/etc/opencode`、`/opt/opencode` 一并删除这些定义、规则和代理；`--keep-data` 时保留配置以供重装。代理由 OpenCode 按需拉起，无端口、无常驻服务、无清理定时器。
