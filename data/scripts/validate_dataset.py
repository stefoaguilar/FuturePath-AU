# validate_dataset.py
# Checks data/opportunities.json against the rules in SCHEMA.md.
# Run it from the data folder:  python scripts/validate_dataset.py
# Errors stop the run (exit code 1). Warnings are just things to look at.

import json, re, sys, datetime, pathlib

# Plan: load the file, check each record against the rules, then print what I found.

# This file lives in data/scripts/, so the data folder is one level up.
DATA = pathlib.Path(__file__).resolve().parent.parent
data = json.loads((DATA / "opportunities.json").read_text(encoding="utf-8"))["opportunities"]

# The allowed values. These need to match SCHEMA.md, so change both if one changes.
CATS = {"scholarship", "internship", "cadetship", "graduate_program", "traineeship", "course", "certification", "mentoring", "other"}
LEVELS = {"undergraduate", "postgraduate", "vocational", "school_leaver", "graduate", "any", "unknown"}
CTYPES = {"education", "enrolment", "field_of_study", "citizenship_residency", "identity_requirement", "skill",
          "experience", "age", "location", "other", "unknown"}
DSTAT = {"date", "rolling", "closed", "unknown"}
VSTAT = {"verified", "needs_recheck", "conflicting", "synthetic"}
# Every record must have all of these fields.
REQ = ["id", "record_type", "title", "provider", "category", "location", "study_level", "summary", "source_url",
       "eligibility_conditions", "deadline", "verification"]

# Errors are real mistakes. Warnings are only things to look at.
errors, warnings = [], []
E = lambda r, m: errors.append(f"{r}: {m}")    # short helpers so the checks below stay on one line
W = lambda r, m: warnings.append(f"{r}: {m}")
ids, urls = set(), set()   # used to spot duplicates

# The date we pretend it is. Records with an earlier deadline get a warning.
# Change this if the recording date changes.
today = datetime.date(2026, 11, 28)

# Check one record at a time.
for o in data:
    r = o.get("id", "?")   # r is the record id, used in the messages

    # Every required field has to be there.
    for k in REQ:
        if k not in o: E(r, f"missing {k}")

    # The id must look like OPP-001 and must be unique.
    if not re.fullmatch(r"OPP-\d{3}", r): E(r, "id must look like OPP-001")
    if r in ids: E(r, "duplicate id")
    ids.add(r)

    # These fields must use one of the allowed words.
    if o.get("record_type") not in {"real", "synthetic"}: E(r, "record_type must be real or synthetic")
    if o.get("category") not in CATS: E(r, f"bad category {o.get('category')}")
    if o.get("study_level") not in LEVELS: E(r, f"bad study_level {o.get('study_level')}")

    # The source link has to be a secure web address.
    u = o.get("source_url", "")
    if not u.startswith("https://"): E(r, "source_url must be https")
    if u in urls: W(r, "source_url shared with another record")  # only a warning, two records can share a page
    urls.add(u)

    # A record with no conditions at all is not allowed. If the page lists none,
    # we still add one condition of type "unknown" so it's obvious we looked.
    if not o.get("eligibility_conditions"): E(r, "needs at least one eligibility condition (use type unknown if truly unknown)")

    # Check each condition. Ids look like OPP-001-E1.
    cids = set()
    for c in o.get("eligibility_conditions", []):
        if not re.fullmatch(re.escape(r) + r"-E\d+", c.get("id", "")): E(r, f"bad condition id {c.get('id')}")
        if c.get("id") in cids: E(r, f"duplicate condition id {c.get('id')}")
        cids.add(c.get("id"))
        if c.get("type") not in CTYPES: E(r, f"{c.get('id')} bad type {c.get('type')}")
        # The most important rule: the app must never decide identity for someone.
        if c.get("type") == "identity_requirement" and c.get("checkable_from_profile"):
            E(r, f"{c.get('id')} identity must never be checkable from profile")
        # Every condition needs its wording, the evidence and a link.
        for k in ("text", "evidence_summary", "source_url"):
            if not c.get(k): E(r, f"{c.get('id')} missing {k}")

    # Deadline: a real date needs a proper date, and "unknown" must not have one.
    d = o.get("deadline", {})
    if d.get("status") not in DSTAT: E(r, "bad deadline status")
    if d.get("status") == "date":
        try: datetime.date.fromisoformat(d.get("date") or "")
        except ValueError: E(r, "deadline status date needs an ISO date")
    elif d.get("status") == "closed":
        # A closed round may keep its old date, but if it's there it has to be a real date.
        if d.get("date"):
            try: datetime.date.fromisoformat(d["date"])
            except ValueError: E(r, "closed deadline date must be ISO if given")
    elif d.get("date"): E(r, "deadline date set but status is not date or closed")

    # Verification: the status must be allowed, and "verified" must say how.
    v = o.get("verification", {})
    if v.get("status") not in VSTAT: E(r, "bad verification status")
    if o.get("record_type") == "real" and v.get("status") == "synthetic": E(r, "real record marked synthetic")
    if o.get("record_type") == "synthetic" and v.get("status") != "synthetic": E(r, "synthetic record must have status synthetic")
    if v.get("status") == "verified" and not v.get("method"): E(r, "verified needs a method")

    # Not an error, just a heads up that the deadline is already over on our demo date.
    if d.get("status") == "date" and d["date"] < str(today): W(r, f"deadline {d['date']} has passed")

# Print the summary at the end.
n = len(data)
print(f"{n} records, {len(errors)} errors, {len(warnings)} warnings")
if not 20 <= n <= 35: print(f"NOTE: the guide asks for about 20-30 records, this file has {n}")
# Empty skills is not a mistake. It means the source didn't list any, so I only count them.
print("records with no skills listed:", sum(1 for o in data if not o.get("skills")))
# List every problem so I can fix them.
for m in errors: print("ERROR  ", m)
for m in warnings: print("WARNING", m)
# Count how many records are in each verification status.
by = {}
for o in data: by[o["verification"]["status"]] = by.get(o["verification"]["status"], 0) + 1
print("verification status counts:", by)
# Exit code 1 means there were errors, 0 means all good.
sys.exit(1 if errors else 0)
