"""Baseline request-intent heuristic (replaced/augmented by the LLM classifier in M5).

Returns Intent(deletion: bool, confidence: 'high'|'low', reason). A request authorizes deletion unless it
clearly asks for something else (access, export, correction, update, marketing opt-out) or explicitly forbids
deletion. Default when no cue matches is deletion with LOW confidence, so low-confidence rows can be reviewed.
Multilingual cues cover the languages present in the request set (en es fr de pt ja and a few others).
"""
import re
from dataclasses import dataclass

DELETE_CUES = re.compile(
    r"\b(delet\w*|eras\w+|remov\w+|clos(?:e|ed|ing|ure)\b|wipe\w*|purge\w*|forget\w*|terminat\w+|deactivat\w+|destroy\w*|"
    r"elimin\w+|borr\w+|suprim\w+|cerrar|cierre|cancelar\s+mi\s+cuenta|"
    r"suppress?ion|supprim\w+|effac\w+|cl[ôo]tur\w+|"
    r"l[öo]sch\w*|entfern\w+|schlie(?:ß|ss)en|"
    r"exclu\w+|apag\w+|encerr\w+|remov\w+|"
    r"eliminar\w*|cancell\w+|"
    r"verwijder\w*)|"
    r"(削除|消去|退会|閉鎖|解約|抹消|삭제|탈퇴|删除|注销|حذف)",
    re.I)
NEGATED = re.compile(
    r"(do\s*not|don[’']?t|please\s+do\s+not|never)\s+(\w+\s+){0,3}(delet\w*|remov\w+|eras\w+|clos\w+)|"
    r"(leave|keep)\s+(my\s+)?(profile|account|data|purchase\s+history)\s+(in\s+place|as\s+is|intact|unchanged)|"
    r"no\s+(quiero\s+que\s+)?(elimin\w+|borr\w+)|no\s+(elimin\w+|borr\w+)|por\s+favor\s+no\s+(elimin\w+|borr\w+)|"
    r"ne\s+(supprim\w+|effac\w+)\s+pas|ne\s+pas\s+(supprim\w+|effac\w+)|"
    r"nicht\s+l[öo]sch\w*|bitte\s+nicht\s+l[öo]sch\w*|"
    r"n[ãa]o\s+(exclu\w+|apag\w+|elimin\w+)|"
    r"(削除|消去|解約|退会)(しないで|しません|は不要|不要)|(アカウント|口座)は(削除|消去)しないで|"
    r"(not|don[’']?t)\s+(want|wish)\s+(to\s+)?(delet\w*|clos\w+|remov\w+)|"
    r"\bnot\s+(?:asking|requesting|a\s+request|an?\s+\w+\s+request)\s+(?:for\s+|to\s+)?(?:the\s+)?(?:deletion|delet\w*|erasure|eras\w+|removal|remov\w+)|"
    r"\bwithout\s+(?:removing|deleting|erasing|closing)\b|"
    r"\b(?:marketing|promotional|newsletter)\s+(?:lists?|emails?|messages?)\s+only\b|\bonly\s+(?:from\s+)?(?:the\s+)?(?:marketing|promotional|newsletter)\b",
    re.I)
OTHER_CUES = re.compile(
    r"\b(replace\s+(?:it|my|the)|out\s+of\s+date|leave\s+(?:the\s+|my\s+)?account\s+(?:active|open|as\s+it\s+is)|keep\s+(?:the\s+|my\s+)?account|copy\s+of|invoices?|receipts?|statement|export\s+(?:of\s+)?my|download\s+my|send\s+me\s+(?:a\s+)?(?:copy|my)|access\s+to\s+my|"
    r"update\s+my|change\s+my|correct\s+my|correction|fix\s+my|change\s+the\s+(?:email|address)|"
    r"unsubscribe|opt\s*[- ]?out|stop\s+(?:sending|emailing)|marketing\s+(?:emails?|messages?)|newsletter|"
    r"copia|factura|actualizar|cambiar|corregir|exportar|"
    r"copie|facture|modifier|corriger|exporter|"
    r"kopie|rechnung|[äa]ndern|korrigieren|exportieren|"
    r"c[óo]pia|fatura|atualizar|corrigir)\b|"
    r"(エクスポート|コピー|請求書|変更|訂正|更新|配信停止|ダウンロード)",
    re.I)
OPT_OUT_ONLY = re.compile(r"\b(unsubscribe|opt\s*[- ]?out|stop\s+(?:sending|emailing)|marketing|newsletter|promotional)\b|配信停止", re.I)
ACCOUNT_WORDS = re.compile(r"\b(account|profile|personal\s+data|cuenta|compte|konto|conta|アカウント|プロフィール|個人データ)\b|アカウント", re.I)


@dataclass(frozen=True)
class Intent:
    deletion: bool
    confidence: str
    reason: str


def classify(text):
    t = text or ""
    neg = bool(NEGATED.search(t))
    dele = bool(DELETE_CUES.search(t))
    other = bool(OTHER_CUES.search(t))
    if neg:
        return Intent(False, "high" if other or dele else "low", "deletion explicitly refused")
    if dele and other and OPT_OUT_ONLY.search(t) and not re.search(r"\b(delete|erase|remove)\s+(my\s+)?(account|profile|data|personal)", t, re.I) and not ACCOUNT_WORDS.search(t):
        return Intent(False, "low", "marketing opt-out wording without account deletion")
    if dele:
        return Intent(True, "high", "deletion cue")
    if other:
        return Intent(False, "high", "non-deletion request cue and no deletion cue")
    return Intent(True, "low", "no cue matched; defaulting to deletion")
