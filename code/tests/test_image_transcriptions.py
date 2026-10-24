"""Independent cross-check of the hand-authored PNG transcriptions against local OCR (tesseract, 3x upscale).

Forward : every identifier typed into a transcription must be visible in the OCR text (edit distance <= 1).
Reverse : every identifier-shaped token OCR finds must be in the transcription, or declared in `omitted_identifiers`
          (OCR may truncate a long id, so an OCR token that is a >= 7-char prefix of a transcribed id also counts).
Also: each transcription is bound to its PNG by sha256 and every record has the provenance fields it needs.
Skipped (loudly) when tesseract or Pillow is missing.  Run: python3 code/tests/test_image_transcriptions.py
"""
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CODE = os.path.dirname(HERE)
REPO = os.path.dirname(CODE)
sys.path.insert(0, CODE)

EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}")
RES = re.compile(r"\b(?:account|analytics|audit_record|backup|data_flow|export|legal_hold|marketing|search|support|tombstone|object|email_delivery)_\d+\b")
USER = re.compile(r"\buser_\d+\b")
TDIR = os.path.join(CODE, "ghostaudit", "image_transcriptions")

try:
    from PIL import Image
    HAVE = bool(shutil.which("tesseract"))
except ImportError:  # pragma: no cover
    HAVE = False


def lev(a, b, cap=2):
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[-1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def ocr_text(path):
    im = Image.open(path).convert("L")
    im = im.resize((im.width * 3, im.height * 3), Image.LANCZOS)
    tmp = tempfile.mktemp(suffix=".png")
    im.save(tmp)
    try:
        return "\n".join(subprocess.run(["tesseract", tmp, "-", "--psm", psm], capture_output=True, text=True).stdout for psm in ("11", "6"))
    finally:
        os.remove(tmp)


def ocr_crop(path, box, scale=5):
    im = Image.open(path).convert("L").crop(tuple(box))
    im = im.resize((im.width * scale, im.height * scale), Image.LANCZOS)
    tmp = tempfile.mktemp(suffix=".png")
    im.save(tmp)
    try:
        return "\n".join(subprocess.run(["tesseract", tmp, "-", "--psm", psm], capture_output=True, text=True).stdout for psm in ("7", "8", "13"))
    finally:
        os.remove(tmp)


def transcribed_ids(doc):
    ids = set()
    for r in doc["records"]:
        if not r.get("resource_id_source"):
            ids.add(r["resource_id"])
        blob = " ".join(str(v) for v in r["fields"].values())
        ids |= set(EMAIL.findall(blob)) | set(USER.findall(blob)) | set(RES.findall(blob))
    return {i.lower() for i in ids}


@unittest.skipUnless(HAVE, "tesseract/Pillow not available: OCR cross-check SKIPPED (install tesseract and `pip install pillow`)")
class OcrCrossCheck(unittest.TestCase):
    def test_every_transcription_agrees_with_ocr_in_both_directions(self):
        problems = []
        for tpath in sorted(glob.glob(os.path.join(TDIR, "*.json"))):
            doc = json.load(open(tpath, encoding="utf-8"))
            img = os.path.join(REPO, "dataset", doc["source_path"])
            self.assertEqual(hashlib.sha256(open(img, "rb").read()).hexdigest(), doc["source_sha256"], tpath)
            text = ocr_text(img)
            ocr_ids = {t.lower() for t in EMAIL.findall(text) + RES.findall(text) + USER.findall(text)}
            mine = transcribed_ids(doc)
            for t in sorted(mine):
                if any(lev(t, o) <= 1 for o in ocr_ids):
                    continue
                box = doc.get("ocr_recheck_boxes", {}).get(t)
                if box and t in ocr_crop(img, box).lower():   # exact read of the cropped line is the independent confirmation
                    continue
                problems.append(f"{doc['evidence_id']}: transcribed {t!r} not found in OCR (full image" + (" or declared crop)" if box else "; no crop declared)"))
            declared = {x.lower() for x in doc.get("omitted_identifiers", [])}
            for o in sorted(ocr_ids):
                if any(lev(o, t) <= 1 for t in mine) or any(len(o) >= 7 and t.startswith(o) for t in mine) or o in declared:
                    continue
                problems.append(f"{doc['evidence_id']}: OCR sees {o!r} that is neither transcribed nor declared omitted")
        self.assertEqual(problems, [], "\n".join(problems))


class TranscriptionStructure(unittest.TestCase):
    def test_provenance_and_binding(self):
        files = sorted(glob.glob(os.path.join(TDIR, "*.json")))
        self.assertEqual(len(files), len(glob.glob(os.path.join(REPO, "dataset", "evidence", "images", "*.png"))), "one transcription per PNG")
        for tpath in files:
            doc = json.load(open(tpath, encoding="utf-8"))
            for k in ("evidence_id", "source_sha256", "method", "transcriber", "manifest_captured_at", "records", "screen"):
                self.assertIn(k, doc, tpath)
            self.assertIn("hand-authored", doc["method"])
            for r in doc["records"]:
                self.assertTrue(r["observed_at"] >= doc["manifest_captured_at"] or r.get("note") or r["kind"] == "ui_reference", f"{tpath}: observed_at before capture without a note")
                if r["resource_id"].startswith(("object_", "tombstone_")):
                    self.assertIn("resource_id_source", r, "ids the screen does not print must cite the catalog row they came from")

    def test_tampered_image_is_rejected(self):
        from ghostaudit.extract import images
        from ghostaudit.observations import ArtifactReport, Store
        tmp = tempfile.mktemp(suffix=".png")
        open(tmp, "wb").write(b"not the original image")
        rep = ArtifactReport("evidence_09", tmp, "png", "2026-09-01T06:00:00Z")
        st = Store()
        images.extract("evidence_09", tmp, "2026-09-01T06:00:00Z", st, rep)
        os.remove(tmp)
        self.assertEqual(rep.status, "failed")
        self.assertEqual(st._obs, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
