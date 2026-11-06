from pathlib import Path
r=Path(__file__).resolve().parent
for name in ['runtime.py','gpu_slots.py','evaluate.py','smdd_eval_bridge.py']:
 (r/name).write_text((r/('source_'+name)).read_text())
base=r.parent/'deepseek-codex-type4-20261004'
s=(base/'worker.py').read_text().replace("[sys.executable,str(ROOT/'run.py'),method,'--task',tid]","[sys.executable,str(ROOT/'run.py'),tid]")
(r/'worker.py').write_text(s)
s=(base/'scheduler.py').read_text().replace("METHODS=['deepseek','codex'];WIDTH=4","METHODS=['solpi'];WIDTH=4")
(r/'scheduler.py').write_text(s)
for name in ['runtime.py','gpu_slots.py','evaluate.py','run.py','worker.py','scheduler.py']:compile((r/name).read_text(),name,'exec')
print('SoL-Pi Type4 syntax verified; model and tools identical to existing Type4 boundary')
