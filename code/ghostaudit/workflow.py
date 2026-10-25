"""Optional workflow-attribution experiment; never a certificate of ownership or deletion.

Build a bipartite graph between overlapping deletion requests and otherwise unlinked
workflow resources. Maximize contextual agreement, allow resources/requests to remain
unassigned, and abstain when forbidding an assignment gives an equally good solution.
Every query is made through a CaseView at the TARGET audit cutoff, including competitors.
No labels, case-number priorities, future identities, or workflow-derived state are used.

Assumptions (deliberately opt-in): one additional orphan per system/request in a workflow
component; one request per orphan in that component; a bounded report-time neighborhood;
proximity and agreement of reported outcomes help ATTRIBUTION, not state reconstruction.
Margins are differences of heuristic scores, NOT calibrated probabilities. The default
thresholds and context weights were selected with public development data, not a holdout.
"""
from bisect import bisect_left, bisect_right
from dataclasses import asdict, dataclass
from datetime import datetime
from math import inf, isfinite

from .caseview import CaseView
from .intent import classify
from .linking import foreign_identifiers, link_subject
from .obligations import category_of_resource

OPERATIONS = {
    "account_service": ("DELETE_RECORD", {"USER_PROFILE"}),
    "analytics_platform": ("ANONYMIZE_RECORD", {"ANALYTICS_PROFILE", "PRODUCT_TELEMETRY"}),
}
OUTCOME = {"SUCCESS": "COMPLETE", "PARTIAL": "PARTIALLY_COMPLETE", "FAILED": "NOT_STARTED"}
EPS = 1e-9


def seconds(timestamp):
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp()


@dataclass(frozen=True)
class WorkflowConfig:
    before_seconds: int = 5400
    after_seconds: int = 600
    min_margin: float = 0.0
    scoring: str = "contextual_v3"  # prior contextual versions and the anchor control remain available

    def __post_init__(self):
        if self.before_seconds <= 0 or self.after_seconds < 0:
            raise ValueError("workflow windows must be positive before and nonnegative after")
        if not isfinite(self.min_margin) or self.min_margin < 0:
            raise ValueError("workflow minimum margin must be finite and nonnegative")
        if self.scoring not in ("contextual", "contextual_v2", "contextual_v3", "anchor"):
            raise ValueError("workflow scoring must be contextual, contextual_v2, contextual_v3 or anchor")

    def to_dict(self):
        return asdict(self)


def maximum_assignment(rows, forbidden=None):
    """Maximum positive-weight partial assignment (successive shortest augmenting paths).

    rows is {request_key: {resource_id: score}}. A null assignment has score zero.
    Returns (total score, mapping). Exact ties may yield any optimum internally;
    callers MUST use counterfactual margins rather than publishing an arbitrary tie.
    """
    source, sink = ("source",), ("sink",)
    requests = [("request", key) for key in sorted(rows)]
    resources = [("resource", rid) for rid in sorted({r for es in rows.values() for r in es})]
    nodes = [source, sink] + requests + resources
    adjacency = {n: [] for n in nodes}
    capacity, cost = {}, {}

    def edge(a, b, c):
        adjacency[a].append(b)
        adjacency[b].append(a)
        capacity[a, b], capacity[b, a] = 1, 0
        cost[a, b], cost[b, a] = c, -c

    for key, es in rows.items():
        a = ("request", key)
        edge(source, a, 0)
        for rid, score in es.items():
            if not isfinite(score):
                raise ValueError("assignment score must be finite")
            if (key, rid) != forbidden:
                edge(a, ("resource", rid), -score)
    for b in resources:
        edge(b, sink, 0)
    total = 0.0
    while True:
        distance = {n: inf for n in nodes}
        distance[source], previous = 0.0, {}
        for _ in range(len(nodes) - 1):
            changed = False
            for a in nodes:
                if distance[a] == inf:
                    continue
                for b in adjacency[a]:
                    if capacity[a, b] and distance[a] + cost[a, b] < distance[b] - EPS:
                        distance[b], previous[b] = distance[a] + cost[a, b], a
                        changed = True
            if not changed:
                break
        if distance[sink] >= -EPS:
            break
        total -= distance[sink]
        node = sink
        while node != source:
            parent = previous[node]
            capacity[parent, node] -= 1
            capacity[node, parent] += 1
            node = parent
    matches = {}
    for key, es in rows.items():
        for rid in es:
            pair = (("request", key), ("resource", rid))
            if pair in capacity and capacity[pair] == 0:
                matches[key] = rid
    return total, matches


