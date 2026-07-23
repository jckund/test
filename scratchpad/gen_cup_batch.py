import os
os.environ["RACE_NAME"] = "Brickyard 400 presented by PPG"
import gen_books as gb

# =========================== CAESARS (W / T3 / T5 / T10 + team) ===========================
# rows: (name, winner, top3, top5, top10)
cae_rows = [
    ("Denny Hamlin", 350, 120, -170, -400), ("Kyle Larson", 650, 200, 120, -320),
    ("Tyler Reddick", 675, 250, 100, -275), ("Ryan Blaney", 850, 300, 150, -240),
    ("Christopher Bell", 900, 275, 140, -240), ("Chase Briscoe", 1000, 325, 150, -250),
    ("William Byron", 1200, 400, 200, -175), ("Chase Elliott", 1200, 400, 200, -150),
    ("Bubba Wallace", 1300, 400, 185, -180), ("Ty Gibbs", 1600, 500, 225, -140),
    ("Carson Hocevar", 1600, 550, 275, -110), ("Joey Logano", 2200, 750, 350, 125),
    ("Chris Buescher", 2800, 800, 375, 120), ("Erik Jones", 3000, 850, 425, 140),
    ("Corey Heim", 3500, 1200, 425, 120), ("Brad Keselowski", 4500, 1200, 500, 180),
    ("Austin Cindric", 5000, 1200, 625, 200), ("John Hunter Nemechek", 6500, 1800, 850, 225),
    ("Alex Bowman", 7500, 2000, 850, 225), ("Ross Chastain", 7500, 2000, 900, 240),
    ("Shane Van Gisbergen", 7500, 2200, 1200, 325), ("Ryan Preece", 8000, 2200, 900, 225),
    ("Daniel Suarez", 8000, 2500, 1000, 275), ("Riley Herbst", 15000, 5000, 2500, 725),
    ("Todd Gilliland", 15000, 3500, 1600, 450), ("Josh Berry", 17500, 4000, 1600, 475),
    ("Michael McDowell", 20000, 8000, 3000, 800), ("Connor Zilisch", 20000, 6000, 2500, 725),
    ("Austin Dillon", 25000, 6000, 2500, 725), ("AJ Allmendinger", 25000, 6500, 2500, 725),
    ("Zane Smith", 25000, 6500, 2000, 675), ("Ricky Stenhouse Jr", 35000, 10000, 4000, 950),
    ("Noah Gragson", 50000, 15000, 6000, 1200), ("Austin Hill", 50000, 15000, 6000, 1200),
    ("Ty Dillon", 100000, 20000, 8000, 2000), ("Cole Custer", 100000, 20000, 7000, 2000),
    ("Casey Mears", 250000, 30000, 20000, 3000), ("Daniel Dye", 250000, 30000, 15000, 2800),
    ("Cody Ware", 250000, 30000, 12500, 3000),
]
cae_win = [(n, r[0]) for n, *r in cae_rows]
cae_t3 = [(n, r[1]) for n, *r in cae_rows]
cae_t5 = [(n, r[2]) for n, *r in cae_rows]
cae_t10 = [(n, r[3]) for n, *r in cae_rows]
team_std = [
    ("Joe Gibbs Racing", 125), ("Hendrick Motorsports", 225), ("23XI Racing", 420),
    ("Team Penske", 650), ("Spire Motorsports", 1400), ("RFK Racing", 1400),
    ("Legacy Motor Club", 2500), ("Trackhouse Racing Team", 3500),
    ("Front Row Motorsports", 12500), ("Wood Brothers Racing", 15000),
    ("Richard Childress Racing", 20000), ("Kaulig Racing", 25000),
    ("Hyak Motorsports", 50000), ("Hass Factory Team", 75000),
    ("Live Fast Motorsports", 200000), ("Rick Ware Racing", 250000), ("Beard Motorsports", 250000),
]
c = gb.write_book("caesars.json", "Caesars",
                  {"winner": (cae_win, 1), "top3": (cae_t3, 3), "top5": (cae_t5, 5), "top10": (cae_t10, 10)})
