"""Shared normalization for extracted records (SQL rows, JSON records, log events)."""
import json
import re

EMAIL_RE = re.compile(r"(?<![A-Za-z0-9._%+\-])[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}")
HASH_RE = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{64}(?![0-9a-fA-F])")
USER_RE = re.compile(r"(?<![A-Za-z0-9_])user_[A-Za-z0-9]+(?![A-Za-z0-9_])")
PHONE_FIELDS = ("phone", "requester_phone", "owner_phone")

# Alias -> normalized field name. Raw column/key names are preserved only through these aliases.
ALIASES = {
    "name": ("full_name", "display_name", "requester_name", "name"),
    "email": ("email", "requester_email", "owner_email", "customer_email", "contact_email", "matched_email"),
    "phone": ("phone", "requester_phone", "owner_phone"),
    "email_hash": ("email_hash",),
    "user_ref": ("customer_reference", "user_id"),
}
# subject_reference / subject_selector / lookup_value etc. hold an email in some record types and a user id in
# others, so they are NOT aliased; every field is scanned for exact identifier tokens instead (see ids_*).
_ALIAS_OF = {a: n for n, al in ALIASES.items() for a in al}


def norm_email(v):
    return v.strip().lower() if isinstance(v, str) and v.strip() else None


from ..normalize import PROVENANCE_PREFIXES, norm_phone, phone_tokens, text_fields  # noqa: E402,F401  (single definition of phone handling)


def norm_hash(v):
    return v.strip().lower() if isinstance(v, str) and re.fullmatch(r"[0-9a-fA-F]{64}", v.strip()) else None


def normalize_fields(raw, flatten=("document",)):
    """Return a flat str->str|None dict with identifier fields normalized under stable names.

    Keys outside ALIASES are kept verbatim. Nested dicts named in `flatten` are merged into the top level;
    other nested containers are kept as JSON text under '<key>_json' so later PII checks can still read them.
    """
    flat = {}
    for k, v in raw.items():
        if k in flatten and isinstance(v, dict):
            for k2, v2 in v.items():
                flat.setdefault(k2, v2)
        elif isinstance(v, (dict, list)):
            flat[f"{k}_json"] = json.dumps(v, sort_keys=True, ensure_ascii=False)
        else:
            flat.setdefault(k, v)
    ids = {"email": {}, "hash": {}, "user": {}, "phone": {}, "phonetxt": {}}
    for k, v in flat.items():
        if not isinstance(v, str) or not v or k.startswith(PROVENANCE_PREFIXES):
            continue
        for m in EMAIL_RE.findall(v):
            ids["email"].setdefault(m.lower(), set()).add(k)
        for m in HASH_RE.findall(v):
            ids["hash"].setdefault(m.lower(), set()).add(k)
        for m in USER_RE.findall(v):
            ids["user"].setdefault(m, set()).add(k)
        if k in PHONE_FIELDS:
            d = norm_phone(v)
            if d:
                ids["phone"].setdefault(d, set()).add(k)
    for k, v in text_fields(tuple((k, v) for k, v in flat.items() if isinstance(v, str))):
        for d in phone_tokens(v):
            ids["phonetxt"].setdefault(d, set()).add(k)
    out = {}
    for k, v in flat.items():
        name = _ALIAS_OF.get(k, k)
        if isinstance(v, bool):
            v = "true" if v else "false"
        if v is not None:
            v = str(v)
        if name in out and out[name] is not None:
            # several aliases for one field (e.g. email + owner_email): keep first non-null, remember the other
            if v is not None and v != out[name]:
                out[f"alt_{k}"] = v  # never overwrite the first value; keep the disagreeing alias visible
            continue
        out[name] = v
    # light normalization used for matching; raw display value kept in *_raw
    for key, fn in (("email", norm_email), ("phone", norm_phone), ("email_hash", norm_hash)):
        if out.get(key) is not None:
            out[f"{key}_raw"] = out[key]
            out[key] = fn(out[key])
    for kind, found in ids.items():
        if found:
            out[f"ids_{kind}"] = "|".join(sorted(found))
    if any(ids.values()):
        out["ids_src"] = json.dumps({f"{kind}:{val}": sorted(fl) for kind, found in ids.items() for val, fl in found.items()}, sort_keys=True)
    return out
