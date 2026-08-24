#!/usr/bin/env python3
"""Build the Tour Championship hand-entered books + DataGolf model file.

Kalshi = fair anchor for Winner; DataGolf model = fair anchor for Top 5 / Top 10
(Kalshi lists no such market for this event). All names are canonicalized against
the live Kalshi winner snapshot via gen_books (CANON_SNAPSHOT), so a typo in any
board raises instead of silently mis-keying.
"""
import csv
import json
import os

os.environ["CANON_SNAPSHOT"] = "data/tourchamp/winner/snapshot.json"
os.environ["RACE_NAME"] = "2026 TOUR Championship"
os.environ["MANUAL_DIR"] = "data/tourchamp/manual"

import gen_books as gb  # noqa: E402  (env must be set first)

EV = 100  # "Ev"/"Even" money

# ---------------------------------------------------------------------------
# BetUS (text board): To Win Outright / Top 5 / Top 10
# ---------------------------------------------------------------------------
betus_win = [
    ("Scottie Scheffler", 300), ("Rory McIlroy", 750), ("Xander Schauffele", 1200),
    ("Ludvig Aberg", 1400), ("Patrick Cantlay", 1600), ("Wyndham Clark", 1600),
    ("Cameron Young", 1800), ("Sam Burns", 1800), ("Tommy Fleetwood", 1800),
    ("Chris Gotterup", 1900), ("Matt Fitzpatrick", 2000), ("Collin Morikawa", 2200),
    ("Russell Henley", 2200), ("Si Woo Kim", 2500), ("Viktor Hovland", 2500),
    ("Hideki Matsuyama", 2800), ("J.J. Spaun", 3500), ("Robert MacIntyre", 4000),
    ("Ryan Gerard", 4000), ("Adam Scott", 4500), ("Tom Kim", 4500),
    ("Gary Woodland", 5000), ("Jacob Bridgeman", 5000), ("Justin Rose", 5000),
    ("Min Woo Lee", 5000), ("Akshay Bhatia", 6000), ("Alex Smalley", 6000),
    ("Kristoffer Reitan", 6000), ("Alex Fitzpatrick", 8000), ("Ryan Fox", 9000),
]
betus_t5 = [
    ("Scottie Scheffler", -170), ("Rory McIlroy", 140), ("Xander Schauffele", 200),
    ("Ludvig Aberg", 220), ("Patrick Cantlay", 250), ("Wyndham Clark", 250),
    ("Cameron Young", 280), ("Sam Burns", 280), ("Tommy Fleetwood", 280),
    ("Chris Gotterup", 300), ("Matt Fitzpatrick", 335), ("Collin Morikawa", 335),
    ("Russell Henley", 335), ("Si Woo Kim", 375), ("Viktor Hovland", 375),
    ("Hideki Matsuyama", 400), ("J.J. Spaun", 475), ("Robert MacIntyre", 550),
    ("Ryan Gerard", 550), ("Adam Scott", 550), ("Tom Kim", 550),
    ("Gary Woodland", 600), ("Jacob Bridgeman", 600), ("Justin Rose", 600),
    ("Min Woo Lee", 600), ("Akshay Bhatia", 750), ("Alex Smalley", 750),
    ("Kristoffer Reitan", 750), ("Alex Fitzpatrick", 900), ("Ryan Fox", 1100),
]
betus_t10 = [
    ("Scottie Scheffler", -475), ("Rory McIlroy", -200), ("Xander Schauffele", -135),
    ("Ludvig Aberg", -130), ("Patrick Cantlay", -115), ("Wyndham Clark", -115),
    ("Cameron Young", -105), ("Sam Burns", -105), ("Tommy Fleetwood", -105),
    ("Chris Gotterup", 105), ("Matt Fitzpatrick", EV), ("Collin Morikawa", 115),
    ("Russell Henley", 115), ("Si Woo Kim", 125), ("Viktor Hovland", 125),
    ("Hideki Matsuyama", 135), ("J.J. Spaun", 160), ("Robert MacIntyre", 180),
    ("Ryan Gerard", 180), ("Adam Scott", 185), ("Tom Kim", 185),
    ("Gary Woodland", 190), ("Jacob Bridgeman", 190), ("Justin Rose", 190),
    ("Min Woo Lee", 190), ("Akshay Bhatia", 225), ("Alex Smalley", 225),
    ("Kristoffer Reitan", 225), ("Alex Fitzpatrick", 280), ("Ryan Fox", 320),
]

