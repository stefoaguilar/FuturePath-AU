# validate_dataset.py
# Checks data/opportunities.json against the rules in SCHEMA.md.
# Run it from the data folder:  python scripts/validate_dataset.py
# Errors stop the run (exit code 1). Warnings are just things to look at.
# It checks the opportunity records, and also the test scenarios in tests/synthetic_scenarios.json.

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
# The profile fields the test scenarios may use. These must match PROFILE_MAPPING.md.
# Each one has a type, and a list of allowed words if it only takes certain words.
PROFILE = {
    "education_level": ("str", {"undergraduate", "postgraduate", "vocational", "school_leaver", "graduate", "not_stated"}),
    "enrolment_status": ("str", {"enrolled_full_time", "enrolled_part_time", "commencing", "not_enrolled", "not_stated"}),
    "institution": ("str", None),
    "citizenship_status": ("str", {"australian_citizen", "permanent_resident", "nz_citizen", "other", "not_stated"}),
    "state": ("str", {"ACT", "NSW", "NT", "QLD", "SA", "TAS", "VIC", "WA", "not_stated"}),
    "field_of_study": ("str", None),
    "weighted_average": ("number", None),
    "skills": ("list", None),
    "experience_notes": ("str", None),
    "preferred_agencies": ("list", None),
    "identity_answer": ("str", {"yes", "no", "prefer_not_to_say", "not_stated"}),
}
# The fields a record may have. Anything else gets a warning (it is probably a typo).
KNOWN = {"id", "record_type", "title", "provider", "category", "location", "study_level", "summary", "skills",
         "source_url", "eligibility_conditions", "deadline", "verification", "data_notes"}
# Every record must have all of these fields.
REQ = ["id", "record_type", "title", "provider", "category", "location", "study_level", "summary", "source_url",
       "eligibility_conditions", "deadline", "verification"]

# Errors are real mistakes. Warnings are only things to look at.
errors, warnings = [], []
E = lambda r, m: errors.append(f"{r}: {m}")    # short helpers so the checks below stay on one line
W = lambda r, m: warnings.append(f"{r}: {m}")
ids, urls = set(), set()   # used to spot duplicates

def is_text(v):
    # True when v is a piece of text that is not empty.
    return isinstance(v, str) and v.strip() != ""

def is_date(v):
    # True when v is a real date written like 2026-10-27.
    try: datetime.date.fromisoformat(v); return True
    except (TypeError, ValueError): return False

# The date we pretend it is. Records with an earlier deadline get a warning.
# Change this if the recording date changes.
today = datetime.date(2026, 11, 28)

