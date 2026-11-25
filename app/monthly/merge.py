from collections import defaultdict

from app.modules.calculate import compute


def merge_runs(runs):
    """合并已签发批次的逐件证据，重算滞留估计。

    同件（同业务组同柜件）跨批去重：前批删失、他批在其观察结束后取走的按已取计一次；
    取件时刻互相冲突的件剔除并登记来源批次；只剩分组估计的批次列为缺证，不参与重算。
    """
    unsubstantiated = []
    claims = defaultdict(list)    # (case, parcel) -> [(run_id, item)]
    horizons = defaultdict(list)  # case -> [horizon]
    batches = defaultdict(set)    # case -> {run_id}
    for run in runs:
        cases = run['report'].get('cases', [])
        if not cases or any('items' not in case for case in cases):
            unsubstantiated.append({'run': run['id'], 'created': run['created']})
            continue
        for case in cases:
            code = case['case']
            batches[code].add(run['id'])
            horizon = (case.get('measure') or {}).get('evidence', {}).get('horizon')
            if horizon is not None:
                horizons[code].append(horizon)
            for item in case['items']:
                claims[(code, item['parcel'])].append((run['id'], item))
    conflicts = []
    observations = defaultdict(list)  # case -> [(age, picked)]
    for (code, parcel), entries in sorted(claims.items()):
        item_runs = sorted({run_id for run_id, _ in entries})
        entries_at = sorted({item['entry'] for _, item in entries})
        exits = sorted({item['exit'] for _, item in entries if item['exit'] is not None})
        cutoffs = sorted({item['cutoff'] for _, item in entries if item['exit'] is None})
        reason = None
        if len(entries_at) > 1:
            reason = 'ENTRY_CONFLICT'
        elif len(exits) > 1:
            reason = 'PICKUP_TIME_CONFLICT'
        elif exits and any(cutoff >= exits[0] for cutoff in cutoffs):
            reason = 'CENSORED_AFTER_PICKUP'
        if reason:
            conflicts.append(dict(case=code, parcel=parcel, reason=reason, runs=item_runs,
                                  entries=entries_at, exits=exits, cutoffs=cutoffs))
            continue
        entry = entries_at[0]
        if exits:
            observations[code].append((exits[0] - entry, True))
        else:
            observations[code].append((max(cutoffs) - entry, False))
    cases = []
    for code in sorted(observations):
        pooled = observations[code]
        horizon = max(horizons.get(code) or [age for age, _ in pooled])
        cases.append(dict(case=code, items=len(pooled),
                          picked=sum(1 for _, picked in pooled if picked),
                          censored=sum(1 for _, picked in pooled if not picked),
                          batches=sorted(batches[code]),
                          measure=compute((pooled, horizon, None))))
    summary = dict(batches=len(runs), substantiated=len(runs)-len(unsubstantiated),
                   unsubstantiated=len(unsubstantiated),
                   items=sum(case['items'] for case in cases),
                   picked=sum(case['picked'] for case in cases),
                   censored=sum(case['censored'] for case in cases),
                   conflicts=len(conflicts))
    return dict(cases=cases, conflicts=conflicts, unsubstantiated=unsubstantiated, summary=summary)
