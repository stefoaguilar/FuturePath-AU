# freshness_check.py
# Goes through every record and tells me which ones need looking at again:
# deadlines that passed, deadlines that are close, records nobody has verified,
# and checks that are getting old.
#
# Run it from the data folder:
#   python scripts/freshness_check.py --today 2026-11-28
#   python scripts/freshness_check.py --online --today 2026-11-28
# With --online it also opens each source link once. It only uses Python's built-in
# libraries and it doesn't crawl, it just asks for the one page. If a page fails
# I open it by hand.
# If you leave out --today it uses the real date from the computer.
# The result is also saved as a CSV in data/reports/.

import json, sys, datetime, pathlib, urllib.request, urllib.error, csv

# This file lives in data/scripts/, so the data folder is one level up.
DATA = pathlib.Path(__file__).resolve().parent.parent
# Read the options typed after the script name.
args = sys.argv[1:]
online = "--online" in args
today = datetime.date.fromisoformat(args[args.index("--today") + 1]) if "--today" in args else datetime.date.today()

# If a record was checked more than this many days ago I want to look at it again.
STALE_DAYS = 14

data = json.loads((DATA / "opportunities.json").read_text(encoding="utf-8"))["opportunities"]
rows = []   # one line per record, saved to the CSV at the end

# Go through the records one by one.
for o in data:
    d, v = o["deadline"], o["verification"]   # shortcuts for the deadline and verification parts

    # Work out the deadline state from the date. Same three states the app uses.
    if d["status"] == "date":
        days = (datetime.date.fromisoformat(d["date"]) - today).days
        state = "future" if days >= 0 else "past"
        left = days
    elif d["status"] == "closed":
        state, left = "past", ""
    else:
        state, left = "unknown", ""   # no date published, so I don't make one up

    # How many days since someone last checked this record.
    age = (today - datetime.date.fromisoformat(v["verified_on"])).days

    # Collect the reasons this record needs a look.
    flags = []
    if state == "unknown": flags.append("no deadline: check page")
    if state == "past": flags.append("closed: look for next round")
    if left != "" and 0 <= left <= 14: flags.append("closing within 14 days")
    if v["status"] != "verified": flags.append(v["status"])
    if age > STALE_DAYS: flags.append(f"verification {age} days old")

    # Only with --online: open the link and note the answer.
    status, modified = "", ""
    if online:
        try:
            # A site can block the request if it doesn't have a User-Agent, so I give it a name.
            req = urllib.request.Request(o["source_url"], headers={"User-Agent": "FuturePathAU-freshness-check/0.1"})
            with urllib.request.urlopen(req, timeout=20) as r:
                status, modified = r.status, r.headers.get("Last-Modified", "")
        except urllib.error.HTTPError as e:
            # The server answered but with an error, like 404.
            status = e.code; flags.append(f"HTTP {e.code}: open by hand")
        except Exception:
            # No answer at all (no internet, timeout, bad link).
            status = "error"; flags.append("unreachable: open by hand")

    # Save this record's result.
    rows.append([o["id"], o["title"][:50], state, left, v["status"], age, status, modified, "; ".join(flags)])

# Save a CSV so I can open it in Excel and keep one per date.
out = DATA / "reports"; out.mkdir(exist_ok=True)
path = out / f"freshness_{today.isoformat()}.csv"
with open(path, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["id", "title", "deadline_state", "days_left", "verification", "days_since_verified", "http_status", "last_modified", "flags"])
    w.writerows(rows)

# Print a short summary on the screen.
counts = {}
for r in rows: counts[r[2]] = counts.get(r[2], 0) + 1
print(f"Checked {len(rows)} records on {today}: {counts}. Report: {path}")
# Show only the records that have a reason to look at them.
for r in rows:
    if r[8]: print(f"  {r[0]}  {r[8]}")
