from pathlib import Path
root=Path(__file__).parent
source=(root/'pocket_pdb_original.py').read_text(encoding='utf-8')
old='logp_to_rank_prob(np.array([p.average_logp[2:] for p in queue_tmp]), queue_weight)'
assert source.count(old)==1
source=source.replace(old,'logp_to_rank_prob([p.average_logp[2:] for p in queue_tmp], queue_weight)')
lines=[]
for line in source.splitlines():
    if line.lstrip().startswith('torch.save(pool,'):
        indent=line[:len(line)-len(line.lstrip())]
        lines.extend([indent+"if config.sample.get('save_snapshots', True):",'    '+line])
    else:lines.append(line)
(root/'pocket_runtime.py').write_text('\n'.join(lines)+'\n',encoding='utf-8')
