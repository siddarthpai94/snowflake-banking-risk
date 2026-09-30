"""Reference word lists for the synthetic generator.

Names are common US given names and surnames used only as vocabulary; every
person the generator builds is fictional. Towns are invented.
"""

FIRST_MALE = """James John Robert Michael William David Richard Joseph Thomas Charles
Christopher Daniel Matthew Anthony Mark Donald Steven Paul Andrew Joshua Kenneth Kevin
Brian George Timothy Ronald Edward Jason Jeffrey Ryan Jacob Gary Nicholas Eric Jonathan
Stephen Larry Justin Scott Brandon Benjamin Samuel Gregory Alexander Frank Patrick Raymond
Jack Dennis Jerry Tyler Aaron Jose Adam Nathan Henry Douglas Zachary Peter Kyle Ethan
Walter Noah Jeremy Christian Keith Roger Terry Gerald Harold Sean Austin Carl Arthur
Lawrence Dylan Jesse Jordan Bryan Billy Joe Bruce Gabriel Logan Albert Willie Alan Juan
Wayne Elijah Randy Roy Vincent Ralph Eugene Russell Bobby Mason Philip Louis Luis Carlos
Miguel Omar Rahul Vikram Wei Hiroshi Tariq Andre Marcus Darnell""".split()

FIRST_FEMALE = """Mary Patricia Jennifer Linda Elizabeth Barbara Susan Jessica Sarah Karen
Lisa Nancy Betty Margaret Sandra Ashley Kimberly Emily Donna Michelle Carol Amanda Dorothy
Melissa Deborah Stephanie Rebecca Sharon Laura Cynthia Kathleen Amy Angela Shirley Anna
Brenda Pamela Emma Nicole Helen Samantha Katherine Christine Debra Rachel Carolyn Janet
Catherine Maria Heather Diane Ruth Julie Olivia Joyce Virginia Victoria Kelly Lauren
Christina Joan Evelyn Judith Megan Andrea Cheryl Hannah Jacqueline Martha Gloria Teresa
Ann Sara Madison Frances Kathryn Janice Jean Abigail Alice Judy Sophia Grace Denise Amber
Doris Marilyn Danielle Beverly Isabella Theresa Diana Natalie Brittany Charlotte Marie
Kayla Alexis Lori Priya Mei Yuki Fatima Aisha Keisha Rosa Lucia""".split()

