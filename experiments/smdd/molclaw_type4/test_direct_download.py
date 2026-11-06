import urllib.request,time,concurrent.futures,json
urls=['https://model-gateway.boltz.bio/boltz2_conf.ckpt','https://huggingface.co/boltz-community/boltz-2/resolve/main/boltz2_conf.ckpt']
def probe(url):
 start=time.monotonic()
 try:
  op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
  with op.open(urllib.request.Request(url,headers={'Range':'bytes=0-4194303'}),timeout=15) as r:
   data=r.read(4194304);seconds=time.monotonic()-start
   return {'url':url,'status':r.status,'bytes':len(data),'seconds':round(seconds,2),'mib_per_second':round(len(data)/1048576/seconds,2),'content_range':r.headers.get('Content-Range')}
 except Exception as e:return {'url':url,'error':type(e).__name__+': '+str(e)[:180],'seconds':round(time.monotonic()-start,2)}
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
 for result in ex.map(probe,urls):print(json.dumps(result),flush=True)
