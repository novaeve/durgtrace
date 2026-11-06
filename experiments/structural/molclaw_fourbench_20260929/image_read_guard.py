"""Reject corrupted local PNGs before Read puts them into a model request."""
import json
from pathlib import Path
import struct
import sys
import zlib

def validate_png(raw):
    if raw[:8] != b'\x89PNG\r\n\x1a\n':raise ValueError('invalid PNG signature')
    pos=8;compressed=[];types=[]
    while pos<len(raw):
        if pos+12>len(raw):raise ValueError('truncated PNG chunk')
        length=struct.unpack('>I',raw[pos:pos+4])[0]
        end=pos+12+length
        if end>len(raw):raise ValueError('truncated PNG data')
        kind=raw[pos+4:pos+8];data=raw[pos+8:pos+8+length]
        crc=struct.unpack('>I',raw[pos+8+length:end])[0]
        if crc != zlib.crc32(kind+data)&0xffffffff:raise ValueError('PNG checksum mismatch')
        if kind==b'IDAT':compressed.append(data)
        types.append(kind);pos=end
    if not types or types[0]!=b'IHDR' or types[-1]!=b'IEND':raise ValueError('incomplete PNG')
    zlib.decompress(b''.join(compressed))

def main():
    event=json.load(sys.stdin)
    if event.get('tool_name')!='Read':return
    p=Path(event.get('tool_input',{}).get('file_path',''))
    if not p.is_absolute():p=Path(event.get('cwd','.'))/p
    if not p.is_file():return
    raw=p.read_bytes()
    if p.suffix.lower()!='.png' and not raw.startswith(b'\x89PNG'):return
    try:validate_png(raw)
    except (ValueError,zlib.error,struct.error):
        print(json.dumps({'hookSpecificOutput':{'hookEventName':'PreToolUse','permissionDecision':'deny','permissionDecisionReason':'This PNG is corrupted (checksum or compressed data validation failed). It cannot be sent to the model API. Regenerate the image from the original SMILES with RDKit, or download the original image bytes directly; do not manually transcribe base64. You may also continue working directly with SMILES.'}}))

if __name__=='__main__':main()
