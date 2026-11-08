"""Install supported global MCP + instructions; preserve other user config."""
import json,pathlib
INSTRUCTIONS='''# 图片搜索与行内展示（全局规则）

用户要求找图、搜图、照片、图片时，必须实际调用 image_search MCP 的 search_images 工具（模型端名称通常为 image_search_search_images），不能只调用普通 websearch 给文章链接，不能以来源网页 og:image 代替搜图。
工具使用无 Key 的必应图片搜索，自动下载、校验并将图片缩小到 1280px、JPEG 质量 82，返回本服务 HTTPS 的 display_url、原图和来源链接、可直接使用的 markdown。
挑选与用户需求相关的结果，在回答正文直接插入工具给出的 ![说明](display_url)；不要只给图片下载链接、不要改写/猜测 URL。按用户要求的张数展示，默认 2–4 张，并附来源页链接。图片可以点开缩放。
要“近期/最新”图片时传 days=30 或 7，不要自行添加年份；外国人物优先使用当地语言原名并设置 market（如 ja-JP）。工具失败可换关键词/市场/日期范围重试，仍无结果就如实说明，禁止伪造图片或声称已看过图片内容（除非实际调用了看图工具）。
该工具仅搜索公开图片，不生成图片，不会调用 OpenCode Go 或其他模型。

# 网页搜索失败回退（全局必须遵守）

普通网页搜索必须优先使用内置 websearch；不要禁用内置搜索，也不要在主搜索已有有效结果时重复搜索。
当内置 websearch 不可用、报错、超时、被限流或没有与问题相关的可用结果时，必须调用 keenable_search MCP 的 search_web_pages 工具（模型端名称通常为 keenable_search_search_web_pages）继续搜索，不要让用户换提问方式，不得伪造搜索结果或来源。
Keenable 是无 Key 的公开后备搜索；优先只取 3–5 条结果，按返回的真实来源链接回答。搜图仍必须使用上面的 image_search，不以网页搜索替代。不要把密码、密钥或其他私密数据放进搜索词。
Keenable 公共额度由出口 IP 共享：每小时 1000 次、每秒最多 10 次；429 时遵守 Retry-After，不连续重试或绕过限额。后备也不可用时如实说明，不声称搜索成功。
'''
def install(root,host,port):
    root=pathlib.Path(root or '/');directory=root/'etc/opencode';file=directory/'opencode.json';config=json.loads(file.read_text()) if file.exists() else {}
    config.setdefault('mcp',{})['image_search']={'type':'local','command':['/usr/bin/python3','/opt/opencode/deploy/image_search.py'],'enabled':True,'timeout':120000,'environment':{'OPENCODE_IMAGE_ORIGIN':'https://'+('['+host+']' if ':' in host else host)+':'+str(port),'OPENCODE_IMAGE_DIR':'/var/lib/opencode-images'}}
    config.setdefault('mcp',{})['keenable_search']={'type':'remote','url':'https://api.keenable.ai/mcp-public','enabled':True,'oauth':False,'timeout':60000,'headers':{'X-Keenable-Title':'opencode-manatsu'}}
    instructions=config.setdefault('instructions',[])
    if '/etc/opencode/IMAGE_SEARCH.md' not in instructions:instructions.append('/etc/opencode/IMAGE_SEARCH.md')
    mode=file.stat().st_mode & 0o777 if file.exists() else 0o644
    file.write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n');file.chmod(mode)
    (directory/'IMAGE_SEARCH.md').write_text(INSTRUCTIONS)
    (root/'var/lib/opencode-images').mkdir(parents=True,exist_ok=True,mode=0o755)