# ---------------------------------------------------------------------------
# BetBoss (screenshots): Outright Winner / To Finish Top 5 / To Finish Top 10
# ---------------------------------------------------------------------------
betboss_win = [
    ("Adam Scott", 3650), ("Akshay Bhatia", 6625), ("Alex Fitzpatrick", 7600),
    ("Alex Smalley", 5375), ("Cameron Young", 1750), ("Chris Gotterup", 1850),
    ("Collin Morikawa", 1750), ("Gary Woodland", 3525), ("Hideki Matsuyama", 2700),
    ("Jacob Bridgeman", 4250), ("JJ Spaun", 3625), ("Justin Rose", 4250),
    ("Kristoffer Reitan", 5250), ("Ludvig Aberg", 1400), ("Matt Fitzpatrick", 1800),
    ("Min Woo Lee", 4875), ("Patrick Cantlay", 1600), ("Robert MacIntyre", 3650),
    ("Rory McIlroy", 825), ("Russell Henley", 2225), ("Ryan Fox", 8225),
    ("Ryan Gerard", 3525), ("Sam Burns", 1600), ("Scottie Scheffler", 312),
    ("Si Woo Kim", 2350), ("Tom Kim", 4125), ("Tommy Fleetwood", 1650),
    ("Viktor Hovland", 2500), ("Wyndham Clark", 1450), ("Xander Schauffele", 1125),
]
betboss_t5 = [
    ("Adam Scott", 635), ("Akshay Bhatia", 988), ("Alex Fitzpatrick", 988),
    ("Alex Smalley", 810), ("Cameron Young", 283), ("Chris Gotterup", 322),
    ("Collin Morikawa", 315), ("Gary Woodland", 640), ("Hideki Matsuyama", 397),
    ("Jacob Bridgeman", 710), ("JJ Spaun", 588), ("Justin Rose", 585),
    ("Kristoffer Reitan", 860), ("Ludvig Aberg", 253), ("Matt Fitzpatrick", 315),
    ("Min Woo Lee", 690), ("Patrick Cantlay", 265), ("Robert MacIntyre", 575),
    ("Rory McIlroy", 149), ("Russell Henley", 384), ("Ryan Fox", 1163),
    ("Ryan Gerard", 585), ("Sam Burns", 275), ("Scottie Scheffler", -151),
    ("Si Woo Kim", 338), ("Tom Kim", 640), ("Tommy Fleetwood", 290),
    ("Viktor Hovland", 403), ("Wyndham Clark", 275), ("Xander Schauffele", 213),
]
betboss_t10 = [
    ("Adam Scott", 206), ("Akshay Bhatia", 288), ("Alex Fitzpatrick", 308),
    ("Alex Smalley", 265), ("Cameron Young", 113), ("Chris Gotterup", 115),
    ("Collin Morikawa", 113), ("Gary Woodland", 203), ("Hideki Matsuyama", 133),
    ("Jacob Bridgeman", 238), ("JJ Spaun", 192), ("Justin Rose", 228),
    ("Kristoffer Reitan", 265), ("Ludvig Aberg", -107), ("Matt Fitzpatrick", 108),
    ("Min Woo Lee", 250), ("Patrick Cantlay", -107), ("Robert MacIntyre", 203),
    ("Rory McIlroy", -179), ("Russell Henley", 127), ("Ryan Fox", 225),
    ("Ryan Gerard", 203), ("Sam Burns", 105), ("Scottie Scheffler", -442),
    ("Si Woo Kim", 127), ("Tom Kim", 219), ("Tommy Fleetwood", 105),
    ("Viktor Hovland", 144), ("Wyndham Clark", -107), ("Xander Schauffele", -139),
]