SURNAMES = """Smith Johnson Williams Brown Jones Garcia Miller Davis Rodriguez Martinez
Hernandez Lopez Gonzalez Wilson Anderson Thomas Taylor Moore Jackson Martin Lee Perez
Thompson White Harris Sanchez Clark Ramirez Lewis Robinson Walker Young Allen King Wright
Scott Torres Nguyen Hill Flores Green Adams Nelson Baker Hall Rivera Campbell Mitchell
Carter Roberts Gomez Phillips Evans Turner Diaz Parker Cruz Edwards Collins Reyes Stewart
Morris Morales Murphy Cook Rogers Gutierrez Ortiz Morgan Cooper Peterson Bailey Reed Kelly
Howard Ramos Kim Cox Ward Richardson Watson Brooks Chavez Wood James Bennett Gray Mendoza
Ruiz Hughes Price Alvarez Castillo Sanders Patel Myers Long Ross Foster Jimenez Powell
Jenkins Perry Russell Sullivan Bell Coleman Butler Henderson Barnes Gonzales Fisher
Vasquez Simmons Romero Jordan Patterson Alexander Hamilton Graham Reynolds Griffin Wallace
Moreno West Cole Hayes Bryant Herrera Gibson Ellis Tran Medina Aguilar Stevens Murray Ford
Castro Marshall Owens Harrison Fernandez McDonald Woods Washington Kennedy Wells Vargas
Henry Chen Freeman Webb Tucker Guzman Burns Crawford Olson Simpson Porter Hunter Gordon
Mendez Silva Shaw Snyder Mason Dixon Munoz Hunt Hicks Holmes Palmer Wagner Black Robertson
Boyd Rose Stone Salazar Fox Warren Mills Meyer Rice Schmidt Garza Daniels Ferguson Nichols
Stephens Soto Weaver Ryan Gardner Payne Grant Dunn Kelley Spencer Hawkins Arnold Pierce
Vazquez Hansen Peters Santos Hart Bradley Knight Elliott Cunningham Duncan Armstrong Hudson
Carroll Lane Riley Andrews Alvarado Ray Delgado Berry Perkins Hoffman Johnston Matthews
Pena Richards Contreras Willis Carpenter Lawrence Sandoval Guerrero George Chapman Rios
Estrada Ortega Watkins Greene Nunez Wheeler Valdez Harper Burke Larson Santiago Maldonado
Morrison Franklin Carlson Austin Dominguez Carr Lawson Jacobs OBrien Lynch Singh Vega
Bishop Montgomery Oliver Jensen Harvey Williamson Gilbert Dean Sims Espinoza Howell Li
Wong Reid Hanson Le McCoy Garrett Burton Fuller Wang Weber Welch Rojas Lucas Marquez
Fields Park Yang Little Banks Padilla Day Walsh Bowman Schultz Luna Fowler Mejia Davidson
Acosta Brewer May Holland Juarez Newman Pearson Curtis Cortez Douglas Schneider Joseph
Barrett Navarro Figueroa Keller Avila Wade Molina Stanley Hopkins Campos Barnett Bates
Chambers Caldwell Beck Lambert Miranda Byrd Craig Ayala Lowe Frazier Powers Neal Leonard
Gregory Carrillo Sutton Fleming Rhodes Shelton Schwartz Norris Jennings Watts Duran Walters
Cohen McDaniel Moran Parks Steele Vaughn Becker Holt DeLeon Barker Terry Hale Leon Hail
Benson Haynes Horton Miles Lyons Pham Graves Bush Thornton Wolfe Warner Cabrera McKinney
Mann Zimmerman Dawson Lara Fletcher Page McCarthy Love Robles Cervantes Solis Erickson
Reeves Chang Klein Salinas Fuentes Baldwin Daniel Simon Velasquez Hardy Higgins Aguirre
Lin Cummings Chandler Sharp Barber Bowen Ochoa Dennis Robbins Liu Ramsey Francis Griffith
Paul Blair OConnor Cardenas Pacheco Cross Calderon Quinn Moss Swanson Chan Rivas Khan
Rodgers Serrano Fitzgerald Rosales Stevenson Christensen Manning Gill Curry McLaughlin
Harmon McGee Gross Doyle Garner Newton Burgess Reese Walton Blake Trujillo Adkins Brady
Goodman Roman Webster Goodwin Fischer Huang Potter Delacruz Montoya Todd Wu Hines Mullins
Castaneda Malone Cannon Tate Mack Sherman Hubbard Hodges Zhang Guerra Wolf Valencia Saunders
Franco Rowe Gallagher Farmer Hammond Hampton Townsend Ingram Wise Gallegos Clarke Barton
Schroeder Maxwell Waters Logan Camacho Strickland Norman Person Colon Parsons Frank Harrington
Glover Osborne Buchanan Casey Floyd Patton Ibarra Ball Tyler Suarez Bowers Orozco Salas
Cobb Gibbs Andrade Bauer Conner Moody Escobar McGuire Lloyd Mueller Hartman French Kramer
McBride Pope Lindsey Velazquez Norton McCormick Sparks Flynn Yates Hogan Marsh Macias
Villanueva Zamora Pratt Stokes Owen Ballard Lang Brock Villarreal Charles Drake Barrera
Cain Patrick Pineda Burnett Mercado Santana Shepherd Bautista Ali Shaffer Lamb Trevino
McKenzie Hess Beil Olsen Cochran Morton Nash Wilkins Petersen Briggs Shah Roth Nicholson
Holloway Lozano Rangel Flowers Hoover Short Arias Mora Valenzuela Bryan Meyers Weiss
Underwood Bass Greer Summers Houston Carson Morrow Clayton Whitaker Decker Yoder Collier
Zuniga Carey Wilcox Melendez Poole Roberson Larsen Conley Davenport Copeland Massey Lam
Huff Rocha Cameron Jefferson Hood Monroe Anthony Pittman Huynh Randall Singleton Kirk
Combs Mathis Christian Skinner Bradford Richard Galvan Wall Boone Kirby Wilkinson Bridges
Bruce Atkinson Velez Meza Roy Vincent York Hodge Villa Abbott Allison Tapia Gates Chase
Sosa Sweeney Farrell Wyatt Dalton Horn Barron Phelps Yu Dickerson Heath Foley Atkins
Mathews Bonilla Acevedo Benitez Zavala Hensley Glenn Cisneros Harrell Shields Rubio Huffman
Choi Boyer Garrison Arroyo Bond Kane Hancock Callahan Dillon Cline Wiggins Grimes Arellano
Melton ONeill Savage Ho Beltran Pitts Parrish Ponce Rich Booth Koch Golden Ware Brennan
McDowell Marks Cantu Humphrey Baxter Sawyer Clay Tanner Hutchinson Kaur Berg Wiley
Gilmore Russo Villegas Hobbs Keith Wilkerson Ahmed Beard McClain Montes Mata Rosario
Vang Walter Henson ONeal Mosley McClure Beasley Stephenson Snow Huerta Preston Vance
Barry Johns Eaton Blackwell Dyer Prince Macdonald Solomon Guevara Stafford English
Hurst Woodard Cortes Shannon Kemp Nolan McCullough Merritt Murillo Moon Salgado Strong
Kline Cordova Barajas Roach Rosas Winters Jacobson Lester Knox Bullock Kerr Leach Meadows
Orr Davila Whitehead Pruitt Kent Conway McKee Barr David Dejesus Marin Berger McIntyre
Blankenship Gaines Palacios Cuevas Bartlett Durham Dorsey McCall ODonnell Stein Browning
Stout Lowery Sloan McLean Hendricks Calhoun Sexton Chung Gentry Hull Duarte Ellison
Nielsen Gillespie Buck Middleton Sellers Leblanc Esparza Hardin Bradshaw McIntosh Howe
Livingston Frost Glass Morse Knapp Herman Stark Bravo Noble Spears Weeks Corona Frederick
Buckley McFarland Hebert Enriquez Hickman Quintero Randolph Schaefer Walls Trejo House
Reilly Pennington Michael Conrad Giles Benjamin Crosby Fitzpatrick Donovan Mays Mahoney
Valentine Raymond Medrano Hahn McMillan Small Bentley Felix Peck Lucero Boyle Hanna Pace
Rush Hurley Harding McConnell Bernal Nava Ayers Everett Ventura Avery Pugh Mayer Bender
Shepard McMahon Landry Case Sampson Moses Magana Blackburn Dunlap Gould Duffy Vaughan
Herring McKay Espinosa Rivers Farley Bernard Ashley Friedman Potts Truong Costa Correa
Blevins Nixon Clements Fry Delarosa Best Benton Lugo Portillo Dougherty Crane Haley Phan
Villalobos Blanchard Horne Finley Quintana Lynn Esquivel Bean Dodson Mullen Xiong Hayden
Cano Levy Huber Richmond Moyer Lim Frye Sheppard McCarty Avalos Booker Waller Parra
Woodward Jaramillo Krueger Rasmussen Brandt Peralta Donaldson Stuart Faulkner Maynard
Galindo Coffey Estes Sanford Burch Maddox Vo OConnell Vu Andersen Spence McPherson Church
Schmitt Stanton Leal Cherry Compton Dudley Sierra Pollard Alfaro Hester Proctor Lu Hinton
Novak Good Madden McCann Terrell Jarvis Dickson Reyna Cantrell Mayo Branch Hendrix Rollins
Rowland Whitney Duke Odom Daugherty Travis Tang Archer""".split()

