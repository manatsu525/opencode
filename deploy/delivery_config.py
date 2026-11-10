"""Global delivery rule: generated files are handed over as same-origin download links."""
import json,pathlib
RULE='/etc/opencode/DELIVERY.md'
def text(workspace):
    return f'''# 交付文件（全局必须遵守）

用户要的成品文件（代码、网页、文档、图片、压缩包等）必须保存在工作区 `{workspace}` 内（可用子目录）。若在其他目录（如 /tmp）生成，完成后复制到工作区。
最终回答必须为每个成品给出可点击的同源下载链接，格式：[下载 文件名](/files/download?path=相对工作区的路径)。路径相对 `{workspace}`，按 URL 编码（空格写 %20，中文等非 ASCII 字符用 UTF-8 百分号编码，子目录用 /），例如 `[下载 xiangqi.html](/files/download?path=xiangqi.html)`、`[下载 报告.pdf](/files/download?path=docs/%E6%8A%A5%E5%91%8A.pdf)`。多个文件时可先打包 zip 再给一个链接。用户也可在右侧“文件/工作区文件”面板浏览并下载任意工作区文件。
不要只回复服务器路径。未经用户明确同意，禁止把文件上传到任何第三方网盘/图床/粘贴站（如 0x0.st、catbox、gofile、transfer.sh 等），也禁止为交付文件另起 HTTP 服务、开放端口或使用隧道。
'''
def install(root,workspace='/var/lib/opencode/workspace'):
    root=pathlib.Path(root or '/');directory=root/'etc/opencode';file=directory/'opencode.json'
    config=json.loads(file.read_text()) if file.exists() else {}
    instructions=config.setdefault('instructions',[])
    if RULE not in instructions:instructions.append(RULE)
    mode=file.stat().st_mode & 0o777 if file.exists() else 0o644
    file.write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n');file.chmod(mode)
    (directory/'DELIVERY.md').write_text(text(workspace))
