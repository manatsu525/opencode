"""Bounded public-page OpenGraph previews. No model calls, cookies, auth or private networks."""
import collections,html.parser,http.client,ipaddress,socket,ssl,threading,time,urllib.parse
LIMIT=512*1024
slots=threading.BoundedSemaphore(4)
cache=collections.OrderedDict()
lock=threading.Lock()

def target(value, deny_host=None):
    parsed=urllib.parse.urlsplit(value)
    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or any(ord(c)<32 for c in value):raise ValueError('Invalid public URL')
    host=parsed.hostname.encode('idna').decode();port=parsed.port or (443 if parsed.scheme=='https' else 80)
    if port!=(443 if parsed.scheme=='https' else 80) or host==deny_host:raise ValueError('Nonstandard/own target')
    addresses={row[4][0] for row in socket.getaddrinfo(host,port,type=socket.SOCK_STREAM)}
    def public(ip):
        address=ipaddress.ip_address(ip);effective=getattr(address,'ipv4_mapped',None) or address
        return effective.is_global and not effective.is_multicast and not any(address.version==6 and address in ipaddress.ip_network(net) for net in ('64:ff9b::/96','64:ff9b:1::/48','2002::/16','2001::/32'))
    if not addresses or not all(public(ip) for ip in addresses):raise ValueError('Private target')
    if deny_host:
        own={row[4][0] for row in socket.getaddrinfo(deny_host,port,type=socket.SOCK_STREAM)}
        if addresses & own:raise ValueError('Own target')
    return parsed,host,port,sorted(addresses)[0]

class PageImages(html.parser.HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.preferred=[];self.fallback=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='meta' and (attrs.get('property') or attrs.get('name','')).lower() in ('og:image','og:image:url','twitter:image','twitter:image:src'):
            if attrs.get('content'):self.preferred.append(attrs['content'])
        if tag=='link' and attrs.get('rel')=='image_src' and attrs.get('href'):self.preferred.append(attrs['href'])
        if tag=='img':
            value=attrs.get('data-src') or attrs.get('src','')
            if value and not any(word in value.lower() for word in ('logo','icon','avatar','banner','emoji','spacer','blank','tracking')):
                if attrs.get('width','').isdigit() and int(attrs['width'])<160:return
                self.fallback.append(value)

def load_page(url,deny_host=None):
    for _ in range(4):
        parsed,host,port,ip=target(url,deny_host)
        class Pinned(http.client.HTTPConnection):
            def connect(self):
                self.sock=socket.create_connection((ip,port),8)
                if parsed.scheme=='https':self.sock=ssl.create_default_context().wrap_socket(self.sock,server_hostname=host)
        connection=Pinned(host,port,timeout=8)
        try:
            connection.request('GET',urllib.parse.urlunsplit(('', '', parsed.path or '/',parsed.query,'')),headers={'User-Agent':'Mozilla/5.0 (compatible; OpenCodeImagePreview/1.0)','Accept':'text/html,image/*;q=0.8','Accept-Encoding':'identity','Connection':'close'})
            response=connection.getresponse()
            if response.status in (301,302,303,307,308):url=urllib.parse.urljoin(url,response.getheader('Location',''));continue
            if response.status!=200:return []
            mime=response.getheader('Content-Type','').lower()
            if mime.startswith('image/'):return [url]
            if 'html' not in mime:return []
            body=response.read(LIMIT).decode('utf-8',errors='replace');parser=PageImages();parser.feed(body);result=[]
            for candidate in parser.preferred or parser.fallback:
                image=urllib.parse.urljoin(url,candidate)
                try:target(image,deny_host)
                except (ValueError,OSError):continue
                if image not in result:result.append(image)
                if len(result)>=2:break
            return result
        finally:connection.close()
    return []

def preview(url,deny_host=None):
    if len(url)>4096:return []
    with lock:
        item=cache.get(url)
        if item and item[0]>time.time():return item[1]
    if not slots.acquire(blocking=False):return []
    try:
        try:images=load_page(url,deny_host)
        except (ValueError,OSError,UnicodeError,http.client.HTTPException):images=[]
        with lock:
            cache[url]=(time.time()+(3600 if images else 120),images);cache.move_to_end(url)
            while len(cache)>128:cache.popitem(last=False)
        return images
    finally:slots.release()