# given name -> common nicknames (used for tier-B duplicate variation)
NICKNAMES = {
    "William": ["Bill", "Will", "Billy"], "Robert": ["Bob", "Rob", "Bobby"],
    "Richard": ["Rick", "Dick", "Rich"], "James": ["Jim", "Jimmy"], "John": ["Jack", "Johnny"],
    "Michael": ["Mike", "Mikey"], "Joseph": ["Joe", "Joey"], "Thomas": ["Tom", "Tommy"],
    "Charles": ["Charlie", "Chuck"], "Christopher": ["Chris"], "Daniel": ["Dan", "Danny"],
    "Matthew": ["Matt"], "Anthony": ["Tony"], "Donald": ["Don"], "Steven": ["Steve"],
    "Andrew": ["Andy", "Drew"], "Joshua": ["Josh"], "Kenneth": ["Ken", "Kenny"],
    "Timothy": ["Tim"], "Ronald": ["Ron"], "Edward": ["Ed", "Eddie"], "Jeffrey": ["Jeff"],
    "Nicholas": ["Nick"], "Jonathan": ["Jon"], "Stephen": ["Steve"], "Lawrence": ["Larry"],
    "Benjamin": ["Ben"], "Samuel": ["Sam"], "Gregory": ["Greg"], "Alexander": ["Alex"],
    "Patrick": ["Pat"], "Raymond": ["Ray"], "Gerald": ["Jerry"], "Zachary": ["Zach"],
    "Douglas": ["Doug"], "Walter": ["Walt"], "Philip": ["Phil"], "Eugene": ["Gene"],
    "Elizabeth": ["Liz", "Beth", "Betsy"], "Patricia": ["Pat", "Patty", "Trish"],
    "Jennifer": ["Jen", "Jenny"], "Margaret": ["Maggie", "Peggy", "Meg"],
    "Susan": ["Sue", "Susie"], "Jessica": ["Jess"], "Kimberly": ["Kim"],
    "Deborah": ["Deb", "Debbie"], "Rebecca": ["Becky", "Becca"], "Katherine": ["Kate", "Kathy", "Katie"],
    "Kathleen": ["Kathy", "Kate"], "Christine": ["Chris", "Christy"], "Pamela": ["Pam"],
    "Samantha": ["Sam"], "Stephanie": ["Steph"], "Cynthia": ["Cindy"], "Victoria": ["Vicky", "Tori"],
    "Jacqueline": ["Jackie"], "Theresa": ["Terry", "Tess"], "Teresa": ["Terry"],
    "Abigail": ["Abby"], "Judith": ["Judy"], "Dorothy": ["Dot", "Dottie"], "Barbara": ["Barb"],
    "Sandra": ["Sandy"], "Melissa": ["Missy", "Mel"], "Amanda": ["Mandy"], "Carolyn": ["Carol"],
    "Virginia": ["Ginny"], "Frances": ["Fran"], "Beverly": ["Bev"], "Isabella": ["Bella"],
    "Danielle": ["Dani"], "Alexis": ["Lexi"], "Madison": ["Maddie"], "Natalie": ["Nat"],
}

