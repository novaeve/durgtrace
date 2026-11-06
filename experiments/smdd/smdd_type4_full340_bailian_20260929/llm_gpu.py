"""Single SSH request: credentials never leave their original GPU host."""
import json,pathlib,sys,time,urllib.request,urllib.error
def main():
 settings={}
 for line in pathlib.Path('/data2/chenfuxin/molingo_20260922/private/deepseek_canchen.env').read_text().splitlines():
  line=line.strip().removeprefix('export ')
  if '=' in line and not line.startswith('#'):
   k,v=line.split('=',1);settings[k.strip().lower()]=v.strip().strip('\"\'')
 body=json.load(sys.stdin);body['model']='deepseek-v4.1-flash';body['enable_thinking']=False
 key=settings['api_key'];base=settings['base_url'].rstrip('/')
 req=urllib.request.Request(base+'/chat/completions',json.dumps(body).encode(),{'Authorization':'Bearer '+key,'Content-Type':'application/json'})
 for i in range(4):
  try:
   with urllib.request.urlopen(req,timeout=240) as response:data=json.load(response)
   print(json.dumps(data));return
  except urllib.error.HTTPError as e:
   if e.code not in (429,500,502,503,504):raise RuntimeError('Bailian HTTP '+str(e.code)) from None
  except (TimeoutError,urllib.error.URLError):pass
  time.sleep(min(2**i*3,24))
 raise RuntimeError('Bailian request failed after 4 attempts')
if __name__=='__main__':main()
