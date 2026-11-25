import csv
import io
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from app.business import DomainIssue
from app.intake.schema import HEADER
from app.monthly.service import compile_report
from app.review.service import execute, review


def batch(records):
    stream = io.StringIO(newline='')
    csv.writer(stream).writerows([HEADER, *records])
    return stream.getvalue().encode()


# 批次 A：1 号件第 5 天取走，2 号件观察到第 10 天未取
BASE = batch([
    ('A1', '0001', 'arrival', 1, 0, 0, 0, 0, '基础入柜'),
    ('A2', '0001', 'arrival', 2, 0, 0, 0, 0, '基础入柜'),
    ('A3', '0001', 'pickup', 1, 0, 5, 0, 0, '已取'),
    ('A4', '0001', 'observation', 0, 0, 10, 10, 5000, '观察窗'),
])
# 批次 B：补齐 2 号件，在前批观察结束后第 14 天取走
BACKFILL = batch([
    ('B1', '0001', 'arrival', 2, 0, 0, 0, 0, '补齐入柜'),
    ('B2', '0001', 'pickup', 2, 0, 14, 0, 0, '补齐取件'),
    ('B3', '0001', 'observation', 0, 0, 20, 14, 0, '观察窗'),
])
# 批次 C：1 号件取件时刻与批次 A 冲突
CLASH = batch([
    ('C1', '0001', 'arrival', 1, 0, 0, 0, 0, '冲突入柜'),
    ('C2', '0001', 'pickup', 1, 0, 7, 0, 0, '冲突取件'),
    ('C3', '0001', 'observation', 0, 0, 10, 7, 0, '观察窗'),
])
# 批次 D：1 号件入柜时刻与批次 A 冲突
ENTRY_CLASH = batch([
    ('D1', '0001', 'arrival', 1, 1, 0, 0, 0, '入柜冲突'),
    ('D2', '0001', 'pickup', 1, 0, 5, 0, 0, '取件'),
    ('D3', '0001', 'observation', 0, 0, 10, 4, 0, '观察窗'),
])
# 批次 E：1 号件在他批取件时刻之后仍记未取
LATE_CENSOR = batch([
    ('E1', '0001', 'arrival', 1, 0, 0, 0, 0, '入柜'),
    ('E2', '0001', 'observation', 0, 0, 8, 8, 10000, '观察窗'),
])
# 批次 F：2 号件观察窗更长，仍未取
LONGER = batch([
    ('F1', '0001', 'arrival', 2, 0, 0, 0, 0, '入柜'),
    ('F2', '0001', 'observation', 0, 0, 20, 20, 10000, '观察窗'),
])

LEGACY = {
    'manifest': {'created': '2026-10-01T00:00:00.000+00:00'},
    'balance': {'releasable': True},
    'cases': [{'case': '0001', 'records': ['old1'], 'status': 'READY',
               'measure': {'value': 5000, 'expected': 5000, 'unit': '基点',
                           'evidence': {'curve': [], 'horizon': 10}, 'flag': False}}],
    'intake': {},
}


def approved(store, data):
    run = execute(store, data)
    return review(store, run['id'], dict(revision=0, status='APPROVED', note='复核通过'))


def legacy_run(store):
    store.register('legacy-run', LEGACY)
    return review(store, 'legacy-run', dict(revision=0, status='APPROVED', note='旧批次留存'))


def merged_case(doc, code='0001'):
    return next(case for case in doc['report']['cases'] if case['case'] == code)


def test_merged_estimate_counts_shared_item_once_as_picked(store):
    approved(store, BASE)
    approved(store, BACKFILL)
    doc = compile_report(store, {'runs': [r['id'] for r in store.list()]})
    case = merged_case(doc)
    assert (case['items'], case['picked'], case['censored']) == (2, 2, 0)
    assert case['measure']['value'] == 0
    assert doc['report']['summary']['items'] == 2
    assert doc['report']['conflicts'] == []


def test_later_censoring_extends_observation(store):
    approved(store, BASE)
    approved(store, LONGER)
    doc = compile_report(store, {'runs': [r['id'] for r in store.list()]})
    case = merged_case(doc)
    assert (case['items'], case['picked'], case['censored']) == (2, 1, 1)
    assert case['measure']['value'] == 5000
    assert case['measure']['evidence']['horizon'] == 20


def test_conflicting_pickup_times_exclude_item_and_name_batches(store):
    first = approved(store, BASE)
    second = approved(store, CLASH)
    doc = compile_report(store, {'runs': [second['id'], first['id']]})
    case = merged_case(doc)
    assert (case['items'], case['picked'], case['censored']) == (1, 0, 1)
    conflicts = doc['report']['conflicts']
    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert conflict['reason'] == 'PICKUP_TIME_CONFLICT' and conflict['parcel'] == 1
    assert conflict['runs'] == sorted([first['id'], second['id']])
    assert conflict['exits'] == [5, 7]
    assert doc['report']['summary']['conflicts'] == 1


