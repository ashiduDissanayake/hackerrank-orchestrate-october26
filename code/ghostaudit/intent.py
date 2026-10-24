"""Baseline request-intent classifier (clause level). Replaced/augmented by the LLM classifier in M5.

A request authorizes deletion when at least one clause affirmatively asks to delete/close the ACCOUNT (or the
person's data in general). The text is split into clauses (sentences, contrast words, and conjunctions followed by
a new instruction) and each clause is classified by action, negation and object:

  AFFIRM_DELETE   deletion verb, not negated, object is the account/profile/personal data (or unspecified)
  NEG_DELETE      negated deletion verb or "keep/leave my account", object is the account/data
  EXCEPTION       negated deletion whose object is records the policy/law requires to be retained: it narrows the
                  deletion, it does not cancel it
  OPT_OUT         marketing/newsletter wording without an account object
  OTHER           access/export/correction/update cues

Decision: AFFIRM_DELETE without NEG_DELETE -> deletion; NEG_DELETE without AFFIRM_DELETE -> not deletion;
both present -> deletion with LOW confidence (contradictory); neither -> OPT_OUT/OTHER means not deletion, else a
low-confidence default of deletion. Any contradictory or unmatched wording is low confidence so it can be reviewed.
"""
import re
from dataclasses import dataclass

DELETE_CUES = re.compile(
    r"\b(delet\w*|eras\w+|remov\w+|clos(?:e|ed|ing|ure)\b|wipe\w*|purge\w*|forget\w*|terminat\w+|deactivat\w+|destroy\w*|"
    r"elimin\w+|borr\w+|suprim\w+|cerrar|cierre|"
    r"suppress?ion|supprim\w+|effac\w+|cl[ôo]tur\w+|"
    r"l[öo]sch\w*|entfern\w+|schlie(?:ß|ss)en|"
    r"exclu\w+|apag\w+|encerr\w+|cancell\w+|verwijder\w*)|"
    r"(削除|消去|退会|閉鎖|解約|抹消|삭제|탈퇴|删除|注销|حذف)", re.I)
NEG = re.compile(
    r"(do\s*not|don[’']?t|never)\s+(?:\w+\s+){0,3}?(delet\w*|remov\w+|eras\w+|clos\w+|wipe\w*)|"
    r"\bnot\s+(?:asking|requesting|a\s+request|an?\s+\w+\s+request)\s+(?:for\s+|to\s+)?(?:the\s+)?(?:deletion|delet\w*|erasure|eras\w+|removal|remov\w+)|"
    r"\bwithout\s+(?:removing|deleting|erasing|closing)\b|"
    r"(not|don[’']?t)\s+(?:want|wish)\s+(?:to\s+)?(?:delet\w*|clos\w+|remov\w+)|"
    r"\bno\s+(?:quiero\s+que\s+)?(?:elimin\w+|borr\w+)|por\s+favor\s+no\s+(?:elimin\w+|borr\w+)|\bno\s+(?:elimin\w+|borr\w+|cierr\w+)|"
    r"ne\s+(?:supprim\w+|effac\w+)\s+pas|ne\s+pas\s+(?:supprim\w+|effac\w+)|"
    r"(?:bitte\s+)?nicht\s+l[öo]sch\w*|n[ãa]o\s+(?:exclu\w+|apag\w+|elimin\w+)|"
    r"(?:削除|消去|解約|退会)(?:しないで|しません|は不要|不要)", re.I)
KEEP_ACCOUNT = re.compile(
    r"\b(?:keep|leave|maintain|preserve)\s+(?:the\s+|my\s+|this\s+)?(?:account|profile)\b|"
    r"\b(?:still|continue\s+to)\s+(?:need|want|use)\s+(?:the\s+|my\s+|this\s+)?(?:account|profile|service)\b|"
    r"\bleave\s+(?:the\s+|my\s+)?(?:profile|account|data|purchase\s+history)\s+(?:in\s+place|as\s+is|intact|unchanged|active|open)\b", re.I)