STREET_WORDS = """Oak Maple Cedar Pine Elm Willow Birch Walnut Chestnut Hickory Aspen
Spruce Laurel Magnolia Sycamore Juniper Hawthorn Linden Poplar Alder Mill River Lake Hill
Ridge Valley Meadow Brook Spring Park Church School Market Union Harbor Bridge Station
Forest Orchard Prairie Summit Highland Sunset Liberty Franklin Jefferson Madison Lincoln
Washington Adams Monroe Jackson Grant Kestrel Heron Falcon Osprey Wren Sparrow Finch
Canal Quarry Foundry Tannery Granary Pellbrook Marrow Ashford Bramble Copper Iron""".split()

STREET_SUFFIX = ["St", "Ave", "Rd", "Dr", "Ln", "Ct", "Blvd", "Way", "Pl", "Ter"]
STREET_SUFFIX_LONG = {"St": "Street", "Ave": "Avenue", "Rd": "Road", "Dr": "Drive",
                      "Ln": "Lane", "Ct": "Court", "Blvd": "Boulevard", "Way": "Way",
                      "Pl": "Place", "Ter": "Terrace"}

# Invented towns. (town, state, zip3 prefix)
TOWNS = [
    ("Kestrel Falls", "OH", "440"), ("Pellbrook", "PA", "150"), ("Ashford Mills", "OH", "441"),
    ("Marrow Point", "PA", "151"), ("Bramblewood", "OH", "442"), ("Copper Ridge", "WV", "260"),
    ("Heron Bay", "OH", "443"), ("Stillwater Junction", "PA", "152"), ("Osprey Hollow", "WV", "261"),
    ("Granary Hill", "OH", "444"), ("Wrenfield", "PA", "153"), ("Tannery Row", "OH", "445"),
    ("Linden Crossing", "PA", "154"), ("Foundry Glen", "WV", "262"), ("Quarry Bend", "OH", "446"),
    ("Finch Harbor", "PA", "155"), ("Sycamore Flats", "OH", "447"), ("Alder Creek", "WV", "263"),
]

