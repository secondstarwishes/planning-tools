"""Fetch live wait times from Queue-Times.com for the parks SSW shows.
Writes wait-times/data/live.json and appends park-level stats to
wait-times/data/history/YYYY-MM.csv (for a future crowd calendar).
Data: Powered by Queue-Times.com (used with permission, with credit)."""
import csv, json, os, sys, time, urllib.request
from datetime import datetime, timezone

UA = {"User-Agent": "SecondStarWishes-PlanningTools/1.0 (+https://www.secondstarwishes.com)"}
OUT = os.path.join(os.path.dirname(__file__), "..", "wait-times", "data")

# key, display name, resort, words that must all appear in the Queue-Times park name, words that must not
TARGETS = [
    ("mk",   "Magic Kingdom",               "wdw", ["magic kingdom"], []),
    ("epcot","EPCOT",                       "wdw", ["epcot"], []),
    ("hs",   "Hollywood Studios",           "wdw", ["hollywood studios"], []),
    ("ak",   "Animal Kingdom",              "wdw", ["animal kingdom"], []),
    ("dl",   "Disneyland Park",             "dl",  ["disneyland"], ["paris", "hong kong", "shanghai", "tokyo", "studios"]),
    ("dca",  "Disney California Adventure", "dl",  ["california adventure"], []),
    ("usf",  "Universal Studios Florida",   "uo",  ["universal studios"], ["hollywood", "japan", "singapore", "beijing"]),
    ("ioa",  "Islands of Adventure",        "uo",  ["islands of adventure"], []),
    ("epic", "Epic Universe",               "uo",  ["epic universe"], []),
    ("ush",  "Universal Studios Hollywood", "uh",  ["universal studios hollywood"], []),
]
RESORTS = {"wdw": "Walt Disney World", "dl": "Disneyland Resort", "uo": "Universal Orlando", "uh": "Universal Hollywood"}

def get(url):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return json.load(r)
        except Exception as e:
            if attempt == 2: raise
            time.sleep(5)

def find_parks():
    companies = get("https://queue-times.com/parks.json")
    parks = [p for c in companies for p in c.get("parks", []) if p.get("country") == "United States"]
    found, missing = {}, []
    for key, name, resort, must, mustnot in TARGETS:
        hits = [p for p in parks if all(w in p["name"].lower() for w in must) and not any(w in p["name"].lower() for w in mustnot)]
        if key == "dl" and len(hits) > 1:
            exact = [p for p in hits if p["name"].lower().strip() in ("disneyland", "disneyland park")]
            hits = exact or hits
        if len(hits) != 1:
            missing.append((key, [h["name"] for h in hits]))
        else:
            found[key] = hits[0]
    if missing:
        print("Park match problem:", missing, file=sys.stderr)
        print("US parks:", sorted(p["name"] for p in parks), file=sys.stderr)
    return found

def main():
    found = find_parks()
    now = datetime.now(timezone.utc)
    out = {"updated": now.isoformat(timespec="seconds"), "source": "https://queue-times.com/", "resorts": RESORTS, "parks": []}
    hist_rows = []
    for key, name, resort, _, _ in TARGETS:
        p = found.get(key)
        if not p:
            continue
        try:
            data = get(f"https://queue-times.com/parks/{p['id']}/queue_times.json")
        except Exception as e:
            print("Fetch failed", key, e, file=sys.stderr); continue
        groups = list(data.get("lands", []))
        if data.get("rides"):
            groups.append({"name": "Other", "rides": data["rides"]})
        lands = []
        waits = []
        for g in groups:
            rides = [{"n": r["name"], "o": bool(r.get("is_open")), "w": int(r.get("wait_time") or 0), "u": r.get("last_updated")} for r in g.get("rides", [])]
            if rides:
                lands.append({"n": g["name"], "r": rides})
                waits += [r["w"] for r in rides if r["o"]]
        out["parks"].append({"k": key, "n": name, "resort": resort, "tz": p.get("timezone"), "qt": p["id"], "lands": lands})
        avg = round(sum(waits) / len(waits), 1) if waits else ""
        hist_rows.append([now.strftime("%Y-%m-%dT%H:%M"), key, len(waits), avg, max(waits) if waits else ""])
    if not out["parks"]:
        print("No park data fetched", file=sys.stderr); sys.exit(1)
    os.makedirs(os.path.join(OUT, "history"), exist_ok=True)
    with open(os.path.join(OUT, "live.json"), "w") as f:
        json.dump(out, f, separators=(",", ":"), ensure_ascii=False)
    hp = os.path.join(OUT, "history", now.strftime("%Y-%m") + ".csv")
    new = not os.path.exists(hp)
    with open(hp, "a", newline="") as f:
        w = csv.writer(f)
        if new: w.writerow(["utc_time", "park", "open_rides", "avg_wait", "max_wait"])
        w.writerows(hist_rows)
    print("OK", len(out["parks"]), "parks", sum(len(l["r"]) for p in out["parks"] for l in p["lands"]), "rides")
    if len(out["parks"]) < len(TARGETS):
        sys.exit(2)

if __name__ == "__main__":
    main()
