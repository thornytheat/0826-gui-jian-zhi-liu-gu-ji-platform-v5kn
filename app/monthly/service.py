from hashlib import sha256

from app.business import DomainIssue
from app.config import RULE_VERSION
from app.monthly.merge import merge_runs
from app.review.service import now


def compile_report(store, values):
    """出月报：同一批组合幂等，成稿一次性完整入库，中断恢复后重试不新增。"""
    if not isinstance(values, dict):
        raise DomainIssue('MONTHLY_FIELDS')
    run_ids = values.get('runs')
    if not isinstance(run_ids, list) or not run_ids or any(type(run_id) is not str or not run_id for run_id in run_ids):
        raise DomainIssue('MONTHLY_FIELDS')
    combo = sorted(set(run_ids))
    runs = []
    for run_id in combo:
        run = store.load(run_id)
        if run['status'] != 'APPROVED':
            raise DomainIssue('RUN_NOT_APPROVED')
        runs.append(run)
    monthly_id = sha256(f'{RULE_VERSION}:monthly:{"+".join(combo)}'.encode()).hexdigest()
    try:
        return store.load_monthly(monthly_id)
    except DomainIssue as error:
        if error.code != 'MONTHLY_NOT_FOUND':
            raise
    report = dict(schema='monthly-report/1',
                  manifest=dict(id=monthly_id, version=RULE_VERSION, created=now(), runs=combo),
                  **merge_runs(runs))
    return store.register_monthly(monthly_id, report)
