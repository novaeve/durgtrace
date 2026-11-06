import base64,json,struct,zlib
from pathlib import Path
from image_read_guard import validate_png

def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
valid=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b'\0\xff\0\0'))+chunk(b'IEND',b'')
validate_png(valid)
for raw in [valid[:-4],valid[:45]+b'X'+valid[46:],b'not a png']:
    try:validate_png(raw)
    except (ValueError,zlib.error):pass
    else:raise AssertionError('Corruption was allowed')

root=Path(__file__).resolve().parent/'runs/full';count=0
names=['s2_MolEdit_AddComponent_0016','s2_MolEdit_AddComponent_0203','s2_MolEdit_AddComponent_0479','s2_MolEdit_DelComponent_0010']
def walk(x):
    global count
    if isinstance(x,dict):
        if x.get('type')=='image' and x.get('source',{}).get('data'):
            raw=base64.b64decode(x['source']['data'],validate=True)
            try:validate_png(raw)
            except (ValueError,zlib.error):count+=1
            else:raise AssertionError('Original broken image not detected')
        for v in x.values():walk(v)
    elif isinstance(x,list):
        for v in x:walk(v)
for name in names:
    for line in (root/name/'events.jsonl').read_text().splitlines():
        try:e=json.loads(line)
        except ValueError:continue
        walk(e)
assert count==4
print('PASS: valid PNG allowed; three synthetic corruptions and all four original corrupt images rejected')