ACCOUNT_OBJ = re.compile(r"\b(account|profile|personal\s+(?:data|information)|my\s+data|everything|cuenta|compte|konto|conta|datos\s+personales|donn[ée]es)\b|アカウント|プロフィール|個人", re.I)
MARKETING_OBJ = re.compile(r"\b(newsletters?|marketing|promotional|promotions?|mailing\s+lists?|unsubscribe|opt\s*[- ]?out|boletín|infolettre)\b|配信停止|メルマガ", re.I)
RETENTION_OBJ = re.compile(
    r"\b(polic(?:y|ies)|law|legal(?:ly)?|tax|regulat\w+|required|requires?|requirements?|retention|retain\w*|obligat\w+|"
    r"ley|obliga\w*|conserv\w+|loi|l[ée]gal\w*|gesetz\w*|aufbewahr\w+|lei|obrigat\w+)\b|法|保存|保管|義務", re.I)
OTHER_CUES = re.compile(
    r"\b(replace\s+(?:it|my|the)|out\s+of\s+date|copy\s+of|invoices?|receipts?|statement|export\s+(?:of\s+)?my|download\s+my|"
    r"send\s+me\s+(?:a\s+)?(?:copy|my)|access\s+to\s+my|update\s+my|change\s+(?:my|the)|correct\s+my|correction|fix\s+my|"
    r"information\s+request|what\s+personal\s+information|"
    r"copia|factura|actualizar|cambiar|corregir|exportar|copie|facture|modifier|corriger|exporter|"
    r"kopie|rechnung|[äa]ndern|korrigieren|exportieren|c[óo]pia|fatura|atualizar|corrigir)\b|"
    r"(エクスポート|コピー|請求書|変更|訂正|更新|ダウンロード)", re.I)

SENTENCE = re.compile(r"(?<=[.!?。！？;])\s*|(?<=[。！？])")
CONTRAST = re.compile(r"[,;]?\s+(?:but|however|although|though|except|yet|pero|mais|aber|mas|sin\s+embargo)\s+|、?ただし、?|が、", re.I)
NEW_INSTRUCTION = re.compile(
    r"\s+(?:and|y|et|und|e)\s+(?=(?:please\s+|por\s+favor\s+)?(?:keep|leave|do\s*n[o’']?t|don[’']?t|delete|erase|remove|close|stop|unsubscribe|"
    r"change|update|send|no\s|ne\s|nicht|mantenga|dejen|elimin|borr|supprim|l[öo]sch))", re.I)


@dataclass(frozen=True)
class Intent:
    deletion: bool
    confidence: str
    reason: str


def clauses(text):
    out = []
    for sent in SENTENCE.split(text or ""):
        for part in CONTRAST.split(sent):
            out += [c.strip() for c in NEW_INSTRUCTION.split(part) if c and c.strip()]
    return out


def classify_clause(c):
    dele, neg = bool(DELETE_CUES.search(c)), bool(NEG.search(c))
    keep = bool(KEEP_ACCOUNT.search(c))
    account = bool(ACCOUNT_OBJ.search(c))
    marketing = bool(MARKETING_OBJ.search(c))
    retention = bool(RETENTION_OBJ.search(c))
    if neg and retention and not account:
        return "EXCEPTION"
    if neg or (keep and not dele):
        return "NEG_DELETE" if (account or keep or not marketing) else "OPT_OUT"
    if dele:
        if marketing and not account:
            return "OPT_OUT"
        return "AFFIRM_DELETE"
    if marketing:
        return "OPT_OUT"
    if OTHER_CUES.search(c):
        return "OTHER"
    return "NONE"


def classify(text):
    kinds = [(c, classify_clause(c)) for c in clauses(text)]
    ks = [k for _, k in kinds]
    aff, neg = "AFFIRM_DELETE" in ks, "NEG_DELETE" in ks
    if aff and neg:
        return Intent(True, "low", "contradictory clauses: both a deletion and a refusal of deletion")
    if aff:
        mixed = any(k in ("OPT_OUT", "OTHER", "EXCEPTION") for k in ks)
        return Intent(True, "high", "deletion clause" + (" with a scoped exception or side request" if mixed else ""))
    if neg:
        return Intent(False, "high", "deletion explicitly refused")
    if any(k in ("OPT_OUT", "OTHER") for k in ks):
        return Intent(False, "high", "non-deletion request (opt-out, access, export or correction) and no deletion clause")
    return Intent(True, "low", "no cue matched; defaulting to deletion")
