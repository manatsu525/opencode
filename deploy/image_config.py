"""Install supported global MCP + instructions; preserve other user config."""
import json,pathlib
INSTRUCTIONS='''# 图片搜索与行内展示（全局规则）

用户要求找图、搜图、照片、图片时，必须实际调用 image_search MCP 的 search_images 工具（模型端名称通常为 image_search_search_images），不能只调用普通 websearch 给文章链接，不能以来源网页 og:image 代替搜图。
工具使用无 Key 的必应图片搜索，自动下载、校验并将图片缩小到 1280px、JPEG 质量 82，返回本服务 HTTPS 的 display_url、原图和来源链接、可直接使用的 markdown。
挑选与用户需求相关的结果，在回答正文直接插入工具给出的 ![说明](display_url)；不要只给图片下载链接、不要改写/猜测 URL。按用户要求的张数展示，默认 2–4 张，并附来源页链接。图片可以点开缩放。
要“近期/最新”图片时传 days=30 或 7，不要自行添加年份；外国人物优先使用当地语言原名并设置 market（如 ja-JP）。工具失败可换关键词/市场/日期范围重试，仍无结果就如实说明，禁止伪造图片或声称已看过图片内容（除非实际调用了看图工具）。
该工具仅搜索公开图片，不生成图片，不会调用 OpenCode Go 或其他模型。
'''
def install(root,host,port):
    root=pathlib.Path(root or '/');directory=root/'etc/opencode';file=directory/'opencode.json';config=json.loads(file.read_text()) if file.exists() else {}
    config.setdefault('mcp',{})['image_search']={'type':'local','command':['/usr/bin/python3','/opt/opencode/deploy/image_search.py'],'enabled':True,'timeout':120000,'environment':{'OPENCODE_IMAGE_ORIGIN':'https://'+('['+host+']' if ':' in host else host)+':'+str(port),'OPENCODE_IMAGE_DIR':'/var/lib/opencode-images'}}
    instructions=config.setdefault('instructions',[])
    if '/etc/opencode/IMAGE_SEARCH.md' not in instructions:instructions.append('/etc/opencode/IMAGE_SEARCH.md')
    mode=file.stat().st_mode & 0o777 if file.exists() else 0o644
    file.write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n');file.chmod(mode)
    (directory/'IMAGE_SEARCH.md').write_text(INSTRUCTIONS)
    (root/'var/lib/opencode-images').mkdir(parents=True,exist_ok=True,mode=0o755)
