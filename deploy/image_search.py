#!/usr/bin/env python3
"""Keyless Bing image search -> validated, resized same-origin JPEGs; stdio MCP."""
import base64,hashlib,html,io,json,os,pathlib,re,sys,time,urllib.parse,warnings
from image_network import fetch,proxy_address
MAX_IMAGE=12*1024*1024

def query_tokens(query):
    """Words (2+ letters, not bare numbers) and CJK/kana/hangul bigrams used to judge whether a result matches."""
    out=set();text=query.lower()
    for run in re.findall('[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]+',text):
        out.update([run] if len(run)<3 else [run[i:i+2] for i in range(len(run)-1)])
    out.update(w for w in re.findall(r'[a-z0-9][a-z0-9\-\.]+',text) if not w.replace('.','').replace('-','').isdigit())
    return out
def relevant(entry,tokens):
    text=(entry.get('title','')+' '+urllib.parse.unquote(entry.get('source_url',''))+' '+urllib.parse.unquote(entry.get('original_url',''))).lower()
    return sum(t in text for t in tokens)>=min(2,len(tokens))
def bing(query,count,days,market,proxy):
    params={'q':query,'first':0,'count':max(count*4,30),'mmasync':1}
    if market:params.update(mkt=market,setlang=market.split('-')[0].replace('zh','zh-hans'))
    if days:params['qft']='+filterui:age-lt%d'%(days*1440)
    raw,_,_=fetch('https://www.bing.com/images/async?'+urllib.parse.urlencode(params),3*1024*1024,accept='text/html',proxy=proxy)
    seen=set();results=[]
    for match in re.finditer(r'\bm=["\'](.*?)["\']',raw.decode('utf-8','replace')):
        try:entry=json.loads(html.unescape(match.group(1)))
        except (ValueError,TypeError):continue
        url=entry.get('murl')
        if not isinstance(url,str) or not url.startswith(('https://','http://')) or url in seen:continue
        seen.add(url);results.append({'title':str(entry.get('t') or query)[:250],'original_url':url,'source_url':str(entry.get('purl') or '')[:4096]})
        if len(results)>=min(count*4,24):break
    return results
def candidates(query,count=4,days=None,market=None):
    """Bing sometimes answers datacenter IPs with results unrelated to the query (or none at all).
    Try the configured egress proxy first, then direct, judge each answer by how many results match the
    query's words, retry while it looks wrong, and only return results that match."""
    if not isinstance(query,str) or not query.strip() or len(query)>300:raise ValueError('query must contain 1–300 characters')
    if not isinstance(count,int) or isinstance(count,bool) or not 1<=count<=8:raise ValueError('count must be 1–8')
    if days is not None and days not in (1,7,30,365):raise ValueError('days must be 1,7,30,365')
    if market is not None and market not in ('ja-JP','zh-CN','en-US','ko-KR'):raise ValueError('Unsupported market')
    tokens=query_tokens(query);proxy=proxy_address()
    market=market or ('ja-JP' if re.search('[\u3040-\u30ff]',query) else 'zh-CN' if re.search('[\u4e00-\u9fff]',query) else 'ko-KR' if re.search('[\uac00-\ud7af]',query) else None)
    # Bing's answers for the same request vary from call to call (empty, unrelated, or good), and differ
    # with and without mkt. Ask up to eight times (proxy first), keep every result that matches the query,
    # and stop as soon as there are enough.
    base=[(proxy,market),(None,market),(proxy,None),(None,None)] if proxy else [(None,market),(None,None)]
    if not market:base=list(dict.fromkeys(base))
    attempts=(base*8)[:8];matched=[];seen=set();answered=False;error=None
    for i,(egress,mkt) in enumerate(attempts):
        if i:time.sleep(0.3)
        try:found=bing(query,count,days,mkt,egress);answered=True
        except Exception as e:error=e;continue
        for entry in found:
            if entry['original_url'] in seen or (tokens and not relevant(entry,tokens)):continue
            seen.add(entry['original_url']);matched.append(entry)
        if len(matched)>=max(count*2,6) or (not tokens and matched):break
    if not answered and error:raise error
    return matched

