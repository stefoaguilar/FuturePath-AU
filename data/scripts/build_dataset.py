# build_dataset.py
# Turns the team's two CSV files plus my 5 hand-read records into one JSON file
# (data/opportunities.json) that follows SCHEMA.md.
#
# How to run (from the data folder):  python scripts/build_dataset.py
# It reads from data/source/: career_pathways.csv, opportunities.csv, hand_read_records.json
#
# WARNING: this was a one-off import. Records were hand-checked after it ran, so
# opportunities.json is now the master copy. Don't re-run this script, it would overwrite those fixes.
#
# Main rule: if the CSV doesn't say something, I leave it as "unknown".
# I never guess. Every record that comes from a CSV stays "needs_recheck"
# until someone opens the official page and checks it by hand.

import csv, json, re, datetime, pathlib

# This file lives in data/scripts/, so the data folder is one level up.
DATA = pathlib.Path(__file__).resolve().parent.parent
SRC = DATA / "source"
OUT = DATA / "opportunities.json"

# The CSV uses its own category words, so these map them to the ones in the schema.
# The schema has no "apprenticeship", so apprenticeships go under traineeship.
CAT = {"Internship": "internship", "Scholarship": "scholarship", "Cadetship": "cadetship",
       "Graduate program": "graduate_program", "Apprenticeship": "traineeship",
       "Traineeship": "traineeship", "Training-to-employment": "traineeship",
       "Early-career program": "other"}

# Same idea for study level. Certificate and diploma both count as vocational.
LEVEL = {"undergraduate": "undergraduate", "postgraduate": "postgraduate", "certificate": "vocational",
         "certificate iv": "vocational", "diploma": "vocational", "school leaver": "school_leaver"}

# These two are already in my hand-read file, so I skip the CSV copy.
# My version is better because it has evidence for each condition.
DUP = {"unsw-cyber": "OPP-002", "defence-grad": "OPP-001"}

# Which records make it into the final 30:
# every High cyber-relevance row from career_pathways.csv, plus three High scholarships,
# plus UniSC. UniSC is only Medium, but it closes on 2026-11-30, so on our demo date
# (2026-11-28) it shows up as "closing soon".
EXTRA_FROM_SCHOLARSHIPS = ["uq-codebots", "csu-csiro", "uq-envato"]
EXTRA_FROM_CAREER_PATHWAYS = ["unisc-first"]


# Skills for the imported records. I only tag a skill when the CSV text (the title, the
# eligibility wording or the notes) actually names that area. If the CSV says nothing,
# the list stays empty. An empty list means "no skills published", not "no skills needed".
# Keep the tags short and in this list so Stefano's skill-gap rule can match them exactly.
SKILLS_BY_CSV_ID = {
    "ct-intern": ["ICT"], "dta-cadet": ["data", "digital"], "cybercx": ["cyber security"],
    "anz-intern": ["technology"], "commbank-tech": ["technology"],
    "suncorp-vac": ["cyber security", "technology"], "telstra-student": ["technology"],
    "ey-cyber": ["cyber security"], "kpmg-vac": ["technology", "digital"], "rba-grad": ["ICT"],
    "qut-csiro": ["STEM"], "qut-accenture": ["STEM"], "services-grad": ["digital", "cyber security"],
    "asio-grad": ["technology"], "uq-codebots": ["computing", "engineering"], "csu-csiro": ["STEM"],
}


