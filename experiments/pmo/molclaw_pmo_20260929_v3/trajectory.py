"""Top-10 AUC on every actual submission; no unobserved tail."""
def complete_auc(rows, budget=1000):
    if len(rows) != budget:
        raise ValueError('Exactly 1000 recorded submissions required')
    seen = {}
    previous = 0.0
    area = 0.0
    curve = []
    for index, row in enumerate(rows, 1):
        if row['index'] != index:
            raise ValueError('Non-contiguous submission trajectory')
        if row['canonical'] and row['status'] != 'invalid':
            seen[row['canonical']] = row['score']
        top = sorted(seen.values(), reverse=True)[:10]
        current = sum(top) / len(top) if top else 0.0
        area += (previous + current) / 2
        curve.append({'submission': index, 'top10_mean': current})
        previous = current
    return area / budget, curve