def google(query,count,days=None,engine='google'):
    """Fallback through the shared headless browser (imgbrowser.py); may ask for a human captcha."""
    import urllib.request
    port=os.environ.get('OPENCODE_IMGBROWSER_PORT','4098')
    request=urllib.request.Request('http://127.0.0.1:'+port+'/search',data=json.dumps({'query':query,'count':count,'days':days,'engine':engine}).encode(),headers={'Content-Type':'application/json'})
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=100) as response:return json.loads(response.read())
    except Exception:return {'status':'error'}

def store_image(url,directory,deny_host=None):
    from PIL import Image,ImageOps
    Image.MAX_IMAGE_PIXELS=25_000_000
    raw,mime,_=fetch(url,MAX_IMAGE,deny_host,accept='image/*')
    if mime not in ('image/jpeg','image/png','image/webp','image/gif','image/avif'):raise ValueError('Supported raster image required')
    with warnings.catch_warnings():
        warnings.simplefilter('error',Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(raw)) as opened:
            image=ImageOps.exif_transpose(opened);image.thumbnail((1280,1280))
            if image.mode in ('RGBA','LA') or 'transparency' in image.info:
                rgba=image.convert('RGBA');out=Image.new('RGB',rgba.size,'white');out.paste(rgba,mask=rgba.getchannel('A'));image=out
            else:image=image.convert('RGB')
            stream=io.BytesIO();image.save(stream,'JPEG',quality=82,optimize=True);encoded=stream.getvalue();size=image.size
    name=hashlib.sha256(encoded).hexdigest()+'.jpg';directory=pathlib.Path(directory);directory.mkdir(parents=True,exist_ok=True,mode=0o755);file=directory/name
    if not file.exists():
        if sum(p.stat().st_size for p in directory.glob('*.jpg'))+len(encoded)>1024**3:raise ValueError('Image cache full; preserving existing chat images')
        temp=directory/(name+'.'+str(os.getpid())+'.tmp')
        try:temp.write_bytes(encoded);temp.chmod(0o644);temp.replace(file)
        finally:
            if temp.exists():temp.unlink()
    return name,size

def search_images(query,count=4,days=None,market=None):
    origin=os.environ.get('OPENCODE_IMAGE_ORIGIN','').rstrip('/');parsed=urllib.parse.urlsplit(origin)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:raise ValueError('HTTPS image origin is not configured')
    directory=os.environ.get('OPENCODE_IMAGE_DIR','/var/lib/opencode-images');results=[];failures=0;deadline=time.monotonic()+80;captcha=False;provider='bing-images-keyless'
    def take(entries):
        nonlocal failures
        for entry in entries:
            if len(results)>=count or time.monotonic()>deadline:break
            if any(r['original_url']==entry['original_url'] for r in results):continue
            try:name,size=store_image(entry['original_url'],directory,parsed.hostname)
            except Exception:failures+=1;continue
            title=entry['title'].replace('[','(').replace(']',')').replace('\n',' ')
            entry.update(display_url=origin+'/chat-images/'+name,width=size[0],height=size[1],markdown='!['+title+']('+origin+'/chat-images/'+name+')');results.append(entry)
    # Priority: Google (browser) > Sogou > Yahoo > DuckDuckGo (browser) > keyless Bing (least reliable).
    tokens=query_tokens(query);used=[]
    for engine in ('google','sogou','yahoo','ddg'):
        if len(results)>=count or time.monotonic()>deadline-15:break
        if engine!='google' and days:continue
        g=google(query,count,days,engine)
        if g.get('status')=='captcha':captcha=True;continue
        if g.get('status')!='ok':continue
        extra=[e for e in g.get('results',[]) if isinstance(e,dict) and str(e.get('original_url','')).startswith(('https://','http://'))]
        extra=[{'title':str(e.get('title') or query)[:250],'original_url':e['original_url'],'source_url':str(e.get('source_url',''))[:4096]} for e in extra]
        if engine=='yahoo':
            # Yahoo tiles carry only the site's domain as text; label them with the query instead.
            for e in extra:
                if re.fullmatch(r'[\w.-]+\.[a-z]{2,}',e['title'].strip()):e['title']=query
        elif engine!='google' and tokens:extra=[e for e in extra if relevant(e,tokens)]
        before=len(results);take(extra)
        if len(results)>before:used.append(engine)
    if used:provider='+'.join(used)+'-images-browser'
    if len(results)<count:
        try:pool=candidates(query,count,days,market)
        except Exception:pool=[]
        if len(pool)<count and len(query.split())>2:
            try:pool+=[e for e in candidates(' '.join(query.split()[:2]),count,days,market) if all(e['original_url']!=p['original_url'] for p in pool)]
            except Exception:pass
        before=len(results);take(pool)
        if len(results)>before:provider='bing-images-keyless' if not used else provider+'+bing'
    note=None
    if captcha:note='Google 搜图被人机验证拦住了（结果若有则来自必应，质量较差）。请把这个链接发给用户：'+origin+'/imgcaptcha/ ，请用户在手机上打开完成验证后回复你，然后用同样参数重试本工具。不要自己绕过验证。'
    elif not results:note='No usable image found. Try another keyword/market/date range; do not invent URLs.'
    out={'provider':provider,'query':query,'images':results,'failed_downloads':failures,'instruction':'Choose relevant results and embed their markdown in your answer. Cite source_url. Do not substitute article OG thumbnails. Search returned images, not generated images. Never claim to have viewed image content unless a vision tool was used.','note':note}
    if captcha:out['captcha_url']=origin+'/imgcaptcha/'
    return out

