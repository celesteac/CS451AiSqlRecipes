"""Hand-written demo data layered on top of the vault import.

The vault recipes all belong to celeste. The other users and their recipes are
made up so the sharing, visibility, and rating features have something to show.
Recipes are referenced by (owner username, title).
"""

USERS = [
    # username, display name, bio
    ("celeste", "Celeste", "Recipes from my Obsidian vault."),
    ("maya_bakes", "Maya R.", "Weekend baker. Cookies are a food group."),
    ("jordan_cooks", "Jordan T.", "Weeknight dinners and meal prep."),
    ("sam_eats", "Sam K.", "Snacks, dips, and noodles."),
    ("priya_p", "Priya P.", "Vegetarian cooking."),
]

# Visibility for celeste's vault recipes (anything not listed is public).
VAULT_VISIBILITY = {
    "Garlic Pasta": "private",            # family recipe from friends
    "Snickerdoodle Blondies": "private",  # empty draft
    "Kolaches": "unlisted",               # no ingredients written down yet
    "Seco de pollo": "unlisted",
}

# Visibility for the demo users' recipes (anything not listed is public).
DEMO_VISIBILITY = {
    ("maya_bakes", "Brown Butter Snickerdoodle Dough"): "private",
    ("jordan_cooks", "Lighter Fettuccine Alfredo"): "private",
    ("sam_eats", "Pad Thai"): "unlisted",
}

# (forked recipe) -> (original recipe)
FORKS = {
    ("jordan_cooks", "Chicken Katsu Curry"): ("celeste", "Chicken Katsu"),
    ("jordan_cooks", "Lighter Fettuccine Alfredo"): ("celeste", "Fettuccine Alfredo"),
}

# (recipe, shared with, permission, shared_at)
SHARES = [
    (("celeste", "Garlic Pasta"), "maya_bakes", "view", "2026-08-02"),
    (("celeste", "Garlic Pasta"), "jordan_cooks", "view", "2026-08-02"),
    (("celeste", "Snickerdoodle Blondies"), "maya_bakes", "edit", "2026-09-10"),
    (("celeste", "Seco de pollo"), "priya_p", "view", "2026-08-20"),
    (("maya_bakes", "Brown Butter Snickerdoodle Dough"), "celeste", "edit", "2026-09-09"),
    (("jordan_cooks", "Lighter Fettuccine Alfredo"), "celeste", "view", "2026-09-01"),
    (("sam_eats", "Pad Thai"), "priya_p", "view", "2026-09-15"),
]

# (user, recipe, saved_at)
SAVES = [
    ("maya_bakes", ("celeste", "Almond Sugar Cookies"), "2026-07-03"),
    ("maya_bakes", ("celeste", "Crumb Cake Cookies"), "2026-07-03"),
    ("maya_bakes", ("celeste", "Salted Caramel Brownies"), "2026-08-11"),
    ("jordan_cooks", ("celeste", "Orange Chicken"), "2026-07-20"),
    ("jordan_cooks", ("celeste", "Chicken Katsu"), "2026-07-20"),
    ("jordan_cooks", ("priya_p", "Chana Masala"), "2026-08-30"),
    ("sam_eats", ("celeste", "Stovetop Popcorn"), "2026-08-05"),
    ("sam_eats", ("celeste", "Peanut Butter Blossoms"), "2026-09-28"),
    ("priya_p", ("celeste", "Fettuccine Alfredo"), "2026-07-14"),
    ("priya_p", ("maya_bakes", "Banana Bread"), "2026-08-01"),
    ("priya_p", ("sam_eats", "Guacamole"), "2026-08-01"),
    ("celeste", ("priya_p", "Chana Masala"), "2026-09-02"),
    ("celeste", ("maya_bakes", "Lemon Bars"), "2026-09-05"),
]

