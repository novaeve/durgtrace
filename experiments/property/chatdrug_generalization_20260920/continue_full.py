import pathlib
p=pathlib.Path(__file__).resolve().parent/'full_experiment.py'
source=p.read_text()
old='if errors>=2:break'
new='if errors>=2 and r["status"]=="error" and r.get("error")!="OUTPUT_TRUNCATED":break'
assert source.count(old)==1
exec(compile(source.replace(old,new),str(p),'exec'),{'__name__':'__main__','__file__':str(p)})
