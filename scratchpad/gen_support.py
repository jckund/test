import sys; sys.path.insert(0, "/tmp/claude-0/-home-user-test/3914d24d-32ea-5700-a54f-0ad2d863e192/scratchpad")
import seriesgen as sg

XF = "Pennzoil 250 presented by Take 5 Oil Change"
TR = "TSport 200 presented by Warn Industries"

# ===================== XFINITY / PENNZOIL 250 =====================
betus_xf_w = [("Justin Allgaier",350),("Sam Mayer",400),("Chase Elliott",400),("Brent Crews",800),("Ross Chastain",900),
 ("Carson Kvapil",1200),("Sheldon Creed",1400),("Jesse Love",1600),("Austin Hill",1800),("Corey Day",1800),
 ("Taylor Gray",1800),("Brandon Jones",2000),("Sammy Smith",2500),("Rajah Caruth",3000),("William Sawalich",3000),
 ("Parker Retzlaff",3500),("Ryan Sieg",5000),("Nicholas Sanchez",5000),("Anthony Alfredo",7500),("Harrison Burton",10000),
 ("Dean Thompson",20000),("Jeb Burton",20000),("Jeremy Clements",20000),("Patrick Staropoli",40000),
 ("Preston Pardus",40000),("Kyle Sieg",50000)]
betus_xf_t3 = [("Justin Allgaier",110),("Sam Mayer",140),("Chase Elliott",140),("Brent Crews",250),("Ross Chastain",275),
 ("Carson Kvapil",400),("Sheldon Creed",450),("Jesse Love",500),("Austin Hill",600),("Corey Day",600),("Taylor Gray",600),
 ("Brandon Jones",650),("Sammy Smith",800),("Rajah Caruth",1000),("William Sawalich",1000),("Parker Retzlaff",1200),
 ("Ryan Sieg",1600),("Nicholas Sanchez",1600),("Anthony Alfredo",2200),("Harrison Burton",3000),("Dean Thompson",5000),
 ("Jeb Burton",5000),("Jeremy Clements",5000),("Patrick Staropoli",10000),("Preston Pardus",10000),("Kyle Sieg",15000),
 ("Blaine Perkins",22500),("Brennan Poole",22500),("Ryan Ellis",45000),("Josh Bilicki",45000),("Garrett Smithley",50000),
 ("JJ Yeley",50000),("Nathan Byrd",50000),("Lavar Scott",50000),("Blake Lothian",50000),("Joey Gase",50000),("Dawson Cram",50000)]
betus_xf_t5 = [("Justin Allgaier",-170),("Sam Mayer",-130),("Chase Elliott",-130),("Brent Crews",150),("Ross Chastain",110),
 ("Carson Kvapil",150),("Sheldon Creed",250),("Jesse Love",275),("Austin Hill",300),("Corey Day",300),("Taylor Gray",300),
 ("Brandon Jones",325),("Sammy Smith",400),("Rajah Caruth",500),("William Sawalich",500),("Parker Retzlaff",600),
 ("Ryan Sieg",800),("Nicholas Sanchez",800),("Anthony Alfredo",1200),("Harrison Burton",1400),("Dean Thompson",2200),
 ("Jeb Burton",2200),("Jeremy Clements",2200),("Patrick Staropoli",5000),("Preston Pardus",5000),("Kyle Sieg",6600),
 ("Blaine Perkins",12500),("Brennan Poole",12500),("Ryan Ellis",22500),("Josh Bilicki",22500),("Garrett Smithley",27500),
 ("JJ Yeley",27500),("Nathan Byrd",27500),("Lavar Scott",25000),("Blake Lothian",27500),("Joey Gase",27500),("Dawson Cram",27500)]
sg.write_book("xfinity","betus.json","BetUS",XF,{"winner":(betus_xf_w,1),"top3":(betus_xf_t3,3),"top5":(betus_xf_t5,5)})

cae_xf_w=[("Justin Allgaier",350),("Chase Elliott",400),("Sam Mayer",475),("Ross Chastain",750),("Brent Crews",800),
 ("Corey Day",1200),("Carson Kvapil",1200),("Sheldon Creed",1600),("Austin Hill",1600),("Jesse Love",1600),("Taylor Gray",1600),
 ("Brandon Jones",1800),("Sammy Smith",3300),("William Sawalich",4000),("Rajah Caruth",4500),("Parker Retzlaff",5000),
 ("Ryan Sieg",5000),("Nicholas Sanchez",6500),("Anthony Alfredo",7000),("Harrison Burton",8000),("Jeremy Clements",15000),
 ("Dean Thompson",20000),("Jeb Burton",25000),("Patrick Staropoli",35000),("Kyle Sieg",75000),("Preston Pardus",75000),
 ("Brennan Poole",100000),("Blaine Perkins",100000),("Ryan Ellis",100000),("Josh Bilicki",100000),("Garrett Smithley",125000),
 ("Blake Lothian",150000),("Lavar Scott",150000),("JJ Yeley",150000),("Dawson Cram",150000)]
