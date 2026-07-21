import os
os.environ["RACE_NAME"] = "Brickyard 400 presented by PPG"
import gen_books as gb

prime_win = [
    ("Denny Hamlin", 350), ("Tyler Reddick", 475), ("Ryan Blaney", 650),
    ("Kyle Larson", 675), ("William Byron", 850), ("Chase Briscoe", 950),
    ("Christopher Bell", 950), ("Chase Elliott", 1100), ("Joey Logano", 1300),
    ("Bubba Wallace", 1400), ("Chris Buescher", 1500), ("Ty Gibbs", 1500),
    ("Carson Hocevar", 1800), ("Erik Jones", 3300), ("Austin Cindric", 4000),
    ("Brad Keselowski", 4500), ("Corey Heim", 4500), ("Shane Van Gisbergen", 5500),
    ("John Hunter Nemechek", 6500), ("Alex Bowman", 7000), ("Ross Chastain", 7000),
    ("Daniel Suarez", 8000), ("Ryan Preece", 8000), ("Riley Herbst", 11000),
    ("Connor Zilisch", 13000), ("Josh Berry", 13000), ("Michael McDowell", 17000),
    ("AJ Allmendinger", 18000), ("Zane Smith", 18000), ("Austin Dillon", 20000),
    ("Austin Hill", 20000), ("Todd Gilliland", 20000), ("Noah Gragson", 25000),
    ("Ricky Stenhouse Jr", 30000), ("Cody Ware", 40000), ("Cole Custer", 40000),
    ("Ty Dillon", 40000), ("Casey Mears", 50000), ("Daniel Dye", 50000),
]
p = gb.write_book("prime.json", "Prime", {"winner": (prime_win, 1)})
n = len(p["tiers"]["winner"]["drivers"])
s = sum(d["novig"] for d in p["tiers"]["winner"]["drivers"])
print("Prime winner drivers:", n, "| race:", p["race"], "| novig sum:", round(s, 6))
assert n == 39, n