gb.write_team("team_caesars.json", "Caesars", team_std)
print("CAESARS:", {t: len(c["tiers"][t]["drivers"]) for t in c["tiers"]})
for t in c["tiers"]:
    assert abs(sum(d["novig"] for d in c["tiers"][t]["drivers"]) - c["tiers"][t]["number_of_winners"]) < 1e-6

# =========================== BETBOSS (Cup winner) ===========================
# Wallace listed twice -> keep main-grid Darrell Wallace Jr +1000, drop appended Bubba +1300.
betboss_win = [
    ("Aj Allmendinger", 16000), ("Alex Bowman", 7950), ("Austin Cindric", 6450),
    ("Austin Dillon", 16000), ("Austin Hill", 16000), ("Brad Keselowski", 4250),
    ("Carson Hocevar", 2250), ("Casey Mears", 16000), ("Chase Briscoe", 1050),
    ("Chase Elliott", 1275), ("Chris Buescher", 2750), ("Christopher Bell", 925),
    ("Cody Ware", 16000), ("Cole Custer", 16000), ("Connor Zilisch", 16000),
    ("Corey Heim", 4000), ("Daniel Dye", 16000), ("Daniel Suarez", 6200),
    ("Darrell Wallace Jr", 1000), ("Denny Hamlin", 313), ("Erik Jones", 3250),
    ("Joey Logano", 2500), ("John Hunter Nemechek", 7200), ("Josh Berry", 16000),
    ("Kyle Larson", 638), ("Michael Mcdowell", 16000), ("Noah Gragson", 16000),
    ("Ricky Stenhouse Jr", 16000), ("Riley Herbst", 16000), ("Ross Chastain", 6700),
    ("Ryan Blaney", 1125), ("Ryan Preece", 9450), ("Shane Van Gisbergen", 9950),
    ("Todd Gilliland", 16000), ("Ty Dillon", 16000), ("Ty Gibbs", 1450),
    ("Tyler Reddick", 663), ("William Byron", 1400), ("Zane Smith", 16000),
]
bb = gb.write_book("betboss.json", "BetBoss", {"winner": (betboss_win, 1)})
print("BETBOSS winner:", len(bb["tiers"]["winner"]["drivers"]))
assert len(bb["tiers"]["winner"]["drivers"]) == 39

