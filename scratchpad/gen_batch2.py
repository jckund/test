import os
os.environ["RACE_NAME"] = "Brickyard 400 presented by PPG"
import gen_books as gb

# ============ PRIME ============
# Winner intentionally NOT re-entered (drift per CLAUDE.md + Casey Mears obscured);
# existing prime.json winner is kept. Add NEW manufacturer + team boards only.
prime_which = {"Toyota": -180, "Chevrolet": 200, "Ford": 420}   # 3-way; no per-make lists posted
mp = gb.write_mfr("mfr_prime.json", "Prime", prime_which, {})    # makes={} -> which-make only
print("Prime mfr which-make:", {k: v["american"] for k, v in mp["winner"].items()},
      "| makes:", mp["makes"])

prime_team = [
    ("Joe Gibbs Racing", 150), ("Hendrick Motorsports", 250), ("23XI Racing", 350),
    ("Team Penske", 400), ("RFK Racing", 1500), ("Spire Motorsports", 2000),
    ("Legacy Motor Club", 2500), ("Trackhouse Racing", 3000), ("Front Row Motorsports", 8000),
    ("Richard Childress Racing", 12000), ("Kaulig Racing", 15000), ("Wood Brothers Racing", 15000),
    ("Hyak Motorsports", 30000), ("Haas Factory Team", 40000), ("Rick Ware Racing", 40000),
    ("Beard Motorsports", 50000), ("Live Fast Motorsports", 50000),
]
tp = gb.write_team("team_prime.json", "Prime", prime_team)
print("Prime team entries:", len(tp["winner"]))

# ============ BETONLINE (winner; Ricky Stenhouse Jr is LOCKED -> omit) ============
betonline_win = [
    ("Denny Hamlin", 325), ("Kyle Larson", 650), ("Tyler Reddick", 700),
    ("Christopher Bell", 850), ("Ryan Blaney", 1000), ("Chase Briscoe", 1200),
    ("William Byron", 1200), ("Bubba Wallace", 1400), ("Chase Elliott", 1400),
    ("Ty Gibbs", 1600), ("Carson Hocevar", 1800), ("Joey Logano", 1800),
    ("Chris Buescher", 2500), ("Corey Heim", 2500), ("Erik Jones", 2800),
    ("Brad Keselowski", 4000), ("Austin Cindric", 5000), ("Ross Chastain", 5000),
    ("John Hunter Nemechek", 5000), ("Daniel Suarez", 6600), ("Alex Bowman", 6600),
    ("Shane Van Gisbergen", 7500), ("Ryan Preece", 7500), ("Riley Herbst", 15000),
    ("Connor Zilisch", 15000), ("Josh Berry", 15000), ("Michael McDowell", 20000),
    ("Zane Smith", 20000), ("Austin Dillon", 25000), ("Todd Gilliland", 25000),
    ("A.J. Allmendinger", 25000), ("Noah Gragson", 25000), ("Austin Hill", 25000),
    ("Cole Custer", 50000), ("Ty Dillon", 50000), ("Cody Ware", 100000),
    ("Daniel Dye", 150000), ("Casey Mears", 150000),
]
bo = gb.write_book("betonline.json", "BetOnline", {"winner": (betonline_win, 1)})
print("BetOnline winner:", len(bo["tiers"]["winner"]["drivers"]),
      "(Ricky Stenhouse omitted - locked)")

# ============ BETBOSS (winner; Wallace twice -> keep main-grid Darrell +1000) ============
betboss_win = [
    ("Aj Allmendinger", 16000), ("Alex Bowman", 6700), ("Austin Cindric", 5950),
    ("Austin Dillon", 16000), ("Austin Hill", 16000), ("Brad Keselowski", 4250),
    ("Carson Hocevar", 2100), ("Casey Mears", 16000), ("Chase Briscoe", 1200),
    ("Chase Elliott", 1225), ("Chris Buescher", 2600), ("Christopher Bell", 850),
    ("Cody Ware", 16000), ("Cole Custer", 16000), ("Connor Zilisch", 16000),
    ("Corey Heim", 3500), ("Daniel Dye", 16000), ("Daniel Suarez", 7400),
    ("Darrell Wallace Jr", 1000), ("Denny Hamlin", 350), ("Erik Jones", 3250),
    ("Joey Logano", 2250), ("John Hunter Nemechek", 5950), ("Josh Berry", 16000),
    ("Kyle Larson", 650), ("Michael Mcdowell", 16000), ("Noah Gragson", 16000),
    ("Ricky Stenhouse Jr", 16000), ("Riley Herbst", 16000), ("Ross Chastain", 7700),
    ("Ryan Blaney", 1125), ("Ryan Preece", 7700), ("Shane Van Gisbergen", 9950),
    ("Todd Gilliland", 16000), ("Ty Dillon", 16000), ("Ty Gibbs", 1350),
    ("Tyler Reddick", 700), ("William Byron", 1400), ("Zane Smith", 14950),
]
bb = gb.write_book("betboss.json", "BetBoss", {"winner": (betboss_win, 1)})
w = bb["tiers"]["winner"]["drivers"]
print("BetBoss winner:", len(w), "| Wallace:", [x["american"] for x in w if x["name"] == "Bubba Wallace"])
assert len(w) == 39