def test_conflicting_entry_times_exclude_item(store):
    approved(store, BASE)
    approved(store, ENTRY_CLASH)
    doc = compile_report(store, {'runs': [r['id'] for r in store.list()]})
    conflict = doc['report']['conflicts'][0]
    assert conflict['reason'] == 'ENTRY_CONFLICT' and conflict['entries'] == [0, 1]


def test_censoring_after_pickup_is_a_conflict(store):
    approved(store, BASE)
    approved(store, LATE_CENSOR)
    doc = compile_report(store, {'runs': [r['id'] for r in store.list()]})
    conflict = doc['report']['conflicts'][0]
    assert conflict['reason'] == 'CENSORED_AFTER_PICKUP'
    assert conflict['exits'] == [5] and conflict['cutoffs'] == [8]


def test_unsubstantiated_batches_are_listed_and_skipped(store):
    approved(store, BASE)
    legacy_run(store)
    doc = compile_report(store, {'runs': [r['id'] for r in store.list()]})
    report = doc['report']
    assert [item['run'] for item in report['unsubstantiated']] == ['legacy-run']
    assert report['summary']['unsubstantiated'] == 1 and report['summary']['substantiated'] == 1
    case = merged_case(doc)
    assert (case['items'], case['picked'], case['censored']) == (2, 1, 1)


def test_only_unsubstantiated_batches_yield_empty_estimate(store):
    legacy_run(store)
    doc = compile_report(store, {'runs': ['legacy-run']})
    report = doc['report']
    assert report['cases'] == [] and report['summary']['items'] == 0
    assert report['summary']['unsubstantiated'] == 1


def test_same_combination_does_not_create_new_report(store):
    approved(store, BASE)
    approved(store, BACKFILL)
    combo = [r['id'] for r in store.list()]
    first = compile_report(store, {'runs': combo})
    second = compile_report(store, {'runs': list(reversed(combo))})
    assert first == second and len(store.list_monthly()) == 1


def test_failed_compile_leaves_no_report(store):
    run = execute(store, BASE)
    with pytest.raises(DomainIssue, match='RUN_NOT_APPROVED'):
        compile_report(store, {'runs': [run['id']]})
    assert store.list_monthly() == []


def test_parallel_compile_commits_single_row(store):
    approved(store, BASE)
    approved(store, BACKFILL)
    combo = [r['id'] for r in store.list()]
    start = Barrier(4)

    def compile_():
        start.wait(3)
        return compile_report(store, {'runs': combo})

    with ThreadPoolExecutor(max_workers=4) as threads:
        results = list(threads.map(lambda _: compile_(), range(4)))
    assert all(result == results[0] for result in results)
    assert len(store.list_monthly()) == 1


def test_non_approved_batch_is_rejected(store):
    run = execute(store, BASE)
    review(store, run['id'], dict(revision=0, status='HELD', note='暂缓观察'))
    with pytest.raises(DomainIssue, match='RUN_NOT_APPROVED'):
        compile_report(store, {'runs': [run['id']]})


def test_unknown_batch_is_rejected(store):
    with pytest.raises(DomainIssue, match='RUN_NOT_FOUND'):
        compile_report(store, {'runs': ['missing']})


def test_monthly_fields_validation(store):
    for values in (None, {}, {'runs': []}, {'runs': ''}, {'runs': [None]}, {'runs': ['']}):
        with pytest.raises(DomainIssue, match='MONTHLY_FIELDS'):
            compile_report(store, values)


def post_run(client, data):
    response = client.post('/api/runs', data={'file': (io.BytesIO(data), 'batch.csv')})
    assert response.status_code == 200
    return response.json['id']


def approve(client, run_id):
    response = client.patch(f'/api/runs/{run_id}', json={'revision': 0, 'status': 'APPROVED', 'note': '复核通过'})
    assert response.status_code == 200


def test_http_monthly_flow(client):
    first, second = post_run(client, BASE), post_run(client, BACKFILL)
    approve(client, first)
    approve(client, second)
    created = client.post('/api/monthly', json={'runs': [first, second]})
    assert created.status_code == 200
    report = created.json['report']
    assert report['schema'] == 'monthly-report/1' and report['summary']['items'] == 2
    again = client.post('/api/monthly', json={'runs': [second, first]})
    assert again.status_code == 200 and again.json['id'] == created.json['id']
    assert len(client.get('/api/monthly').json['items']) == 1
    detail = client.get(f"/api/monthly/{created.json['id']}")
    assert detail.status_code == 200 and detail.json['report']['manifest']['runs'] == sorted([first, second])


def test_http_monthly_rejections(client):
    pending = post_run(client, BASE)
    assert client.get('/api/monthly/unknown').status_code == 404
    assert client.post('/api/monthly', json={'runs': ['unknown']}).status_code == 404
    held = client.post('/api/monthly', json={'runs': [pending]})
    assert held.status_code == 409 and held.json['code'] == 'RUN_NOT_APPROVED'
    assert client.post('/api/monthly', json={'runs': []}).status_code == 422
    assert client.post('/api/monthly').status_code == 422
    assert client.get('/api/monthly').json['items'] == []