# (user, recipe, cooked_on, rating, comment). celeste's vault "I made it: true"
# recipes also get an undated log entry, added by build_seed.py.
COOK_LOGS = [
    ("celeste", ("celeste", "Fettuccine Alfredo"), "2026-09-14", 5, "Doubled the cheese again."),
    ("celeste", ("celeste", "Chicken Katsu"), "2026-09-21", 4, "Fried from frozen, worked well."),
    ("celeste", ("celeste", "Peanut Butter Blossoms"), "2026-10-03", 5, "Made spiders for a Halloween party."),
    ("celeste", ("priya_p", "Chana Masala"), "2026-09-08", 4, None),
    ("maya_bakes", ("celeste", "Almond Sugar Cookies"), "2026-07-10", 5, "Tried a lemon icing, also great."),
    ("maya_bakes", ("celeste", "Crumb Cake Cookies"), "2026-07-24", 4, "Long chill but worth it."),
    ("maya_bakes", ("celeste", "Salted Caramel Brownies"), "2026-08-15", 5, None),
    ("maya_bakes", ("maya_bakes", "Banana Bread"), "2026-06-30", 4, None),
    ("maya_bakes", ("maya_bakes", "Lemon Bars"), "2026-08-22", 5, None),
    ("jordan_cooks", ("celeste", "Orange Chicken"), "2026-07-26", 5, "Double fry is the trick."),
    ("jordan_cooks", ("celeste", "Chicken Katsu"), "2026-07-27", 4, None),
    ("jordan_cooks", ("jordan_cooks", "Weeknight Turkey Chili"), "2026-09-03", 4, None),
    ("jordan_cooks", ("jordan_cooks", "Chicken Katsu Curry"), "2026-09-12", 5, None),
    ("jordan_cooks", ("celeste", "Garlic Pasta"), "2026-08-09", 3, "A bit plain, added chili flakes."),
    ("sam_eats", ("celeste", "Stovetop Popcorn"), "2026-08-06", 5, None),
    ("sam_eats", ("celeste", "Stovetop Popcorn"), "2026-09-19", 4, "Burned the second batch a little."),
    ("sam_eats", ("sam_eats", "Guacamole"), "2026-07-04", 5, None),
    ("sam_eats", ("celeste", "Fettuccine Alfredo"), "2026-08-18", 3, "Too rich for me."),
    ("priya_p", ("priya_p", "Chana Masala"), "2026-08-12", 5, None),
    ("priya_p", ("priya_p", "Mango Lassi"), "2026-08-12", 4, None),
    ("priya_p", ("maya_bakes", "Banana Bread"), "2026-08-04", 4, None),
    ("priya_p", ("celeste", "Seco de pollo"), "2026-08-24", 5, "Loved the cilantro sauce."),
]

# (author, recipe, body, created_at) comments left on someone else's recipe
COMMENTS = [
    ("maya_bakes", ("celeste", "Almond Sugar Cookies"), "Lemon icing instead of almond is great too.", "2026-07-10"),
    ("jordan_cooks", ("celeste", "Orange Chicken"), "Air fryer reheat at 400°F kept them crunchy.", "2026-07-28"),
    ("sam_eats", ("celeste", "Stovetop Popcorn"), "Coconut oil really does taste like the movies.", "2026-08-06"),
]

# (owner, name, description, visibility, [recipes in order])
COLLECTIONS = [
    ("celeste", "Meal Prep", "Freezer-friendly dinners", "private",
     [("celeste", "Chicken Katsu"), ("celeste", "Orange Chicken"), ("celeste", "Seco de pollo")]),
    ("celeste", "Halloween Party", "Spooky treats", "public",
     [("celeste", "Peanut Butter Blossoms"), ("celeste", "Salted Caramel Brownies"),
      ("celeste", "Stovetop Popcorn")]),
    ("maya_bakes", "Cookie Swap", "Cookies for the December swap", "public",
     [("celeste", "Almond Sugar Cookies"), ("celeste", "Crumb Cake Cookies"),
      ("maya_bakes", "Lemon Bars")]),
    ("jordan_cooks", "Weeknight Rotation", None, "public",
     [("jordan_cooks", "Weeknight Turkey Chili"), ("jordan_cooks", "Chicken Katsu Curry"),
      ("priya_p", "Chana Masala")]),
]
