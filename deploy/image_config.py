"""Install supported global MCP + instructions; preserve other user config."""
import json,pathlib
INSTRUCTIONS='''# 图片搜索与行内展示（全局规则）

用户要求找图、搜图、照片、图片时，必须实际调用 image_search MCP 的 search_images 工具（模型端名称通常为 image_search_search_images），不能只调用普通 websearch 给文章链接，不能以来源网页 og:image 代替搜图。
工具使用无 Key 的必应图片搜索，自动下载、校验并将图片缩小到 1280px、JPEG 质量 82，返回本服务 HTTPS 的 display_url、原图和来源链接、可直接使用的 markdown。
挑选与用户需求相关的结果，在回答正文直接插入工具给出的 ![说明](display_url)；不要只给图片下载链接、不要改写/猜测 URL。按用户要求的张数展示，默认 2–4 张，并附来源页链接。图片可以点开缩放。
要“近期/最新”图片时传 days=30 或 7，不要自行添加年份；外国人物优先使用当地语言原名并设置 market（如 ja-JP）。工具失败可换关键词/市场/日期范围重试，仍无结果就如实说明，禁止伪造图片或声称已看过图片内容（除非实际调用了看图工具）。
该工具仅搜索公开图片，不生成图片，不会调用 OpenCode Go 或其他模型。

# 网页搜索顺序（全局必须遵守）

每次需要上网查资料，第一步必须直接调用内置 `websearch` 工具，哪怕要查好几条，也逐条或并列直接调用 `websearch`。禁止一开始就用 keenable_search，也禁止用 `execute` 去批量调用 keenable。不要禁用内置搜索，也不要在主搜索已有有效结果时重复搜索。
只有本轮 `websearch` 出现以下情况，才改用 keenable_search 的 `search_web_pages`（工具名通常为 keenable_search_search_web_pages）补搜：报错、超时、被限流、返回“No search results found”，或结果明显不相关、过旧、太少，不足以回答。改用时在回答里不必解释，但不得伪造结果或来源。
读取网页正文优先用内置 `webfetch`；webfetch 失败或被拦时，才用 keenable_search 的 `fetch_page_content`。
Keenable 是无 Key 的公开后备搜索：每次取 3–5 条结果即可；公共额度按出口 IP 共享（每小时 1000 次、每秒最多 10 次），遇到 429 遵守 Retry-After，不连续重试或绕过限额。后备也不可用时如实说明。搜图仍必须用上面的 image_search。不要把密码、密钥或其他私密数据放进搜索词。
'''
def install(root,host,port):
    root=pathlib.Path(root or '/');directory=root/'etc/opencode';file=directory/'opencode.json';config=json.loads(file.read_text()) if file.exists() else {}
    config.setdefault('mcp',{})['image_search']={'type':'local','command':['/usr/bin/python3','/opt/opencode/deploy/image_search.py'],'enabled':True,'timeout':120000,'environment':{'OPENCODE_IMAGE_ORIGIN':'https://'+('['+host+']' if ':' in host else host)+':'+str(port),'OPENCODE_IMAGE_DIR':'/var/lib/opencode-images'}}
    # Local stdio proxy to Keenable's keyless /mcp-public: drops the server's "use me first" instructions,
    # marks its tools as fallback, and stays out of Code Mode so it is a normal tool beside websearch.
    config.setdefault('mcp',{})['keenable_search']={'type':'local','command':['/usr/bin/python3','/opt/opencode/deploy/keenable_proxy.py'],'enabled':True,'codemode':False,'timeout':60000,'environment':{'KEENABLE_TITLE':'opencode-manatsu'}}
    instructions=config.setdefault('instructions',[])
    if '/etc/opencode/IMAGE_SEARCH.md' not in instructions:instructions.append('/etc/opencode/IMAGE_SEARCH.md')
    mode=file.stat().st_mode & 0o777 if file.exists() else 0o644
    file.write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n');file.chmod(mode)
    (directory/'IMAGE_SEARCH.md').write_text(INSTRUCTIONS)
    (root/'var/lib/opencode-images').mkdir(parents=True,exist_ok=True,mode=0o755)
