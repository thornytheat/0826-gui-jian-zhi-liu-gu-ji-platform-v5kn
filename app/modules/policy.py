from app.business import decision


def policy(result):
    reason = 'HORIZON_UNOBSERVED' if result['flag'] else ('DWELL_RATE_MISMATCH' if result['value'] != result['expected'] else None)
    return decision(result,reason)