# =========================== BETUS (W/T3/T5/T10 + mfr + team) ===========================
bu_win = [
    ("Denny Hamlin", 350), ("Kyle Larson", 700), ("Tyler Reddick", 750), ("Christopher Bell", 800),
    ("Bubba Wallace", 1000), ("Ryan Blaney", 1050), ("Chase Briscoe", 1200), ("Chase Elliott", 1250),
    ("Ty Gibbs", 1300), ("William Byron", 1400), ("Carson Hocevar", 2000), ("Joey Logano", 2000),
    ("Chris Buescher", 3000), ("Corey Heim", 3000), ("Erik Jones", 3000), ("Brad Keselowski", 4500),
    ("John Hunter Nemechek", 6000), ("Austin Cindric", 6000), ("Ross Chastain", 7500), ("Alex Bowman", 7500),
    ("Daniel Suarez", 7500), ("Ryan Preece", 7500), ("Shane Van Gisbergen", 7500), ("Connor Zilisch", 15000),
    ("Josh Berry", 20000), ("Riley Herbst", 20000), ("Michael McDowell", 25000), ("Austin Dillon", 25000),
    ("AJ Allmendinger", 25000), ("Austin Hill", 25000), ("Zane Smith", 25000), ("Todd Gilliland", 25000),
    ("Ricky Stenhouse Jr", 40000), ("Noah Gragson", 50000),
]
bu_t3 = [
    ("Denny Hamlin", 110), ("Kyle Larson", 220), ("Christopher Bell", 250), ("Tyler Reddick", 250),
    ("Ryan Blaney", 325), ("Chase Briscoe", 400), ("William Byron", 400), ("Chase Elliott", 450),
    ("Bubba Wallace", 320), ("Ty Gibbs", 325), ("Joey Logano", 600), ("Carson Hocevar", 600),
    ("Chris Buescher", 800), ("Corey Heim", 800), ("Erik Jones", 800), ("Brad Keselowski", 1400),
    ("John Hunter Nemechek", 1600), ("Ross Chastain", 1800), ("Austin Cindric", 1800), ("Daniel Suarez", 2000),
    ("Alex Bowman", 2000), ("Ryan Preece", 2200), ("Shane Van Gisbergen", 2200), ("Josh Berry", 4000),
    ("Riley Herbst", 4000), ("Connor Zilisch", 4000), ("Michael McDowell", 5000), ("Austin Dillon", 6000),
    ("AJ Allmendinger", 6000), ("Austin Hill", 6000), ("Zane Smith", 6000), ("Todd Gilliland", 6000),
    ("Noah Gragson", 8000), ("Ricky Stenhouse Jr", 10000), ("Ty Dillon", 22500), ("Cole Custer", 22500),
    ("Cody Ware", 22500), ("Casey Mears", 45000), ("Daniel Dye", 45000),
]
bu_t5 = [
    ("Denny Hamlin", -170), ("Kyle Larson", 125), ("Christopher Bell", 150), ("Tyler Reddick", 150),
    ("Ryan Blaney", 180), ("Chase Briscoe", 210), ("William Byron", 220), ("Chase Elliott", 250),
    ("Bubba Wallace", 160), ("Ty Gibbs", 180), ("Joey Logano", 300), ("Carson Hocevar", 300),
    ("Chris Buescher", 400), ("Corey Heim", 400), ("Erik Jones", 400), ("Brad Keselowski", 650),
    ("John Hunter Nemechek", 800), ("Ross Chastain", 1000), ("Austin Cindric", 1000), ("Daniel Suarez", 1100),
    ("Alex Bowman", 1100), ("Ryan Preece", 800), ("Shane Van Gisbergen", 800), ("Josh Berry", 1800),
    ("Riley Herbst", 1800), ("Connor Zilisch", 1800), ("Michael McDowell", 2200), ("Austin Dillon", 2800),
    ("AJ Allmendinger", 2800), ("Austin Hill", 2800), ("Zane Smith", 2500), ("Todd Gilliland", 2200),
    ("Noah Gragson", 3500), ("Ricky Stenhouse Jr", 5000), ("Ty Dillon", 12500), ("Cole Custer", 12500),
    ("Cody Ware", 12500), ("Casey Mears", 22500), ("Daniel Dye", 22500),
]
bu_t10 = [
    ("Denny Hamlin", -400), ("Kyle Larson", -265), ("Christopher Bell", -225), ("Tyler Reddick", -225),
    ("Ryan Blaney", -175), ("Chase Briscoe", -160), ("William Byron", -160), ("Chase Elliott", -150),
    ("Bubba Wallace", -200), ("Ty Gibbs", -175), ("Joey Logano", 100), ("Carson Hocevar", 100),
    ("Chris Buescher", 140), ("Corey Heim", 140), ("Erik Jones", 140), ("Brad Keselowski", 220),
    ("John Hunter Nemechek", 250), ("Ross Chastain", 280), ("Austin Cindric", 280), ("Daniel Suarez", 300),
    ("Alex Bowman", 300), ("Ryan Preece", 325), ("Shane Van Gisbergen", 325), ("Josh Berry", 600),
    ("Riley Herbst", 600), ("Connor Zilisch", 600), ("Michael McDowell", 800), ("Austin Dillon", 1100),
    ("AJ Allmendinger", 1100), ("Austin Hill", 1100), ("Zane Smith", 650), ("Todd Gilliland", 800),
    ("Noah Gragson", 1300), ("Ricky Stenhouse Jr", 1400), ("Ty Dillon", 2500), ("Cole Custer", 2200),
    ("Cody Ware", 2500), ("Casey Mears", 3300), ("Daniel Dye", 3300),
]
bu = gb.write_book("betus.json", "BetUS",
                   {"winner": (bu_win, 1), "top3": (bu_t3, 3), "top5": (bu_t5, 5), "top10": (bu_t10, 10)})
print("BETUS:", {t: len(bu["tiers"][t]["drivers"]) for t in bu["tiers"]})

