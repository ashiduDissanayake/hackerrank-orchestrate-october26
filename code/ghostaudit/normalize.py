"""Identifier normalization shared by extraction (indexing), linking (retrieval) and exposure checks.

One definition of how a phone number or name is recognised in text, so the three stages cannot disagree.

Phones: a token is a digit run written with optional '+', spaces, dots, dashes or parentheses, with 9..15 digits and
no word character or dot glued to either end (so order numbers like ORD-20260123 and timestamps are not phones).
A token matches a subject number when, after dropping leading zeros (00-prefixed international form), it equals the
subject's full digits or is a >= 9-digit national suffix of them. Linking is by exact match on that rule, never by
fuzzy similarity.

Names are NEVER used to link (shared names are common): they are only searched, as whole phrases, inside records
that are already linked, to report exposure.
"""
import re

PHONE_TOKEN = re.compile(r"(?<![\w.])\+?\d[\d\s().\-]{6,}\d(?![\w])")
MIN_DIGITS, MAX_DIGITS = 9, 15
# provenance/annotation fields describe how a record was obtained; they are never evidence about WHO the record belongs to
PROVENANCE_PREFIXES = ("provenance_", "transcription_", "source_screen")
SKIP_FIELD_PREFIXES = ("ids_", "trace", "alt_") + PROVENANCE_PREFIXES
SKIP_FIELDS = {"resource_id", "locator", "email_raw", "phone_raw", "email_hash_raw"}


def digits(s):
    return re.sub(r"\D", "", s) if isinstance(s, str) else ""


def norm_phone(v):
    d = digits(v)
    return d or None


def text_fields(fields):
    """(key, value) pairs worth scanning for embedded identifiers."""
    for k, v in fields:
        if v and not k.startswith(SKIP_FIELD_PREFIXES) and k not in SKIP_FIELDS:
            yield k, v


def phone_tokens(text):
    out = []
    for tok in PHONE_TOKEN.findall(text or ""):
        d = digits(tok)
        if MIN_DIGITS <= len(d.lstrip("0")) <= MAX_DIGITS:
            out.append(d)
    return out


def phone_key(d):
    return d.lstrip("0")[-MIN_DIGITS:]


def phone_matches(token_digits, subject_digits):
    t = token_digits.lstrip("0")
    s = subject_digits.lstrip("0")
    return len(t) >= MIN_DIGITS and len(s) >= MIN_DIGITS and (t == s or s.endswith(t))


def name_in_text(name, text):
    """Whole-phrase, case-insensitive match of a full name (>= 5 chars with a space); never a substring of a longer word."""
    n = (name or "").strip()
    if len(n) < 5 or " " not in n:
        return False
    return re.search(r"(?<!\w)" + re.escape(n) + r"(?!\w)", text or "", re.I) is not None