# ---------------------------------------------------------------------------
# Caesars (JSON price.a): Tournament Winner / Top 5 / Top 10
# ---------------------------------------------------------------------------
czr_win = [
    ("Scottie Scheffler", 310), ("Rory McIlroy", 1000), ("Xander Schauffele", 1100),
    ("Sam Burns", 1200), ("Wyndham Clark", 1400), ("Ludvig Aberg", 1500),
    ("Collin Morikawa", 1800), ("Matt Fitzpatrick", 1800), ("Cameron Young", 1800),
    ("Tommy Fleetwood", 2000), ("Chris Gotterup", 2000), ("Patrick Cantlay", 2000),
    ("Si Woo Kim", 2000), ("Viktor Hovland", 2500), ("Russell Henley", 2700),
    ("Hideki Matsuyama", 3500), ("Gary Woodland", 4000), ("J.J. Spaun", 4000),
    ("Jacob Bridgeman", 4000), ("Ryan Gerard", 4500), ("Tom Kim", 4500),
    ("Justin Rose", 4500), ("Adam Scott", 5000), ("Robert MacIntyre", 5000),
    ("Min Woo Lee", 5500), ("Alex Smalley", 6500), ("Kristoffer Reitan", 6500),
    ("Akshay Bhatia", 7500), ("Alex Fitzpatrick", 8000), ("Ryan Fox", 10000),
]
czr_t5 = [
    ("Scottie Scheffler", -150), ("Rory McIlroy", 170), ("Xander Schauffele", 195),
    ("Ludvig Aberg", 255), ("Wyndham Clark", 260), ("Sam Burns", 280),
    ("Cameron Young", 280), ("Collin Morikawa", 280), ("Matt Fitzpatrick", 300),
    ("Patrick Cantlay", 300), ("Tommy Fleetwood", 310), ("Chris Gotterup", 325),
    ("Si Woo Kim", 360), ("Russell Henley", 400), ("Viktor Hovland", 400),
    ("Hideki Matsuyama", 475), ("J.J. Spaun", 600), ("Gary Woodland", 600),
    ("Ryan Gerard", 600), ("Tom Kim", 625), ("Robert MacIntyre", 625),
    ("Jacob Bridgeman", 675), ("Adam Scott", 675), ("Justin Rose", 675),
    ("Min Woo Lee", 750), ("Alex Smalley", 850), ("Kristoffer Reitan", 850),
    ("Alex Fitzpatrick", 1100), ("Ryan Fox", 1300), ("Akshay Bhatia", 1300),
]
czr_t10 = [
    ("Scottie Scheffler", -560), ("Rory McIlroy", -165), ("Xander Schauffele", -145),
    ("Collin Morikawa", 100), ("Ludvig Aberg", 100), ("Cameron Young", 100),
    ("Matt Fitzpatrick", 105), ("Sam Burns", 105), ("Wyndham Clark", 105),
    ("Patrick Cantlay", 110), ("Tommy Fleetwood", 115), ("Chris Gotterup", 125),
    ("Si Woo Kim", 130), ("Russell Henley", 140), ("Viktor Hovland", 150),
    ("Hideki Matsuyama", 175), ("J.J. Spaun", 210), ("Gary Woodland", 210),
    ("Ryan Gerard", 225), ("Robert MacIntyre", 230), ("Adam Scott", 235),
    ("Jacob Bridgeman", 235), ("Tom Kim", 235), ("Justin Rose", 250),
    ("Min Woo Lee", 275), ("Alex Smalley", 300), ("Kristoffer Reitan", 300),
    ("Alex Fitzpatrick", 330), ("Akshay Bhatia", 400), ("Ryan Fox", 450),
]

BOOKS = {
    "betus.json":   ("BetUS",   {"winner": (betus_win, 1),   "top5": (betus_t5, 5),   "top10": (betus_t10, 10)}),
    "betboss.json": ("BetBoss", {"winner": (betboss_win, 1), "top5": (betboss_t5, 5), "top10": (betboss_t10, 10)}),
    "caesars.json": ("Caesars", {"winner": (czr_win, 1),     "top5": (czr_t5, 5),     "top10": (czr_t10, 10)}),
}

for fn, (src, tiers) in BOOKS.items():
    for tk, (rows, nw) in tiers.items():
        assert len(rows) == 30, f"{fn} {tk}: expected 30 rows, got {len(rows)}"
    obj = gb.write_book(fn, src, tiers)
    print(f"wrote {fn}: " + ", ".join(f"{tk}={len(v['drivers'])}" for tk, v in obj["tiers"].items()))

# ---------------------------------------------------------------------------
# DataGolf model -> data/tourchamp/model/datagolf.json
# fair-probability anchor. CSV names are "Last, First"; flip + canonicalize.
# ---------------------------------------------------------------------------
CSV = "/root/.claude/uploads/48629e05-cb5e-5637-baed-293830ef469a/2dcacfa7-tour_championship_preds_ch_model.csv"
COLMAP = {"win": "winner", "top_5": "top5", "top_10": "top10", "top_20": "top20"}
model_tiers = {v: {} for v in COLMAP.values()}
with open(CSV, newline="") as fh:
    for row in csv.DictReader(fh):
        raw = row["player_name"]
        last, first = [s.strip() for s in raw.split(",", 1)]
        name = gb.canon(f"{first} {last}")
        for col, tk in COLMAP.items():
            model_tiers[tk][name] = round(float(row[col]), 6)

model = {"source": "DataGolf", "captured_at": gb._ts(), "model": True,
         "race": os.environ["RACE_NAME"], "tiers": model_tiers}
os.makedirs("data/tourchamp/model", exist_ok=True)
with open("data/tourchamp/model/datagolf.json", "w") as fh:
    json.dump(model, fh, indent=2, ensure_ascii=False)
print("wrote model/datagolf.json: " + ", ".join(f"{tk}={len(v)}" for tk, v in model_tiers.items()))