class WorkflowAttributor:
    def __init__(self, store, identity, history, config=None, rules=()):
        self.store, self.identity = store, identity
        self.config = config or WorkflowConfig()
        self.history = sorted((r for r in history if classify(r.request_text).deletion),
                              key=lambda r: (r.reported_at, r.requested_at, r.email, r.case_id))
        self.report_times = [seconds(r.reported_at) for r in self.history]
        self._contexts, self._views, self._edges, self._decisions = {}, {}, {}, {}
        self._event_indexes = {}
        from .obligations import action_table
        self.actions = action_table(rules)
        self._ranking_contexts = {}

    def _view(self, cutoff):
        if cutoff not in self._views:
            self._views[cutoff] = CaseView(self.store, cutoff)
        return self._views[cutoff]

    def _context(self, request, cutoff):
        key = (request.email, cutoff)
        if key not in self._contexts:
            subj = self.identity.resolve(request.email, cutoff)
            self._contexts[key] = (subj, link_subject(self._view(cutoff), subj))
        return self._contexts[key]

    def _near_requests(self, event_time, cutoff):
        t, cfg = seconds(event_time), self.config
        lo = bisect_left(self.report_times, t - cfg.after_seconds)
        hi = bisect_right(self.report_times, t + cfg.before_seconds)
        return [q for q in self.history[lo:hi] if q.requested_at <= event_time and q.reported_at <= cutoff]

    def _window_events(self, request, cutoff):
        if cutoff not in self._event_indexes:
            events = sorted((a for a in self._view(cutoff).activity() if a.source_system == "deletion_worker"),
                            key=lambda a: (a.event_time, a.activity_id))
            self._event_indexes[cutoff] = ([seconds(a.event_time) for a in events], events)
        event_times, events = self._event_indexes[cutoff]
        rep, cfg = seconds(request.reported_at), self.config
        lo = bisect_left(event_times, max(seconds(request.requested_at), rep - cfg.before_seconds))
        hi = bisect_right(event_times, min(seconds(cutoff), rep + cfg.after_seconds))
        return events[lo:hi]

    def _candidate_edges(self, request, cutoff, system):
        key = (request.case_id, cutoff, system)
        if key in self._edges:
            return self._edges[key]
        result = self._edges[key] = {}
        if not classify(request.request_text).deletion or request.requested_at > cutoff or request.reported_at > cutoff:
            return result
        subj, links = self._context(request, cutoff)
        if not subj.user_id or subj.conditions:
            return result
        # This is a conservative capacity assumption, not a claim that people have one account forever.
        if any(ln.system_id == system for ln in links.links.values()):
            return result
        cv, events = self._view(cutoff), self._window_events(request, cutoff)
        anchors = [a for a in events if a.resource_id in links.links]
        context = None
        if self.config.scoring in ("contextual_v2", "contextual_v3"):
            from .context_features import ranking_context
            context_key = (request.case_id, cutoff)
            if context_key not in self._ranking_contexts:
                self._ranking_contexts[context_key] = ranking_context(cv, subj, links, request, anchors, self.actions)
            context = self._ranking_contexts[context_key]
        operation, categories = OPERATIONS[system]
        for a in events:
            if a.target_system != system or a.event_type != operation:
                continue
            obs = cv.for_resource(a.resource_id)
            cat = category_of_resource(obs)
            if cat is not None and cat not in categories:
                continue
            if system != "account_service" and not obs:
                continue
            if (self.config.scoring in ("contextual_v2", "contextual_v3") and system == "analytics_platform"
                    and not any(o.present is True for o in obs)):
                # An empty or failed lookup is not evidence of an anonymous
                # policy record. Do not infer a new treated-record obligation
                # from the worker claim alone. Explicit identity links remain
                # the responsibility of the evidence engine.
                continue
            if self.config.scoring in ("contextual_v2", "contextual_v3") and system == "analytics_platform":
                from .state import copy_states
                if not copy_states(cv, a.resource_id, system, None, subj, cat).present_copies():
                    continue
            if foreign_identifiers(cv, subj, a.resource_id):
                continue
            if any(o.f("ids_user") and subj.user_id not in o.f("ids_user").split("|") for o in obs):
                continue
            competitors = self._near_requests(a.event_time, cutoff)
            if any(a.resource_id in self._context(q, cutoff)[1].links and
                   self._context(q, cutoff)[0].user_id != subj.user_id for q in competitors):
                continue
            report_distance = abs(seconds(a.event_time) - seconds(request.reported_at)) / 3600
            anchor_distance = min((abs(seconds(a.event_time) - seconds(b.event_time)) / 3600 for b in anchors),
                                  default=report_distance)
            outcome_match = OUTCOME.get(a.reported_result) == request.reported_status
            score = (3 - anchor_distance if self.config.scoring == "anchor" else
                     3 - report_distance - anchor_distance + float(outcome_match))
            proposal = {"resource_id": a.resource_id, "system_id": system, "activity_id": a.activity_id,
                        "event_time": a.event_time, "score": score,
                        "features": {"report_distance_hours": report_distance, "anchor_distance_hours": anchor_distance,
                                     "reported_outcome_agrees": outcome_match,
                                     "anchor_activity_ids": [b.activity_id for b in anchors]},
                        "contending_case_ids": sorted(q.case_id for q in competitors)}
            if context is not None:
                from .context_features import candidate_context
                adjustment, details = candidate_context(cv, proposal, request, context)
                proposal["score"] += adjustment
                proposal["features"]["context"] = details
                if self.config.scoring == "contextual_v3" and system == "account_service":
                    from .context_features import account_context
                    adjustment, details = account_context(cv, proposal, request, subj, anchors, context)
                    proposal["score"] += adjustment
                    proposal["features"]["account_context"] = details
            old = result.get(a.resource_id)
            if old is None or proposal["score"] > old["score"]:
                result[a.resource_id] = proposal
        return result

    def _component(self, target, cutoff, system):
        pending, seen, rows = [target], set(), {}
        while pending:
            q = pending.pop()
            if q.case_id in seen:
                continue
            seen.add(q.case_id)
            edges = self._candidate_edges(q, cutoff, system)
            if not edges:
                continue
            rows[q.case_id] = edges
            for edge in edges.values():
                for other in self._near_requests(edge["event_time"], cutoff):
                    if other.case_id not in seen and edge["resource_id"] in self._candidate_edges(other, cutoff, system):
                        pending.append(other)
        return rows

    def decisions(self, request):
        """Return candidate rankings and accepted/rejected opt-in proposals, never evidence-backed links."""
        cutoff, out = request.audit_at, []
        for system in OPERATIONS:
            cache_key = (request.case_id, cutoff, system)
            if cache_key not in self._decisions:
                rows = self._component(request, cutoff, system)
                weights = {key: {rid: p["score"] for rid, p in es.items()} for key, es in rows.items()}
                best, matches = maximum_assignment(weights)
                for key, es in rows.items():
                    ranked = sorted(es.values(), key=lambda p: (-p["score"], p["resource_id"]))
                    decision = {"system_id": system, "accepted": False, "reason": "unassigned",
                                "candidates": ranked, "component_case_ids": sorted(rows),
                                "assignment_score": best, "margin": 0.0}
                    if key in matches:
                        rid = matches[key]
                        alternative, _ = maximum_assignment(weights, forbidden=(key, rid))
                        margin = max(0.0, best - alternative)
                        accepted = margin > self.config.min_margin + EPS
                        decision.update({"proposal": es[rid], "margin": margin, "alternative_score": alternative,
                                         "accepted": accepted,
                                         "reason": "inferred_workflow_assignment" if accepted else "ambiguous_or_low_margin"})
                    self._decisions[key, cutoff, system] = decision
                self._decisions.setdefault(cache_key, {"system_id": system, "accepted": False,
                                                      "reason": "no_eligible_candidates", "candidates": [], "margin": 0.0})
            out.append(self._decisions[cache_key])
        return out

    def proposals(self, request):
        return [{**d["proposal"], "margin": d["margin"], "alternative_score": d["alternative_score"],
                 "component_case_ids": d["component_case_ids"], "candidate_count": len(d["candidates"]),
                 "basis": "inferred_workflow_assignment", "certified": False}
                for d in self.decisions(request) if d["accepted"]]
