"""Sabotage check: shows the v3 fixtures and boundary tests can FAIL. Each variant re-introduces one reviewed flaw by monkeypatching
account_proof, then reports which frozen-fixture cases change. A variant that changes nothing would mean the fixtures prove nothing.
  python3 scripts/sabotage_account_proof.py"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "code"))
from ghostaudit import account_proof as ap  # noqa: E402
from ghostaudit import run as runner  # noqa: E402

FX = os.path.join(REPO, "code", "evaluation", "fixtures", "synth_v3")


def statuses():
    _, _, res = runner.run_dataset(FX)
    return {r.case_id: r.internal for r in res}


base = statuses()
orig_scope, orig_events, orig_proof = ap._profile_scope, ap._events, ap.account_proof

variants = {}


def v_system_name_is_enough():
    ap._profile_scope = lambda sc: True
    ap.is_profile_row = lambda o: True      # also treat any collection as profile rows
    # a declared non-profile collection is no longer skipped
    ap.COLLECTION_CATEGORY = {**ap.COLLECTION_CATEGORY, "notification_preferences": ap.PROFILE}


def v_drop_pre_request_events():
    def ev(cv, subj, requested_at, allow_weak, require_row, weak_promotion):
        events, seen = orig_events(cv, subj, requested_at, allow_weak, require_row, weak_promotion)
        return [e for e in events if not e.pre], seen
    ap._events = ev


def v_no_promotion():
    def p(cv, subj, requested_at, allow_weak=False, require_row=False, pre_request_exclusion=True, weak_promotion=True):
        return orig_proof(cv, subj, requested_at, allow_weak, require_row, pre_request_exclusion, False)
    ap.account_proof = p
    import ghostaudit.engine as eng
    eng.account_proof = p


variants = {"treat any account_service collection as a profile collection": v_system_name_is_enough,
            "ignore captures made before the request (the pre-fix behaviour)": v_drop_pre_request_events,
            "disable per-source promotion of weak exports": v_no_promotion}
import importlib  # noqa: E402

for name, fn in variants.items():
    importlib.reload(ap)
    orig_scope, orig_events, orig_proof = ap._profile_scope, ap._events, ap.account_proof
    import ghostaudit.engine as eng
    importlib.reload(eng)
    fn()
    got = statuses()
    changed = {c: (base[c], got[c]) for c in base if base[c] != got[c]}
    print(f"{name}\n   changed fixture cases: {changed or 'NONE (this check would be vacuous)'}")