# BetUS manufacturer
which = {"Toyota": -155, "Chevrolet": 225, "Ford": 500}
chevy = [("Kyle Larson", 175), ("William Byron", 245), ("Chase Elliott", 350), ("Carson Hocevar", 700),
    ("Shane Van Gisbergen", 1800), ("Ross Chastain", 2200), ("Alex Bowman", 2200), ("Daniel Suarez", 2500),
    ("Connor Zilisch", 4000), ("Michael McDowell", 5500), ("AJ Allmendinger", 6000), ("Austin Hill", 6500),
    ("Austin Dillon", 6500), ("Ricky Stenhouse Jr", 10000), ("Ty Dillon", 13000), ("Cole Custer", 13000),
    ("Cody Ware", 13000), ("Daniel Dye", 17000), ("Casey Mears", 17000)]
ford = [("Ryan Blaney", 115), ("Joey Logano", 360), ("Chris Buescher", 450), ("Austin Cindric", 1000),
    ("Brad Keselowski", 1100), ("Ryan Preece", 1500), ("Josh Berry", 3000), ("Zane Smith", 3000),
    ("Todd Gilliland", 4500), ("Noah Gragson", 6500)]
toyota = [("Denny Hamlin", 230), ("Tyler Reddick", 285), ("Christopher Bell", 550), ("Chase Briscoe", 550),
    ("Bubba Wallace", 1000), ("Ty Gibbs", 1100), ("Erik Jones", 2000), ("Corey Heim", 2500),
    ("John Hunter Nemechek", 3500), ("Riley Herbst", 6500)]
m = gb.write_mfr("mfr_betus.json", "BetUS", which, {"Chevrolet": chevy, "Ford": ford, "Toyota": toyota})
print("BETUS mfr:", {k: v["american"] for k, v in m["winner"].items()},
      "| per-make:", {k: len(v["drivers"]) for k, v in m["makes"].items()})

# BetUS Team of Race Winner (partial board, 13 teams; "others on request")
bu_team = [("Joe Gibbs Racing", 120), ("Hendrick Motorsports", 280), ("23XI Racing", 350),
    ("Team Penske", 600), ("RFK Racing", 1600), ("Spire Motorsports", 1600), ("Legacy Motor Club", 2200),
    ("Trackhouse Racing", 3300), ("Front Row Motorsports", 10000), ("Richard Childress Racing", 12500),
    ("Kaulig Racing", 20000), ("Wood Brothers Racing", 20000), ("Hyak Motorsports", 40000)]
tm = gb.write_team("team_betus.json", "BetUS", bu_team)
print("BETUS team:", len(tm["winner"]))

# =========================== CAESARS manufacturer (per-make only; no which-make 3-way posted) ===========================
cae_chevy = [("Kyle Larson", 150), ("William Byron", 280), ("Chase Elliott", 300), ("Carson Hocevar", 525),
    ("Daniel Suarez", 2200), ("Alex Bowman", 2200), ("Ross Chastain", 2200), ("Shane Van Gisbergen", 2500),
    ("Austin Dillon", 5500), ("Connor Zilisch", 6000), ("AJ Allmendinger", 6000), ("Michael McDowell", 8500),
    ("Ricky Stenhouse Jr", 10000), ("Cody Ware", 15000), ("Austin Hill", 15000), ("Ty Dillon", 25000),
    ("Casey Mears", 30000), ("Daniel Dye", 30000)]
cae_ford = [("Ryan Blaney", 140), ("Chris Buescher", 325), ("Joey Logano", 325), ("Brad Keselowski", 725),
    ("Austin Cindric", 750), ("Ryan Preece", 1400), ("Todd Gilliland", 2800), ("Josh Berry", 2800),
    ("Zane Smith", 3000)]
cae_toyota = [("Denny Hamlin", 175), ("Tyler Reddick", 350), ("Christopher Bell", 525), ("Chase Briscoe", 550),
    ("Bubba Wallace", 725), ("Ty Gibbs", 875), ("Corey Heim", 1500), ("Erik Jones", 2000),
    ("John Hunter Nemechek", 4000), ("Riley Herbst", 10000)]
mc = gb.write_mfr("mfr_caesars.json", "Caesars", {},
                  {"Chevrolet": cae_chevy, "Ford": cae_ford, "Toyota": cae_toyota})
print("CAESARS mfr per-make:", {k: len(v["drivers"]) for k, v in mc["makes"].items()}, "| which-make:", mc["winner"])
print("OK")
