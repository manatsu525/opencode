"""Bounded public HTTP(S) only; DNS-pinned connections, no cookies/auth/proxy credentials."""
import http.client,ipaddress,socket,ssl,urllib.parse
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'
def target(url,deny_host=None):
    if any(ord(c)<32 for c in url) or len(url)>8192:raise ValueError('Invalid URL')
    p=urllib.parse.urlsplit(url)
    if p.scheme not in ('http','https') or not p.hostname or p.username or p.password:raise ValueError('Public HTTP(S) URL required')
    host=p.hostname.encode('idna').decode();port=p.port or (443 if p.scheme=='https' else 80)
    if port!=(443 if p.scheme=='https' else 80) or host==deny_host:raise ValueError('Nonstandard/own target')
    addresses={row[4][0] for row in socket.getaddrinfo(host,port,type=socket.SOCK_STREAM)}
    for ip in addresses:
        address=ipaddress.ip_address(ip);effective=getattr(address,'ipv4_mapped',None) or address
        if not effective.is_global or effective.is_multicast or any(address.version==6 and address in ipaddress.ip_network(net) for net in ('64:ff9b::/96','64:ff9b:1::/48','2002::/16','2001::/32')):raise ValueError('Private target')
    if not addresses:raise ValueError('No public target')
    if deny_host and addresses & {row[4][0] for row in socket.getaddrinfo(deny_host,port,type=socket.SOCK_STREAM)}:raise ValueError('Own target')
    return p,host,port,sorted(addresses,key=lambda value:(ipaddress.ip_address(value).version!=4,value))
def fetch(url,limit,deny_host=None,accept='*/*'):
    for _ in range(4):
        p,host,port,addresses=target(url,deny_host)
        class Pinned(http.client.HTTPConnection):
            def connect(self):
                last=None
                for ip in addresses:
                    raw=None
                    try:
                        raw=socket.create_connection((ip,port),8)
                        self.sock=ssl.create_default_context().wrap_socket(raw,server_hostname=host) if p.scheme=='https' else raw
                        return
                    except OSError as error:
                        last=error
                        if raw:raw.close()
                raise last or OSError('No reachable public address')
        c=Pinned(host,port,timeout=10)
        try:
            c.request('GET',urllib.parse.urlunsplit(('','',urllib.parse.quote(p.path or '/',safe="/%:@!$&'()*+,;=-._~"),urllib.parse.quote(p.query,safe="=&?/%:+;@,!$'()*-._~"),'')),headers={'User-Agent':UA,'Accept':accept,'Accept-Language':'zh-CN,zh;q=0.9,ja;q=0.8,en;q=0.7','Accept-Encoding':'identity','Connection':'close'})
            response=c.getresponse()
            if response.status in (301,302,303,307,308):url=urllib.parse.urljoin(url,response.getheader('Location',''));continue
            if response.status!=200:raise ValueError('Public source HTTP '+str(response.status))
            data=response.read(limit+1)
            if len(data)>limit:raise ValueError('Response too large')
            return data,response.getheader('Content-Type','').split(';')[0].lower(),url
        finally:c.close()
    raise ValueError('Too many redirects')
