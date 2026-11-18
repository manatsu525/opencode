"""Global delivery rule: generated files are handed over as same-origin download links."""
import json,pathlib
RULE='/etc/opencode/DELIVERY.md'
def text(workspace):
    return f'''# 交付文件（全局必须遵守）

用户要的成品文件（代码、网页、文档、图片、压缩包等）必须保存在工作区内（可用子目录）。工作区就是本服务的启动目录，绝对路径在环境变量 `OPENCODE_WORKSPACE` 里（不确定时运行 `echo $OPENCODE_WORKSPACE`）；每个登录用户有自己的工作区。若在其他目录（如 /tmp）生成，完成后复制到工作区。
最终回答必须为每个成品给出可点击的同源下载链接，格式：[下载 文件名](/files/download?path=相对工作区的路径)。路径相对工作区根目录（`$OPENCODE_WORKSPACE`），按 URL 编码（空格写 %20，中文等非 ASCII 字符用 UTF-8 百分号编码，子目录用 /），例如 `[下载 xiangqi.html](/files/download?path=xiangqi.html)`、`[下载 报告.pdf](/files/download?path=docs/%E6%8A%A5%E5%91%8A.pdf)`。多个文件时可先打包 zip 再给一个链接。用户也可在右侧“文件/工作区文件”面板浏览并下载任意工作区文件。
不要只回复服务器路径。未经用户明确同意，禁止把文件上传到任何第三方网盘/图床/粘贴站（如 0x0.st、catbox、gofile、transfer.sh 等），也禁止为交付文件另起 HTTP 服务、开放端口或使用隧道。

# 大任务的做法
复杂或多步骤的任务：先用 todo 工具列出步骤，再逐步完成；把成品拆成多个文件，每完成一部分就写入文件并尽早运行测试或检查。不要在一次思考里构思完整个方案再一次性输出——单次回复有输出上限，长内容要分文件、分步写入。

# 保护宿主机（全局必须遵守）
本服务以 root 跑在用户唯一的云服务器上，机器一旦断网或卡死，只能去云控制台强制重启，所有服务一起中断。
- 禁止任何会改动宿主机网络的操作：容器/虚拟机一律不得使用 `--network host`/`--net=host`（尤其 redroid、Waydroid 等安卓环境，安卓 netd 会接管宿主路由和防火墙导致整机断网）；不得修改 iptables/nftables、路由表、ip rule、DNS、网卡、sshd、nginx、Cloudflare WARP 的配置。
- 确需安卓或其他容器环境时：用默认 bridge 网络加端口映射（如 `-p 127.0.0.1:5555:5555`），设内存上限（如 `--memory 3g`），不加 `--restart`；运行前先向用户说明方案。
- 安装系统级软件（如 apt install docker.io）、加载内核模块、停止或重启系统服务之前，先说明影响并征得用户同意。
- 本服务内存上限 4G：gradle/Java 等重任务要限制内存（如 `org.gradle.jvmargs=-Xmx1536m`、`--max-workers=2`），后台进程用完即停。
'''
def install(root,workspace='/var/lib/opencode/workspace'):
    root=pathlib.Path(root or '/');directory=root/'etc/opencode';file=directory/'opencode.json'
    config=json.loads(file.read_text()) if file.exists() else {}
    instructions=config.setdefault('instructions',[])
    if RULE not in instructions:instructions.append(RULE)
    mode=file.stat().st_mode & 0o777 if file.exists() else 0o644
    file.write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n');file.chmod(mode)
    (directory/'DELIVERY.md').write_text(text(workspace))
