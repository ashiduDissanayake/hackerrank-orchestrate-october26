"""Baseline intent heuristic tests. Texts are written for the test (not copied from labeled data) except the
four explicit-negation forms observed in the evaluation requests, which test the PATTERN, not a case id."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ghostaudit.intent import classify  # noqa: E402

DELETION = [
    "Please erase the account linked to this email address.",
    "I am asking you to remove my account and the personal information linked to it.",
    "Bitte löschen Sie mein Konto und alle damit verbundenen persönlichen Daten.",
    "Je demande la suppression définitive du compte associé à cette adresse e-mail.",
    "Intenté eliminar mi cuenta ayer, pero la página terminó mostrando un error.",
    "Quero que excluam minha conta e meus dados pessoais.",
    "このメールアドレスに関連するアカウントの完全な削除を依頼します。",
    "Je demande la suppression définitive de mon compte.",
    "I closed my account, but an old download link still works. Please delete that export file as well.",
    "I was told the account had been deleted, but I can still find traces in search.",
]
NOT_DELETION = [
    "I need a copy of last year's invoices for my records. Please leave my profile and purchase history in place.",
    "Quiero actualizar mi correo electrónico; por favor no elimine nada de mi cuenta.",
    "注文履歴のデータをエクスポートしてください。アカウントは削除しないでください。",
    "Please stop the promotional emails. I still need the account and my order history, so I am not asking for deletion.",
    "My surname is misspelled on the account. Can you correct it without removing any of my records?",
    "Please remove me from marketing lists only. I still want receipts and service messages for this account.",
    "Can you tell me what personal information you hold about me? This is an information request, not a request to erase it.",
    "Do not delete my account, I only want to change my phone number.",
    "Merci de ne pas supprimer mon compte, je souhaite seulement modifier mon adresse.",
    "The shipping address on my profile is out of date. Please replace it with the new one and keep the account.",
]


class Intent(unittest.TestCase):
    def test_deletion(self):
        for t in DELETION:
            self.assertTrue(classify(t).deletion, t)

    def test_not_deletion(self):
        for t in NOT_DELETION:
            self.assertFalse(classify(t).deletion, t)

    def test_default_is_low_confidence_deletion(self):
        i = classify("Hello, please process this.")
        self.assertTrue(i.deletion)
        self.assertEqual(i.confidence, "low")


if __name__ == "__main__":
    unittest.main(verbosity=2)
