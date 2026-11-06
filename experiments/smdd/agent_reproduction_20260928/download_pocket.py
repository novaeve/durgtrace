from html.parser import HTMLParser
from pathlib import Path
import requests

class Form(HTMLParser):
    def __init__(self):
        super().__init__()
        self.action = None
        self.params = {}
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'form': self.action = a.get('action')
        if tag == 'input' and 'name' in a: self.params[a['name']] = a.get('value','')

p=Path(__file__).parent/'pretrained_Pocket2Mol.pt'
f=Form()
f.feed(p.read_text(encoding='utf-8'))
r=requests.get(f.action,params=f.params,timeout=120)
r.raise_for_status()
assert len(r.content)==44921289, (len(r.content),r.headers.get('Content-Type'))
p.write_bytes(r.content)
print('Downloaded official Pocket2Mol checkpoint:',len(r.content))
