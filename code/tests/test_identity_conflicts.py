"""Lookup-key links vs the identity shown by the returned record; catalog links vs the record's own identity."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ghostaudit.caseview import CaseView  # noqa: E402
from ghostaudit.data import IdentityRow  # noqa: E402
from ghostaudit.extract.common import normalize_fields  # noqa: E402
from ghostaudit.identity import IdentityIndex  # noqa: E402
from ghostaudit.linking import link_subject  # noqa: E402
from ghostaudit.obligations import action_table, evaluate  # noqa: E402
from ghostaudit.observations import Store, make_obs  # noqa: E402
from ghostaudit.pipeline import CatalogLink  # noqa: E402

AT = "2026-06-15T12:00:00Z"
T = "2026-06-10T00:00:00Z"
RULES = [{"data_category": c, "required_action": a} for c, a in (("SEARCH_INDEX_ENTRY", "DELETE"), ("MARKETING_PROFILE", "DELETE"), ("USER_PROFILE", "DELETE"))]
U = IdentityRow("user_9", "Kwame Mensah", "kwame@example.org", "+233 24 456 1267", "d" * 64, "2026-01-01T00:00:00Z")


def world(obs, catalog=()):
    st = Store()
    for i, (system, rid, kind, present, fields) in enumerate(obs):
        st.add_obs(make_obs("evidence_c", f"r{i}", T, T, system, rid, "export", kind, present, normalize_fields(fields)))
    st.catalog_links = list(catalog)
    st.finalize()
    return IdentityIndex([U], []).resolve("kwame@example.org", AT), CaseView(st, AT)


class LookupKey(unittest.TestCase):
    def test_near_miss_document_returned_for_the_subjects_query_is_not_linked(self):
        # a search for the subject's address returned the subject's own document AND a near-miss decoy
        subj, cv = world([
            ("search_service", "search_1", "lookup", True, {"lookup_key": "kwame@example.org", "email": "kwame@example.org"}),
            ("search_service", "search_2", "lookup", True, {"lookup_key": "kwame@example.org", "email": "kwame.jr@example.org"})])
        lr = link_subject(cv, subj)
        self.assertIn("search_1", lr.links)
        self.assertNotIn("search_2", lr.links)
        self.assertTrue(any(r[0] == "search_2" and r[1] == "record_identity_contradicts_lookup_key" for r in lr.rejected))

    def test_lookup_returning_a_record_with_no_identifier_stays_linked(self):
        subj, cv = world([("account_service", "account_1", "lookup", False, {"lookup_key": "kwame@example.org", "status_code": "404"})])
        lr = link_subject(cv, subj)
        self.assertIn("account_1", lr.links)
        self.assertEqual(lr.links["account_1"].chains[0].kind, "trace")

    def test_record_with_its_own_matching_attribute_is_never_rejected(self):
        subj, cv = world([("search_service", "search_3", "record", True, {"email": "kwame@example.org", "lookup_key": "kwame@example.org", "phone": "+44 7700 900000"})])
        self.assertIn("search_3", link_subject(cv, subj).links, "an extra foreign phone does not outweigh the record's own matching email")


class CatalogConflict(unittest.TestCase):
    def test_catalog_link_contradicted_by_the_record_is_an_explicit_conflict(self):
        cat = [CatalogLink(activity_id="act_1", event_time="2026-06-11T00:00:00Z", system_id="marketing_platform", resource_id="marketing_9",
                           email="kwame@example.org", user_ref="user_9", exclusive=False)]
        subj, cv = world([("marketing_platform", "marketing_9", "ui_record", True, {"name": "Someone Else", "email": "other.person@example.org"})], cat)
        lr = link_subject(cv, subj)
        self.assertIn("marketing_9", lr.links)
        self.assertTrue(lr.links["marketing_9"].conflict)
        ob = evaluate(cv, subj, lr.links["marketing_9"], action_table(RULES))
        self.assertEqual((ob.verdict, ob.reason), ("UNKNOWN", "conflicting_identity_evidence"))

    def test_catalog_link_with_a_consistent_record_is_a_normal_violation(self):
        cat = [CatalogLink(activity_id="act_1", event_time="2026-06-11T00:00:00Z", system_id="marketing_platform", resource_id="marketing_9",
                           email="kwame@example.org", user_ref="user_9", exclusive=False)]
        subj, cv = world([("marketing_platform", "marketing_9", "ui_record", True, {"name": "Kwame Mensah"})], cat)
        ob = evaluate(cv, subj, link_subject(cv, subj).links["marketing_9"], action_table(RULES))
        self.assertEqual((ob.verdict, ob.reason), ("VIOLATION", "record_present"))



class ProvenanceIsNotEvidence(unittest.TestCase):
    def test_identifiers_inside_provenance_fields_never_link(self):
        subj, cv = world([("search_service", "search_9", "ui_record", True, {
            "email": "someone.else@example.org", "source_screen": "search console query email:kwame@example.org",
            "provenance_note": "catalog says kwame@example.org / user_9; phone +233 24 456 1267"})])
        self.assertEqual(link_subject(cv, subj).links, {})

    def test_marketing_style_conflict_survives_a_provenance_note_naming_the_subject(self):
        cat = [CatalogLink(activity_id="act_1", event_time="2026-06-11T00:00:00Z", system_id="marketing_platform", resource_id="marketing_9",
                           email="kwame@example.org", user_ref="user_9", exclusive=False)]
        subj, cv = world([("marketing_platform", "marketing_9", "ui_record", True, {
            "name": "Someone Else", "email": "other.person@example.org", "provenance_note": "catalog: kwame@example.org user_9"})], cat)
        lr = link_subject(cv, subj)
        self.assertTrue(lr.links["marketing_9"].conflict)
        self.assertFalse(lr.links["marketing_9"].attribute_direct())



class CatalogLabelJoin(unittest.TestCase):
    def test_statement_pdf_is_joined_to_its_catalog_resource_without_leaking_earlier(self):
        from ghostaudit.pipeline import build
        ds, st = build(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "dataset"))
        obs = st._by_resource["export_1842"]
        self.assertEqual([o.evidence_id for o in obs], ["evidence_18"])
        self.assertEqual(obs[0].available_at, "2026-07-18T11:07:01Z", "raised to the catalog row's event_time")
        self.assertIn("activity_4009", obs[0].f("provenance_resource_id_source"))
        self.assertEqual(CaseView(st, "2026-07-18T11:05:00Z").for_resource("export_1842"), [], "invisible before the catalog row existed")
        self.assertEqual(len(CaseView(st, "2026-07-19T13:00:00Z").for_resource("export_1842")), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