cae_xf_t3=[("Justin Allgaier",130),("Chase Elliott",125),("Sam Mayer",140),("Ross Chastain",260),("Brent Crews",260),
 ("Corey Day",250),("Carson Kvapil",250),("Sheldon Creed",375),("Austin Hill",450),("Jesse Love",325),("Taylor Gray",500),
 ("Brandon Jones",550),("Sammy Smith",700),("William Sawalich",1000),("Rajah Caruth",1000),("Parker Retzlaff",1100),
 ("Ryan Sieg",1000),("Nicholas Sanchez",1400),("Anthony Alfredo",1800),("Harrison Burton",2200),("Jeremy Clements",4500),
 ("Dean Thompson",4000),("Jeb Burton",4500),("Patrick Staropoli",8000),("Kyle Sieg",10000),("Preston Pardus",10000),
 ("Brennan Poole",25000),("Blaine Perkins",25000),("Ryan Ellis",25000),("Josh Bilicki",25000),("Garrett Smithley",25000),
 ("Blake Lothian",30000),("Lavar Scott",30000),("JJ Yeley",30000),("Dawson Cram",30000)]
cae_xf_t5=[("Justin Allgaier",-160),("Chase Elliott",-150),("Sam Mayer",-135),("Ross Chastain",130),("Brent Crews",130),
 ("Corey Day",160),("Carson Kvapil",160),("Sheldon Creed",170),("Austin Hill",200),("Jesse Love",155),("Taylor Gray",225),
 ("Brandon Jones",275),("Sammy Smith",325),("William Sawalich",500),("Rajah Caruth",475),("Parker Retzlaff",475),
 ("Ryan Sieg",475),("Nicholas Sanchez",750),("Anthony Alfredo",900),("Harrison Burton",1000),("Jeremy Clements",2000),
 ("Dean Thompson",1600),("Jeb Burton",2000),("Patrick Staropoli",3000),("Kyle Sieg",5000),("Preston Pardus",4500),
 ("Brennan Poole",12000),("Blaine Perkins",10000),("Ryan Ellis",12500),("Josh Bilicki",12500),("Garrett Smithley",12500),
 ("Blake Lothian",12500),("Lavar Scott",12500),("JJ Yeley",12500),("Dawson Cram",15000)]
sg.write_book("xfinity","caesars.json","Caesars",XF,{"winner":(cae_xf_w,1),"top3":(cae_xf_t3,3),"top5":(cae_xf_t5,5)})

prime_xf_w=[("Justin Allgaier",300),("Chase Elliott",370),("Sam Mayer",550),("Ross Chastain",750),("Brent Crews",800),
 ("Carson Kvapil",980),("Jesse Love",1410),("Sheldon Creed",1410),("Austin Hill",1510),("Corey Day",1510),("Taylor Gray",1610),
 ("Brandon Jones",1810),("Sammy Smith",2815),("William Sawalich",3520),("Parker Retzlaff",5025),("Rajah Caruth",5025),
 ("Ryan Sieg",5025),("Nicholas Sanchez",5530),("Anthony Alfredo",7035),("Harrison Burton",8040),("Jeb Burton",20100),
 ("Jeremy Clements",20100),("Dean Thompson",25120),("Patrick Staropoli",35170),("Preston Pardus",50240),("Kyle Sieg",55270),
 ("Blaine Perkins",90440),("Brennan Poole",90440),("Joey Gase",100483),("Josh Bilicki",100483),("Lavar Scott",100483),
 ("Nathan Byrd",100483),("Ryan Ellis",100485),("Blake Lothian",105508),("Dawson Cram",105508),("Garrett Smithley",105508),("JJ Yeley",105508)]
sg.write_book("xfinity","prime.json","Prime",XF,{"winner":(prime_xf_w,1)})

# ===================== TRUCK / TSPORT 200 =====================
# Kalshi spellings: Giovanni Ruggiero, Nicholas Sanchez, Tanner Gray, Mini Tyrrell, Andres Perez De Lara, Corey LaJoie
betus_tr_w=[("Layne Riggs",275),("Chandler Smith",375),("Kaden Honeycutt",500),("Ty Majeski",750),("Christian Eckes",1100),
 ("Connor Mosack",1200),("Nicholas Sanchez",1200),("Giovanni Ruggiero",1700),("Harrison Burton",2200),("Grant Enfinger",2200),
 ("Tyler Ankrum",3000),("Landen Lewis",3300),("Ben Rhodes",3300),("Gavan Boschele",3500),("Daniel Hemric",4500),
 ("Stewart Friesen",4500),("Jake Garcia",4500),("Tanner Gray",7000),("Michael Christopher",10000),("Jonathan Shafer",10000),
 ("Cole Butcher",15000),("Justin Haley",15000),("Corey LaJoie",15000),("Brenden Queen",20000),("Conor Daly",20000),
 ("Andres Perez De Lara",20000),("Derek Lemke",50000),("Dawson Sutton",50000),("Kris Wright",50000),("Jackson MacEnko",50000)]
