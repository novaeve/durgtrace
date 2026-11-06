from pathlib import Path
import subprocess,json
r=Path('/home/chenfuxin/smdd-migration/smdd-assets/experiments')
print('EXPERIMENTS',[p.name for p in r.iterdir() if any(x in p.name.lower() for x in ['type4','opus','claude','codex'])])
p=Path('/home/chenfuxin/smdd-migration/smdd-assets/smdd_native_mcp_server.py');print('MCP_SOURCE',p.read_text() if p.exists() else 'missing')
for name in ['harness','public','source']:
 p=r/'type4_full340_bailian_20260929'/name;print('ASSETS',str(p),[q.name for q in p.iterdir()] if p.exists() else None)
print('PARALLEL',(r/'type4_full340_bailian_20260929/parallel_status.json').read_text())
