"""Phone/name normalization applied consistently in indexing, linking and exposure checks, with guards."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ghostaudit.caseview import CaseView  # noqa: E402
from ghostaudit.data import AuditChange, IdentityRow  # noqa: E402
from ghostaudit.extract.common import normalize_fields  # noqa: E402
from ghostaudit.identity import IdentityIndex  # noqa: E402
from ghostaudit.linking import link_subject  # noqa: E402
from ghostaudit.normalize import name_in_text, phone_matches, phone_tokens  # noqa: E402
from ghostaudit.observations import Store, make_obs  # noqa: E402
from ghostaudit.obligations import action_table, evaluate  # noqa: E402

AT = "2026-06-15T12:00:00Z"
OLD, NEW = "+44 7700 900111", "+44 7700 900123"
RULES = [{"data_category": "SUPPORT_MESSAGE", "required_action": "REDACT"}]


def world(records, changes=True):
    u = IdentityRow("user_5", "Marta Quiroga", "marta@example.org", NEW, "c" * 64, "2026-05-01T00:00:00Z")
    ch = [AuditChange("a1", "user_5", "2026-05-01T00:00:00Z", "phone", OLD, NEW)] if changes else []
    ix = IdentityIndex([u], ch)
    st = Store()
    for i, (rid, t, text) in enumerate(records):
        st.add_obs(make_obs("evidence_p", f"r{i}", t, t, "support_platform", rid, "inventory", "record", True, normalize_fields({"message_text": text})))
    st.finalize()
    return ix.resolve("marta@example.org", AT), CaseView(st, AT)


class Normalization(unittest.TestCase):
    def test_written_forms_of_one_number_match(self):
        d = "447700900123"
        for text in ("+44 7700 900123", "+44-7700-900123", "(+44) 7700 900123", "0044 7700 900123", "07700 900123", "07700.900.123", "7700900123"):
            toks = phone_tokens(f"call {text} please")
            self.assertTrue(any(phone_matches(t, d) for t in toks), text)

    def test_unrelated_numbers_do_not_match(self):
        d = "447700900123"
        for text in ("order ORD-20260123 shipped", "ticket 12345678", "ref 2026-06-10 12:30:45", "tracking 9447700900123", "call +44 7700 900124",
                     "sku 77009001 24", "+1 202 555 0103"):
            toks = phone_tokens(text)
            self.assertFalse(any(phone_matches(t, d) for t in toks), text)

    def test_names_only_whole_phrases(self):
        self.assertTrue(name_in_text("Marta Quiroga", "Customer marta quiroga asked"))
        self.assertFalse(name_in_text("Marta Quiroga", "Submarta Quirogaville"))
        self.assertFalse(name_in_text("Ann", "Ann called"))
        self.assertFalse(name_in_text("Marta", "Marta called"), "single names are never matched")


class Linking(unittest.TestCase):
    def test_record_with_phone_only_in_free_text_is_linked_and_checked(self):
        subj, cv = world([("support_1", "2026-06-10T00:00:00Z", "Please ring me on 07700 900123 about delivery.")])
        lr = link_subject(cv, subj)
        self.assertIn("support_1", lr.links)
        ch = lr.links["support_1"].chains[0]
        self.assertEqual((ch.kind, ch.field), ("direct", "message_text"))
        ob = evaluate(cv, subj, lr.links["support_1"], action_table(RULES))
        self.assertEqual((ob.verdict, ob.reason), ("VIOLATION", "identifiers_exposed"))

    def test_historical_phone_links_only_records_written_after_it_belonged_to_the_user(self):
        # OLD was the user's number until 2026-05-01; NEW from then on
        subj, cv = world([("support_old", "2026-04-01T00:00:00Z", "my number is +44 7700 900111"),
                          ("support_new_early", "2026-04-01T00:00:00Z", "my number is +44 7700 900123"),
                          ("support_new", "2026-06-01T00:00:00Z", "my number is +44 7700 900123")])
        lr = link_subject(cv, subj)
        self.assertIn("support_old", lr.links, "historical number is linkable (valid from before the log)")
        self.assertNotIn("support_new_early", lr.links, "NEW cannot link a record written before it belonged to the user")
        self.assertIn("support_new", lr.links)
        self.assertTrue(any(r[0] == "support_new_early" for r in lr.rejected))

    def test_unrelated_numbers_and_names_never_link(self):
        subj, cv = world([("support_a", "2026-06-10T00:00:00Z", "order ORD-20260123 and ticket 12345678"),
                          ("support_b", "2026-06-10T00:00:00Z", "Customer Marta Quiroga asked about delivery"),
                          ("support_c", "2026-06-10T00:00:00Z", "call +44 7700 900124 or +1 202 555 0103")])
        self.assertEqual(sorted(link_subject(cv, subj).links), [], "a name alone or a different number is not identity proof")

    def test_future_record_with_the_number_is_not_visible(self):
        subj, cv = world([("support_f", "2026-06-20T00:00:00Z", "ring +44 7700 900123")])
        self.assertEqual(link_subject(cv, subj).links, {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
