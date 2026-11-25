from app.business import DomainIssue, by_kind, prepared, single


def prepare(rows):
    window = single(rows,'observation')
    cutoff = window['exit']
    arrivals = by_kind(rows,'arrival')
    entry = {r['parcel']:r['entry'] for r in arrivals}
    if not entry or len(entry) != len(arrivals) or window['basis_points'] > 10_000 or any(t > cutoff for t in entry.values()):
        raise DomainIssue('INVALID_COHORT')
    exits = {}
    for row in by_kind(rows,'pickup'):
        key, time = row['parcel'],row['exit']
        if key not in entry or key in exits:
            raise DomainIssue('PICKUP_CONFLICT')
        if time < entry[key]:
            raise DomainIssue('PICKUP_BEFORE_ENTRY')
        exits[key] = time
    observations = [(min(exits.get(k,cutoff),cutoff)-t,exits.get(k,cutoff+1)<=cutoff) for k,t in entry.items()]
    return prepared(len(observations),{'cutoff':cutoff,'censored':sum(not picked for _,picked in observations)},(observations,window['observed'],window['basis_points']))