TOOL={'name':'search_images','description':'Search actual images (Google Images via a shared headless browser; Sogou, Yahoo, DuckDuckGo, then keyless Bing as fallbacks), download/resize to same-origin JPEGs and return ready-to-embed Markdown. Use whenever the user asks for photos/pictures/images. No model calls/API key. For latest images set days=30 or 7, do not invent a year; use native names and market for foreign subjects.','inputSchema':{'type':'object','properties':{'query':{'type':'string','minLength':1,'maxLength':300},'count':{'type':'integer','minimum':1,'maximum':8,'default':4},'days':{'type':'integer','enum':[1,7,30,365]},'market':{'type':'string','enum':['ja-JP','zh-CN','en-US','ko-KR']}},'required':['query'],'additionalProperties':False}}
def handle(message):
    method=message.get('method');params=message.get('params') or {}
    if method=='initialize':return {'protocolVersion':params.get('protocolVersion','2024-11-05'),'capabilities':{'tools':{}},'serverInfo':{'name':'opencode-image-search','version':'1.0.0'}}
    if method=='ping':return {}
    if method=='tools/list':return {'tools':[TOOL]}
    if method=='tools/call':
        if params.get('name')!='search_images':raise ValueError('Unknown tool')
        try:
            result=search_images(**params.get('arguments',{}));content=[{'type':'text','text':json.dumps(result,ensure_ascii=False)}]
            directory=pathlib.Path(os.environ.get('OPENCODE_IMAGE_DIR','/var/lib/opencode-images'))
            for image in result['images']:
                name=urllib.parse.urlsplit(image['display_url']).path.rsplit('/',1)[-1]
                content.append({'type':'image','mimeType':'image/jpeg','data':base64.b64encode((directory/name).read_bytes()).decode('ascii')})
            return {'content':content,'isError':not result['images'] and not result.get('captcha_url')}
        except Exception as e:return {'content':[{'type':'text','text':'Image search failed: '+type(e).__name__+'. Try another query or source; never invent image URLs.'}],'isError':True}
    raise ValueError('Unknown method')
def main():
    for line in sys.stdin:
        try:
            if len(line)>65536:continue
            message=json.loads(line)
            if 'id' not in message:continue
            try:response={'jsonrpc':'2.0','id':message['id'],'result':handle(message)}
            except Exception:response={'jsonrpc':'2.0','id':message['id'],'error':{'code':-32601,'message':'Unsupported MCP request'}}
            print(json.dumps(response,ensure_ascii=False),flush=True)
        except (ValueError,TypeError):continue
if __name__=='__main__':main()