# Check one record at a time.
for o in data:
    r = o.get("id", "?")   # r is the record id, used in the messages

    # Every required field has to be there.
    for k in REQ:
        if k not in o: E(r, f"missing {k}")

    # The fields must also be the right type: text that is not empty, and lists where a list is expected.
    for k in ("id", "record_type", "title", "provider", "category", "location", "study_level", "summary", "source_url"):
        if k in o and not is_text(o[k]): E(r, f"{k} must be text and not empty")
    if "skills" in o and not (isinstance(o["skills"], list) and all(is_text(s) for s in o["skills"])):
        E(r, "skills must be a list of text (an empty list is fine)")
    if "eligibility_conditions" in o and not (isinstance(o["eligibility_conditions"], list) and all(isinstance(c, dict) for c in o["eligibility_conditions"])):
        E(r, "eligibility_conditions must be a list of objects")
        o["eligibility_conditions"] = []   # stop the checks below from crashing
    if "deadline" in o and not isinstance(o["deadline"], dict): E(r, "deadline must be an object"); o["deadline"] = {}
    if "verification" in o and not isinstance(o["verification"], dict): E(r, "verification must be an object"); o["verification"] = {}
    for k in o:
        if k not in KNOWN: W(r, f"unknown field {k}")

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
            if not is_text(c.get(k)): E(r, f"{c.get('id')} {k} must be text and not empty")
        # checkable_from_profile must be true or false, not missing and not text.
        if not isinstance(c.get("checkable_from_profile"), bool): E(r, f"{c.get('id')} checkable_from_profile must be true or false")

    # Deadline: a real date needs a proper date, and "unknown" must not have one.
    d = o.get("deadline", {})
    if d.get("status") not in DSTAT: E(r, "bad deadline status")
    if d.get("status") == "date":
        try: datetime.date.fromisoformat(d.get("date") or "")
        except ValueError: E(r, "deadline status date needs an ISO date")
    elif d.get("status") == "closed":
        # A closed round may keep its old date. If it is there, it must be a real date that is not in the future.
        if d.get("date"):
            if not is_date(d["date"]): E(r, "closed deadline date must be ISO if given")
            elif d["date"] > str(today): E(r, "closed deadline date is in the future")
        # The note must say what the page says, including anything about the next round.
        if not is_text(d.get("note")): E(r, "closed deadline needs a note that says what the page says about the next round")
    elif d.get("date"): E(r, "deadline date set but status is not date or closed")

    # Verification: the status must be allowed, and "verified" must say how.
    v = o.get("verification", {})
    if v.get("status") not in VSTAT: E(r, "bad verification status")
    if o.get("record_type") == "real" and v.get("status") == "synthetic": E(r, "real record marked synthetic")
    if o.get("record_type") == "synthetic" and v.get("status") != "synthetic": E(r, "synthetic record must have status synthetic")
    if v.get("status") == "verified" and not v.get("method"): E(r, "verified needs a method")
    if not is_date(v.get("verified_on")): E(r, "verification.verified_on must be a real date like 2026-10-27")
    if not is_text(v.get("method")): E(r, "verification.method must be text and not empty")

    # Not an error, just a heads up that the deadline is already over on our demo date.
    if d.get("status") == "date" and d["date"] < str(today): W(r, f"deadline {d['date']} has passed")

# ---- The test scenarios ----
# Check that each scenario uses the profile field names and values from PROFILE_MAPPING.md.
SC = DATA.parent / "tests" / "synthetic_scenarios.json"
cond_ids = {c.get("id") for o in data for c in o.get("eligibility_conditions", [])}
rec_ids = {o.get("id") for o in data}
n_sc = 0
if not SC.exists():
    W("scenarios", "tests/synthetic_scenarios.json not found, skipped")
else:
    sc = json.loads(SC.read_text(encoding="utf-8"))
    if sc.get("reference_date") != str(today): E("scenarios", f"reference_date {sc.get('reference_date')} is not {today}")
    seen = set()
    for s in sc.get("scenarios", []):
        n_sc += 1
        i = s.get("id", "?")
        for k in ("id", "name", "profile", "opportunity", "expected"):
            if k not in s: E(i, f"scenario missing {k}")
        if i in seen: E(i, "duplicate scenario id")
        seen.add(i)
        if s.get("opportunity") not in rec_ids | {"any"}: E(i, f"opportunity {s.get('opportunity')} is not in the dataset")
        # Profile: only the agreed field names, with the right type and allowed words.
        prof = s.get("profile", {})
        if not isinstance(prof, dict): E(i, "profile must be an object"); continue
        for k, v in prof.items():
            if k not in PROFILE: E(i, f"profile field {k} is not in PROFILE_MAPPING.md"); continue
            kind, allowed = PROFILE[k]
            if kind == "str" and not is_text(v): E(i, f"profile {k} must be text")
            elif kind == "number" and (isinstance(v, bool) or not isinstance(v, (int, float))): E(i, f"profile {k} must be a number")
            elif kind == "list" and not (isinstance(v, list) and all(is_text(x) for x in v)): E(i, f"profile {k} must be a list of text")
            if allowed and v not in allowed: E(i, f"profile {k} has value {v!r}, allowed: {sorted(allowed)}")
        # Expected results can only name conditions that exist in the record they test.
        for k in s.get("expected", {}):
            if re.fullmatch(r"OPP-\d{3}-E\d+", k) and k not in cond_ids: E(i, f"expected names {k}, which is not a condition")
            if re.fullmatch(r"OPP-\d{3}-E\d+", k) and not k.startswith(str(s.get("opportunity")) + "-"): E(i, f"expected {k} does not belong to {s.get('opportunity')}")

# Print the summary at the end.
n = len(data)
print(f"{n} records, {n_sc} scenarios, {len(errors)} errors, {len(warnings)} warnings")
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