def read_csv(name):
    # utf-8-sig drops the invisible BOM at the start of career_pathways.csv.
    # Without it the first column is called "﻿id" and the script crashes.
    with open(SRC / name, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def level_of(raw):
    # Some rows list several levels, like "Undergraduate; postgraduate".
    # If they all map to the same thing I use it, otherwise I call it "any".
    parts = [p.strip().lower() for p in raw.split(";") if p.strip()]
    mapped = {LEVEL.get(p, "unknown") for p in parts}
    return mapped.pop() if len(mapped) == 1 else "any"


def classify(text):
    # Guess the condition type from keywords. It's rough, so a person still checks it later.
    t = text.lower()
    # Words like "varies" or "confirm" mean the CSV doesn't really know the condition,
    # so I call it "unknown" instead of pretending it's a firm rule.
    if re.search(r"\b(vary|varies|differ|differs|confirm|check|depend)", t):
        return "unknown", False
    if "identify as" in t:
        return "identity_requirement", False
    if "citizen" in t or "work-right" in t or "residen" in t:
        return ("location" if "residence" in t else "citizenship_residency"), False
    if "enrol" in t or "student" in t or "course" in t or "degree" in t or "study" in t or "year" in t:
        return "enrolment", False
    return "other", False


def conditions(rec_id, summary, url, pipe):
    # opportunities.csv separates conditions with "|", career_pathways.csv uses one sentence.
    parts = [p.strip() for p in summary.split("|")] if pipe else [summary.strip()]
    out = []
    for i, p in enumerate(p for p in parts if p):
        ctype, _ = classify(p)
        out.append({
            "id": f"{rec_id}-E{i+1}", "type": ctype, "text": p,
            "evidence_summary": "Copied from the team CSV. Not yet compared with the official page.",
            # Always false for imported rows. The app shouldn't auto-check a condition
            # until a person has confirmed the wording is right.
            "source_url": url, "checkable_from_profile": False})
    return out


def deadline(row):
    d = row.get("closing_date", "").strip()
    status_text = (row.get("application_status") or row.get("notes") or "").strip()
    if d:
        datetime.date.fromisoformat(d)  # stops the script if the date is badly typed
        return {"status": "date", "date": d, "note": status_text}
    # No date in the CSV. I keep the free text as a note but don't turn it into a date.
    return {"status": "unknown", "date": None,
            "note": status_text or "No closing date published in the team CSV."}


def convert(row, new_id, pipe):
    # Builds one full record from one CSV row.
    amount = row.get("amount", "").strip()
    note = (row.get("application_status") or row.get("notes") or "").strip()
    # The CSV has no summary column, so I build a short one from the other columns.
    summary = f"{row['provider']}: {row['title']}."
    if amount and amount.lower() != "see source":
        summary += f" Value or pay: {amount}."
    if note:
        summary += f" Team note: {note}."
    return {
        "id": new_id, "record_type": "real", "title": row["title"], "provider": row["provider"],
        "category": CAT.get(row.get("category", "Scholarship"), "other"),
        "location": row["locations"], "study_level": level_of(row["study_levels"]),
        "summary": summary, "skills": SKILLS_BY_CSV_ID.get(row["id"], []),
        "source_url": row["source_url"],
        "eligibility_conditions": conditions(new_id, row["eligibility_summary"], row["source_url"], pipe),
        "deadline": deadline(row),
        "verification": {"verified_on": row["last_verified"], "status": "needs_recheck",
                         "method": "Imported from the team CSV. Not independently checked against the official page."},
        # Keep the old CSV id so I can trace a record back to its row.
        "data_notes": f"Source CSV id: {row['id']}. Cyber relevance in CSV: {row['cyber_relevance']}. "
                      f"Study levels in CSV: {row['study_levels']}."
                      + (" Skills come from the CSV wording and are not yet checked against the official page."
                         if row["id"] in SKILLS_BY_CSV_ID else " No skills published in the CSV, so the skills list is empty.")}


def main():
    hand = json.loads((SRC / "hand_read_records.json").read_text(encoding="utf-8"))["opportunities"]
    cp = read_csv("career_pathways.csv")
    op = {r["id"]: r for r in read_csv("opportunities.csv")}
    records = list(hand)  # my 5 go first, so they keep OPP-001 to OPP-005
    n = len(records)
    picked = [r for r in cp if r["cyber_relevance"] == "High" and r["id"] not in DUP]
    picked += [op[i] for i in EXTRA_FROM_SCHOLARSHIPS]
    picked += [r for r in cp if r["id"] in EXTRA_FROM_CAREER_PATHWAYS]
    for row in picked:
        n += 1
        # Only rows from opportunities.csv use "|" between conditions.
        records.append(convert(row, f"OPP-{n:03d}", pipe=row["id"] in op))
    out = {"schema_version": "0.1-draft",
           "dataset_note": "Real records only. Hand-read records (OPP-001 to OPP-005) were read from official pages on 2026-10-26. "
                           "Later records were imported from the team CSVs and are all needs_recheck until a person opens the source link.",
           "opportunities": records}
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(records)} records to {OUT}")


if __name__ == "__main__":
    main()
