"""Sabotage check for fixtures v4: re-introduce each fixed flaw by monkeypatching and show which frozen fixture flips. A variant that
changes nothing would mean the fixture proves nothing.  python3 scripts/sabotage_v4.py"""
import importlib
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "code"))
FX = os.path.join(REPO, "code", "evaluation", "fixtures", "synth_v4")


def fresh():
    for m in [m for m in sys.modules if m.startswith("ghostaudit")]:
        del sys.modules[m]
    from ghostaudit import run
    return run


def snapshot(run, **kw):
    _, _, res = run.run_dataset(FX, **kw)
    return {r.case_id: (r.status, tuple((s["phase"], s["resource_id"], s["operation"]) for s in r.steps)) for r in res}


base = snapshot(fresh())


def report(name, got):
    changed = sorted(c for c in base if base[c] != got[c])
    print(f"{name}\n   fixtures that change: {changed or 'NONE (this check would be vacuous)'}")


# 1. episode scoping switched off
report("no request-episode scoping", snapshot(fresh(), episode_scoping=False))

# 2. a source reference no longer resolves its system (the old Link(src, None) behaviour)
run = fresh()
from ghostaudit import linking  # noqa: E402
linking._resolve_system = lambda cv, ln: None if ln.system_id is None and not cv.for_resource(ln.resource_id) else orig(cv, ln)  # noqa: F821
orig = None
run = fresh()
from ghostaudit import linking as L  # noqa: E402
orig = L._resolve_system
L._resolve_system = lambda cv, ln: (orig(cv, ln) if cv.for_resource(ln.resource_id) else None)
report("source-referenced resource gets no system (silently dropped)", snapshot(run))

# 3. treatment label clears every detected exposure (the old behaviour)
run = fresh()
from ghostaudit import facts  # noqa: E402
_read = facts.read


def old_read(o, subj=None):
    f = _read(o, subj)
    if (o.kind == "record_lookup" or o.store in ("handover", "ledger", "history")) and o.f("result") in ("ANONYMIZED", "REDACTED"):
        f.exposed.clear()
    return f


facts.read = old_read
import ghostaudit.obligations as ob  # noqa: E402
ob.read = old_read
report("treatment label overrides the returned payload", snapshot(run))

# 4. any scope absence is accepted for a linked resource (the old copy_states behaviour)
run = fresh()
from ghostaudit import coverage_rules as cr  # noqa: E402
import ghostaudit.state as st  # noqa: E402
st.absence_support = lambda cv, subj, sc, category, allow_weak=False: (True, sc.basis)
report("unsupported scope omission erases presence", snapshot(run))
