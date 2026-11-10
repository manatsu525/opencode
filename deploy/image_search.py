#!/usr/bin/env python3
"""Keyless Bing image search -> validated, resized same-origin JPEGs; stdio MCP."""
import base64,hashlib,html,io,json,os,pathlib,re,sys,time,urllib.parse,warnings
from image_network import fetch
MAX_IMAGE=12*1024*1024

def candidates(query,count=4,days=None,market=None):
    if not isinstance(query,str) or not query.strip() or len(query)>300:raise ValueError('query must contain 1–300 characters')
    if not isinstance(count,int) or isinstance(count,bool) or not 1<=count<=8:raise ValueError('count must be 1–8')
    if days is not None and days not in (1,7,30,365):raise ValueError('days must be 1,7,30,365')
    if market is not None and market not in ('ja-JP','zh-CN','en-US','ko-KR'):raise ValueError('Unsupported market')
    market=market or ('ja-JP' if re.search('[\u3040-\u30ff]',query) else 'zh-CN' if re.search('[\u4e00-\u9fff]',query) else 'ko-KR' if re.search('[\uac00-\ud7af]',query) else 'en-US')
    params={'q':query,'first':0,'count':max(count*4,30),'mmasync':1,'mkt':market,'setlang':market.split('-')[0].replace('zh','zh-hans')}
    if days:params['qft']='+filterui:age-lt%d'%(days*1440)
    raw,_,_=fetch('https://www.bing.com/images/async?'+urllib.parse.urlencode(params),3*1024*1024,accept='text/html')
    seen=set();results=[]
    for match in re.finditer(r'\bm=["\'](.*?)["\']',raw.decode('utf-8','replace')):
        try:entry=json.loads(html.unescape(match.group(1)))
        except (ValueError,TypeError):continue
        url=entry.get('murl')
        if not isinstance(url,str) or not url.startswith(('https://','http://')) or url in seen:continue
        seen.add(url);results.append({'title':str(entry.get('t') or query)[:250],'original_url':url,'source_url':str(entry.get('purl') or '')[:4096]})
        if len(results)>=min(count*4,24):break
    return results

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
    directory=os.environ.get('OPENCODE_IMAGE_DIR','/var/lib/opencode-images');results=[];failures=0;deadline=time.monotonic()+80
    for entry in candidates(query,count,days,market):
        if time.monotonic()>deadline:break
        try:name,size=store_image(entry['original_url'],directory,parsed.hostname)
        except Exception:failures+=1;continue
        title=entry['title'].replace('[','(').replace(']',')').replace('\n',' ')
        entry.update(display_url=origin+'/chat-images/'+name,width=size[0],height=size[1],markdown='!['+title+']('+origin+'/chat-images/'+name+')');results.append(entry)
        if len(results)>=count:break
    return {'provider':'bing-images-keyless','query':query,'images':results,'failed_downloads':failures,'instruction':'Choose relevant results and embed their markdown in your answer. Cite source_url. Do not substitute article OG thumbnails. Search returned images, not generated images. Never claim to have viewed image content unless a vision tool was used.','note':None if results else 'No usable image found. Try another keyword/market/date range; do not invent URLs.'}

TOOL={'name':'search_images','description':'Search actual images with keyless Bing Images, download/resize to same-origin JPEGs and return ready-to-embed Markdown. Use whenever the user asks for photos/pictures/images. No model calls/API key. For latest images set days=30 or 7, do not invent a year; use native names and market for foreign subjects.','inputSchema':{'type':'object','properties':{'query':{'type':'string','minLength':1,'maxLength':300},'count':{'type':'integer','minimum':1,'maximum':8,'default':4},'days':{'type':'integer','enum':[1,7,30,365]},'market':{'type':'string','enum':['ja-JP','zh-CN','en-US','ko-KR']}},'required':['query'],'additionalProperties':False}}
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
            return {'content':content,'isError':not bool(result['images'])}
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
