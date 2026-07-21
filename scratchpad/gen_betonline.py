import os
os.environ["RACE_NAME"] = "Brickyard 400 presented by PPG"
import gen_books as gb

betonline_win = [
    ("Denny Hamlin", 350), ("Kyle Larson", 650), ("Tyler Reddick", 800),
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
    ("Ricky Stenhouse Jr", 40000), ("Cole Custer", 50000), ("Ty Dillon", 50000),
    ("Cody Ware", 100000), ("Daniel Dye", 150000), ("Casey Mears", 150000),
]
b = gb.write_book("betonline.json", "BetOnline", {"winner": (betonline_win, 1)})
w = b["tiers"]["winner"]["drivers"]
print("BetOnline winner drivers:", len(w), "| race:", b["race"],
      "| novig sum:", round(sum(d["novig"] for d in w), 6))
assert len(w) == 39, len(w)