betus_tr_t3=[("Layne Riggs",-160),("Chandler Smith",125),("Kaden Honeycutt",140),("Ty Majeski",180),("Christian Eckes",300),
 ("Connor Mosack",325),("Nicholas Sanchez",425),("Giovanni Ruggiero",450),("Harrison Burton",650),("Grant Enfinger",650),
 ("Tyler Ankrum",900),("Landen Lewis",1000),("Ben Rhodes",1100),("Gavan Boschele",1100),("Daniel Hemric",1300),
 ("Stewart Friesen",1400),("Jake Garcia",1400),("Tanner Gray",1800),("Michael Christopher",2800),("Jonathan Shafer",2800),
 ("Cole Butcher",4000),("Justin Haley",4000),("Corey LaJoie",4000),("Brenden Queen",5000),("Conor Daly",5000),
 ("Andres Perez De Lara",5000),("Derek Lemke",15000),("Dawson Sutton",15000),("Kris Wright",15000),("Jackson MacEnko",15000),
 ("Cassten Everidge",17500),("Mini Tyrrell",35000),("Toni Breidinger",45000),("Frankie Muniz",50000),("Timmy Hill",50000),
 ("Spencer Boyd",50000),("Justin S Carroll",50000)]
betus_tr_t5=[("Layne Riggs",-265),("Chandler Smith",-165),("Kaden Honeycutt",-140),("Ty Majeski",105),("Christian Eckes",150),
 ("Connor Mosack",175),("Nicholas Sanchez",230),("Giovanni Ruggiero",230),("Harrison Burton",325),("Grant Enfinger",325),
 ("Tyler Ankrum",400),("Landen Lewis",400),("Ben Rhodes",450),("Gavan Boschele",450),("Daniel Hemric",550),
 ("Stewart Friesen",575),("Jake Garcia",575),("Tanner Gray",800),("Michael Christopher",1100),("Jonathan Shafer",1100),
 ("Cole Butcher",1700),("Justin Haley",1700),("Corey LaJoie",1700),("Brenden Queen",2200),("Conor Daly",2200),
 ("Andres Perez De Lara",2200),("Derek Lemke",6600),("Dawson Sutton",6600),("Kris Wright",6600),("Jackson MacEnko",6600),
 ("Cassten Everidge",9000),("Mini Tyrrell",17500),("Toni Breidinger",22500),("Frankie Muniz",27500),("Timmy Hill",27500),
 ("Spencer Boyd",27500),("Justin S Carroll",27500)]
sg.write_book("truck","betus.json","BetUS",TR,{"winner":(betus_tr_w,1),"top3":(betus_tr_t3,3),"top5":(betus_tr_t5,5)})

prime_tr_w=[("Layne Riggs",200),("Chandler Smith",300),("Kaden Honeycutt",555),("Ty Majeski",630),("Christian Eckes",1010),
 ("Connor Mosack",1210),("Nicholas Sanchez",1210),("Giovanni Ruggiero",2010),("Grant Enfinger",2520),("Harrison Burton",2825),
 ("Tyler Ankrum",3030),("Landen Lewis",3530),("Stewart Friesen",4035),("Ben Rhodes",4540),("Daniel Hemric",4540),
 ("Gavan Boschele",4540),("Jake Garcia",6050),("Parker Eatmon",7560),("Tanner Gray",7560),("Jonathan Shafer",10080),
 ("Justin Haley",10080),("Michael Christopher",10080),("Corey LaJoie",12100),("Brenden Queen",15120),("Cole Butcher",15120),
 ("Conor Daly",15120),("Andres Perez De Lara",20155),("Jackson MacEnko",50380),("Kris Wright",50380),("Dawson Sutton",55415),
 ("Derek Lemke",55415),("Cassten Everidge",75570),("Frankie Muniz",100750),("Justin S Carroll",100750),("Mini Tyrrell",100750),
 ("Spencer Boyd",100750),("Timmy Hill",100750),("Toni Breidinger",100750)]
sg.write_book("truck","prime.json","Prime",TR,{"winner":(prime_tr_w,1)})

