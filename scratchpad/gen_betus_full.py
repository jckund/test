import os
os.environ["RACE_NAME"] = "Brickyard 400 presented by PPG"
import gen_books as gb

# --- Winner (34; "others on request") ---
win = [
    ("Denny Hamlin", 350), ("Kyle Larson", 650), ("Tyler Reddick", 800),
    ("Christopher Bell", 800), ("Ryan Blaney", 1000), ("Chase Briscoe", 1200),
    ("William Byron", 1200), ("Chase Elliott", 1400), ("Bubba Wallace", 900),
    ("Ty Gibbs", 1000), ("Carson Hocevar", 1800), ("Joey Logano", 1800),
    ("Chris Buescher", 2500), ("Erik Jones", 2500), ("Brad Keselowski", 4000),
    ("Corey Heim", 2500), ("Austin Cindric", 6000), ("Ross Chastain", 6000),
    ("Alex Bowman", 6600), ("John Hunter Nemechek", 5000), ("Ryan Preece", 7500),
    ("Shane Van Gisbergen", 7500), ("Daniel Suarez", 6600), ("Connor Zilisch", 15000),
    ("Josh Berry", 15000), ("Riley Herbst", 15000), ("Michael McDowell", 20000),
    ("Austin Dillon", 25000), ("AJ Allmendinger", 25000), ("Austin Hill", 25000),
    ("Zane Smith", 25000), ("Noah Gragson", 30000), ("Todd Gilliland", 25000),
    ("Ricky Stenhouse Jr", 40000),
]
# --- Top 3 (39) --- ("Chase Elliot" on board = Chase Elliott typo)
t3 = [
    ("Denny Hamlin", 110), ("Kyle Larson", 220), ("Christopher Bell", 250),
    ("Tyler Reddick", 250), ("Ryan Blaney", 325), ("Chase Briscoe", 400),
    ("William Byron", 400), ("Chase Elliott", 450), ("Bubba Wallace", 320),
    ("Ty Gibbs", 325), ("Joey Logano", 600), ("Carson Hocevar", 600),
    ("Chris Buescher", 800), ("Corey Heim", 800), ("Erik Jones", 800),
    ("Brad Keselowski", 1400), ("John Hunter Nemechek", 1600), ("Ross Chastain", 1800),
    ("Austin Cindric", 1800), ("Daniel Suarez", 2000), ("Alex Bowman", 2000),
    ("Ryan Preece", 2200), ("Shane Van Gisbergen", 2200), ("Josh Berry", 4000),
    ("Riley Herbst", 4000), ("Connor Zilisch", 4000), ("Michael McDowell", 5000),
    ("Austin Dillon", 6000), ("AJ Allmendinger", 6000), ("Austin Hill", 6000),
    ("Zane Smith", 6000), ("Todd Gilliland", 6000), ("Noah Gragson", 8000),
    ("Ricky Stenhouse Jr", 10000), ("Ty Dillon", 22500), ("Cole Custer", 22500),
    ("Cody Ware", 22500), ("Casey Mears", 45000), ("Daniel Dye", 45000),
]
# --- Top 5 (39) ---
t5 = [
    ("Denny Hamlin", -170), ("Kyle Larson", 125), ("Christopher Bell", 150),
    ("Tyler Reddick", 150), ("Ryan Blaney", 180), ("Chase Briscoe", 220),
    ("William Byron", 220), ("Chase Elliott", 250), ("Bubba Wallace", 160),
    ("Ty Gibbs", 180), ("Joey Logano", 300), ("Carson Hocevar", 300),
    ("Chris Buescher", 400), ("Corey Heim", 400), ("Erik Jones", 400),
    ("Brad Keselowski", 650), ("John Hunter Nemechek", 800), ("Ross Chastain", 1000),
    ("Austin Cindric", 1000), ("Daniel Suarez", 1100), ("Alex Bowman", 1100),
    ("Ryan Preece", 1200), ("Shane Van Gisbergen", 1200), ("Josh Berry", 1800),
    ("Riley Herbst", 1800), ("Connor Zilisch", 1800), ("Michael McDowell", 2200),
    ("Austin Dillon", 2800), ("AJ Allmendinger", 2800), ("Austin Hill", 2800),
    ("Zane Smith", 2800), ("Todd Gilliland", 2800), ("Noah Gragson", 3500),
    ("Ricky Stenhouse Jr", 5000), ("Ty Dillon", 12500), ("Cole Custer", 12500),
    ("Cody Ware", 12500), ("Casey Mears", 22500), ("Daniel Dye", 22500),
]
# --- Top 10 (39) --- ("Ev" = Even = +100)
t10 = [
    ("Denny Hamlin", -400), ("Kyle Larson", -265), ("Christopher Bell", -225),
    ("Tyler Reddick", -225), ("Ryan Blaney", -175), ("Chase Briscoe", -160),
    ("William Byron", -160), ("Chase Elliott", -150), ("Bubba Wallace", -200),
    ("Ty Gibbs", -175), ("Joey Logano", 100), ("Carson Hocevar", 100),
    ("Chris Buescher", 140), ("Corey Heim", 140), ("Erik Jones", 140),
    ("Brad Keselowski", 220), ("John Hunter Nemechek", 250), ("Ross Chastain", 280),
    ("Austin Cindric", 280), ("Daniel Suarez", 300), ("Alex Bowman", 300),
    ("Ryan Preece", 350), ("Shane Van Gisbergen", 350), ("Josh Berry", 600),
    ("Riley Herbst", 600), ("Connor Zilisch", 600), ("Michael McDowell", 800),
    ("Austin Dillon", 1000), ("AJ Allmendinger", 1000), ("Austin Hill", 1000),
    ("Zane Smith", 1000), ("Todd Gilliland", 800), ("Noah Gragson", 1200),
    ("Ricky Stenhouse Jr", 1400), ("Ty Dillon", 2500), ("Cole Custer", 2500),
    ("Cody Ware", 2500), ("Casey Mears", 3300), ("Daniel Dye", 3300),
]

