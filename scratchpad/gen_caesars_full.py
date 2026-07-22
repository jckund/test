import os
os.environ["RACE_NAME"] = "Brickyard 400 presented by PPG"
import gen_books as gb

# (name, winner, top3)
rows = [
    ("Denny Hamlin", 350, 120), ("Kyle Larson", 650, 200), ("Tyler Reddick", 700, 250),
    ("Christopher Bell", 900, 275), ("Ryan Blaney", 1000, 300), ("William Byron", 1200, 400),
    ("Chase Briscoe", 1200, 325), ("Chase Elliott", 1200, 400), ("Bubba Wallace", 1300, 400),
    ("Ty Gibbs", 1600, 525), ("Carson Hocevar", 1600, 550), ("Joey Logano", 2000, 750),
    ("Chris Buescher", 2500, 800), ("Erik Jones", 3000, 850), ("Brad Keselowski", 4000, 1200),
    ("Corey Heim", 4500, 1200), ("Austin Cindric", 5000, 1200), ("John Hunter Nemechek", 6500, 1800),
    ("Alex Bowman", 7000, 2000), ("Ross Chastain", 7000, 2000), ("Shane Van Gisbergen", 7500, 2800),
    ("Ryan Preece", 8000, 2200), ("Daniel Suarez", 8000, 2500), ("Riley Herbst", 15000, 5000),
    ("Josh Berry", 17500, 4000), ("Michael McDowell", 20000, 8000), ("Todd Gilliland", 20000, 3500),
    ("Connor Zilisch", 20000, 6000), ("Austin Dillon", 25000, 6000), ("AJ Allmendinger", 25000, 6500),
    ("Zane Smith", 25000, 6500), ("Ricky Stenhouse Jr", 35000, 10000), ("Noah Gragson", 50000, 15000),
    ("Austin Hill", 50000, 15000), ("Ty Dillon", 100000, 20000), ("Cole Custer", 125000, 20000),
    ("Casey Mears", 250000, 30000), ("Daniel Dye", 250000, 30000), ("Cody Ware", 250000, 30000),
]
win = [(n, w) for (n, w, _t) in rows]
t3 = [(n, t) for (n, _w, t) in rows]

team = [
    ("Joe Gibbs Racing", 125), ("Hendrick Motorsports", 225), ("23XI Racing", 420),
    ("Team Penske", 650), ("Spire Motorsports", 1400), ("RFK Racing", 1400),
    ("Legacy Motor Club", 2500), ("Trackhouse Racing Team", 3500),
    ("Front Row Motorsports", 12500), ("Wood Brothers Racing", 15000),
    ("Richard Childress Racing", 20000), ("Kaulig Racing", 25000),
    ("Hyak Motorsports", 50000), ("Hass Factory Team", 75000),
    ("Live Fast Motorsports", 200000), ("Rick Ware Racing", 250000),
    ("Beard Motorsports", 250000),
]

c = gb.write_book("caesars.json", "Caesars", {"winner": (win, 1), "top3": (t3, 3)})
for tk in ("winner", "top3"):
    d = c["tiers"][tk]
    print(f"  {tk}: {len(d['drivers'])} drivers, novig sum={sum(x['novig'] for x in d['drivers']):.4f}")
tm = gb.write_team("team_caesars.json", "Caesars", team)
print("  team entries:", len(tm["winner"]))