betboss_tr_w=[("Layne Riggs",208),("Chandler Smith",345),("Kaden Honeycutt",518),("Ty Majeski",595),("Christian Eckes",1105),
 ("Connor Mosack",1400),("Nicholas Sanchez",1200),("Giovanni Ruggiero",1600),("Grant Enfinger",2800),("Harrison Burton",3050),
 ("Tyler Ankrum",3150),("Landen Lewis",3050),("Ben Rhodes",4050),("Daniel Hemric",4250),("Gavan Boschele",5000),
 ("Stewart Friesen",4750),("Jake Garcia",5250),("Tanner Gray",8200),("Michael Christopher",11200),("Jonathan Shafer",12450),
 ("Justin Haley",9900),("Corey LaJoie",16000),("Brenden Queen",16000),("Cole Butcher",14950),("Conor Daly",16000),
 ("Andres Perez De Lara",16000),("Derek Lemke",16000),("Dawson Sutton",16000),("Kris Wright",16000),("Jackson MacEnko",16000),
 ("Cassten Everidge",16000),("Mini Tyrrell",16000),("Frankie Muniz",16000),("Justin S Carroll",16000),("Spencer Boyd",16000),
 ("Timmy Hill",16000),("Toni Breidinger",16000),("Parker Eatmon",7900)]
sg.write_book("truck","betboss.json","BetBoss",TR,{"winner":(betboss_tr_w,1)})

cae_tr_w=[("Layne Riggs",230),("Chandler Smith",425),("Ty Majeski",575),("Kaden Honeycutt",600),("Christian Eckes",800),
 ("Connor Mosack",1200),("Nicholas Sanchez",1400),("Giovanni Ruggiero",2000),("Grant Enfinger",2800),("Harrison Burton",3000),
 ("Landen Lewis",3300),("Tyler Ankrum",3300),("Stewart Friesen",3500),("Daniel Hemric",4500),("Gavan Boschele",4500),
 ("Ben Rhodes",4500),("Jake Garcia",6000),("Tanner Gray",7500),("Parker Eatmon",7500),("Michael Christopher",10000),
 ("Justin Haley",10000),("Corey LaJoie",12500),("Jonathan Shafer",12500),("Brenden Queen",15000),("Cole Butcher",15000),
 ("Conor Daly",17500),("Andres Perez De Lara",20000),("Dawson Sutton",50000),("Kris Wright",50000),("Derek Lemke",50000),
 ("Jackson MacEnko",50000),("Cassten Everidge",75000),("Mini Tyrrell",100000),("Justin S Carroll",150000)]
cae_tr_t3=[("Layne Riggs",-140),("Chandler Smith",105),("Ty Majeski",125),("Kaden Honeycutt",160),("Christian Eckes",250),
 ("Connor Mosack",375),("Nicholas Sanchez",375),("Giovanni Ruggiero",525),("Grant Enfinger",575),("Harrison Burton",725),
 ("Landen Lewis",825),("Tyler Ankrum",825),("Stewart Friesen",1000),("Daniel Hemric",1200),("Gavan Boschele",1200),
 ("Ben Rhodes",1200),("Jake Garcia",1400),("Tanner Gray",2200),("Parker Eatmon",2200),("Michael Christopher",3300),
 ("Justin Haley",2800),("Corey LaJoie",2800),("Jonathan Shafer",5000),("Brenden Queen",4000),("Cole Butcher",4000),
 ("Conor Daly",4000),("Andres Perez De Lara",5000),("Dawson Sutton",12500),("Kris Wright",12500),("Derek Lemke",12500),
 ("Jackson MacEnko",12500),("Cassten Everidge",17500),("Mini Tyrrell",22500),("Justin S Carroll",30000)]
cae_tr_t5=[("Layne Riggs",-260),("Chandler Smith",-200),("Ty Majeski",-180),("Kaden Honeycutt",-130),("Christian Eckes",120),
 ("Connor Mosack",180),("Nicholas Sanchez",190),("Giovanni Ruggiero",240),("Grant Enfinger",260),("Harrison Burton",325),
 ("Landen Lewis",375),("Tyler Ankrum",375),("Stewart Friesen",375),("Daniel Hemric",525),("Gavan Boschele",525),
 ("Ben Rhodes",525),("Jake Garcia",725),("Tanner Gray",1000),("Parker Eatmon",1000),("Michael Christopher",1400),
 ("Justin Haley",1200),("Corey LaJoie",1400),("Jonathan Shafer",2000),("Brenden Queen",1600),("Cole Butcher",1600),
 ("Conor Daly",700),("Andres Perez De Lara",2500),("Dawson Sutton",5500),("Kris Wright",5000),("Derek Lemke",5500),
 ("Jackson MacEnko",5500),("Cassten Everidge",7500),("Mini Tyrrell",10000),("Justin S Carroll",15000)]
sg.write_book("truck","caesars.json","Caesars",TR,{"winner":(cae_tr_w,1),"top3":(cae_tr_t3,3),"top5":(cae_tr_t5,5)})
print("DONE support-series")
