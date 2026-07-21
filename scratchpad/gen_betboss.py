import os
os.environ["RACE_NAME"] = "Brickyard 400 presented by PPG"
import gen_books as gb

# BetBoss Outright Winner, Brickyard 400. Board listed Wallace twice
# (Darrell Wallace Jr +1400 in-grid, Bubba Wallace +1200 appended at bottom);
# keep the main-grid Darrell Wallace Jr entry, drop the duplicate.
betboss_win = [
    ("Aj Allmendinger", 16000), ("Alex Bowman", 6450), ("Austin Cindric", 5950),
    ("Austin Dillon", 16000), ("Austin Hill", 16000), ("Brad Keselowski", 3750),
    ("Carson Hocevar", 2000), ("Casey Mears", 16000), ("Chase Briscoe", 1200),
    ("Chase Elliott", 1300), ("Chris Buescher", 2350), ("Christopher Bell", 880),
    ("Cody Ware", 16000), ("Cole Custer", 16000), ("Connor Zilisch", 16000),
    ("Corey Heim", 4100), ("Daniel Dye", 16000), ("Daniel Suarez", 6950),
    ("Darrell Wallace Jr", 1400), ("Denny Hamlin", 303), ("Erik Jones", 3250),
    ("Joey Logano", 2350), ("John Hunter Nemechek", 6950), ("Josh Berry", 16000),
    ("Kyle Larson", 625), ("Michael Mcdowell", 16000), ("Noah Gragson", 16000),
    ("Ricky Stenhouse Jr", 16000), ("Riley Herbst", 16000), ("Ross Chastain", 6950),
    ("Ryan Blaney", 1060), ("Ryan Preece", 7950), ("Shane Van Gisbergen", 10200),
    ("Todd Gilliland", 16000), ("Ty Dillon", 16000), ("Ty Gibbs", 1500),
    ("Tyler Reddick", 700), ("William Byron", 1300), ("Zane Smith", 16000),
]
b = gb.write_book("betboss.json", "BetBoss", {"winner": (betboss_win, 1)})
w = b["tiers"]["winner"]["drivers"]
print("BetBoss winner drivers:", len(w), "| race:", b["race"],
      "| novig sum:", round(sum(d["novig"] for d in w), 6))
assert len(w) == 39, len(w)
# confirm Wallace canonicalized once
assert sum(1 for d in w if d["name"] == "Bubba Wallace") == 1
print("Wallace ->", [d for d in w if d["name"] == "Bubba Wallace"][0])