OCCUPATIONS = [
    ("Registered nurse", 800), ("Retail associate", 600), ("Teacher", 400), ("Software developer", 200),
    ("Truck driver", 900), ("Electrician", 1200), ("Accountant", 300), ("Warehouse supervisor", 700),
    ("Retired", 500), ("Office manager", 400), ("Pharmacist", 300), ("Mechanic", 1500),
    ("Construction laborer", 1800), ("Sales representative", 600), ("Student", 300),
    ("Home health aide", 900), ("Police officer", 300), ("Chef", 1200), ("Hair stylist", 2000),
    ("Real estate agent", 800), ("Physician", 300), ("Plumber", 1500), ("Barista", 700),
    ("Insurance adjuster", 300), ("Dental hygienist", 400),
]

BUSINESS_TYPES = [
    ("Landscaping", "LLC", 4000, False), ("Plumbing", "Inc", 3000, False),
    ("Dental Group", "PC", 500, False), ("Logistics", "LLC", 1000, False),
    ("Accounting", "LLP", 300, False), ("Properties", "LLC", 500, False),
    ("Holdings", "LLC", 200, False), ("Auto Repair", "Inc", 6000, False),
    ("Consulting", "LLC", 200, False), ("Construction", "Inc", 5000, False),
    ("Family Restaurant", "LLC", 45000, True), ("Laundromat", "LLC", 30000, True),
    ("Convenience Store", "Inc", 55000, True), ("Car Wash", "LLC", 35000, True),
    ("Liquor Store", "Inc", 60000, True), ("Diner", "LLC", 40000, True),
]

EMAIL_DOMAINS = ["example.com", "example.net", "example.org", "mail.example", "inbox.example"]

EXTERNAL_BANKS = ["First Meridian Bank", "Union Crest Bank", "Harborline Federal", "Summit Trust Co",
                  "Great Plains Savings", "Coastal Ridge Bank", "Northgate Credit Union",
                  "Bluewater National"]

COUNTERPARTIES = ["Tri-State Electric", "Heron Bay Water Authority", "Summit Mortgage Servicing",
                  "Quickstop Fuel", "Grocery Mart", "Northgate Wireless", "Metro Insurance Co",
                  "Kestrel Falls Payroll Svcs", "State Revenue Dept", "Riverside Pharmacy",
                  "Home Supply Depot", "City Utilities", "Brightline Streaming", "Auto Finance Co",
                  "Medical Associates", "Payroll Direct Inc", "Online Marketplace",
                  "Pellbrook Energy Co-op"]

SHELL_COUNTERPARTIES = ["Global Tradeways Ltd", "Pinnacle Import Export", "Atlas Venture Partners LLC",
                        "Silverline Holdings", "Crescent Commodities", "Orion Freight Brokers",
                        "Meridian Asset Group", "Keystone Merchandising"]
