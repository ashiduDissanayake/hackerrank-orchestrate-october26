"""PNG screenshots: structured extraction is done once by a vision model (M5) and cached.
Until then every image is reported as `pending` so coverage numbers never overstate."""


def extract(evidence_id, path, available_at, store, report):
    report.status = "pending"
    report.notes.append("vision extraction not run yet (M5)")