b = gb.write_book("betus.json", "BetUS",
                  {"winner": (win, 1), "top3": (t3, 3), "top5": (t5, 5), "top10": (t10, 10)})
for tk in ("winner", "top3", "top5", "top10"):
    d = b["tiers"][tk]
    s = sum(x["novig"] for x in d["drivers"])
    print(f"  {tk}: {len(d['drivers'])} drivers, novig sum={s:.4f} (target {d['number_of_winners']})")

# --- Manufacturer ---
# NOTE: Winning Manufacturer board was truncated at "Ford +50"; read as +500
# (only value giving a sane ~108% 3-way book). FLAG TO USER.
which_make = {"Toyota": -155, "Chevrolet": 225, "Ford": 500}
chevy = [
    ("Kyle Larson", 150), ("William Byron", 300), ("Chase Elliott", 375),
    ("Carson Hocevar", 500), ("Ross Chastain", 1800), ("Daniel Suarez", 2000),
    ("Alex Bowman", 2000), ("Shane Van Gisbergen", 2200), ("Connor Zilisch", 5000),
    ("Michael McDowell", 6000), ("Austin Dillon", 8000), ("AJ Allmendinger", 8000),
    ("Austin Hill", 8000), ("Ricky Stenhouse Jr", 12500), ("Ty Dillon", 30000),
]
ford = [
    ("Ryan Blaney", 115), ("Joey Logano", 275), ("Chris Buescher", 400),
    ("Brad Keselowski", 700), ("Austin Cindric", 1100), ("Ryan Preece", 1400),
    ("Josh Berry", 2800), ("Todd Gilliland", 2800), ("Zane Smith", 3300),
    ("Noah Gragson", 6000), ("Cole Custer", 20000), ("Cody Ware", 20000),
]
toyota = [
    ("Denny Hamlin", 175), ("Christopher Bell", 450), ("Tyler Reddick", 450),
    ("Chase Briscoe", 700), ("Bubba Wallace", 800), ("Ty Gibbs", 1000),
    ("Corey Heim", 1400), ("Erik Jones", 1800), ("John Hunter Nemechek", 3000),
    ("Riley Herbst", 10000),
]
m = gb.write_mfr("mfr_betus.json", "BetUS", which_make,
                 {"Chevrolet": chevy, "Ford": ford, "Toyota": toyota})
print("  mfr which-make:", {k: v["american"] for k, v in m["winner"].items()})
print("  mfr per-make counts:", {k: len(v["drivers"]) for k, v in m["makes"].items()})
