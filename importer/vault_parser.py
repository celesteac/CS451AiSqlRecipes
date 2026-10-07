"""Parse Obsidian recipe notes (YAML frontmatter + markdown body) into plain dicts."""
import re
from fractions import Fraction
from pathlib import Path

import yaml

UNICODE_FRACTIONS = {"½": "1/2", "⅓": "1/3", "⅔": "2/3", "¼": "1/4", "¾": "3/4",
                     "⅛": "1/8", "⅜": "3/8", "⅝": "5/8", "⅞": "7/8"}

UNITS = {
    "cup": "cup", "cups": "cup",
    "tablespoon": "tbsp", "tablespoons": "tbsp", "tbsp": "tbsp", "tbs": "tbsp",
    "teaspoon": "tsp", "teaspoons": "tsp", "tsp": "tsp",
    "ounce": "oz", "ounces": "oz", "oz": "oz",
    "pound": "lb", "pounds": "lb", "lb": "lb", "lbs": "lb",
    "g": "g", "gram": "g", "grams": "g", "kg": "kg", "ml": "ml",
    "pint": "pint", "pints": "pint", "stick": "stick", "sticks": "stick",
    "packet": "packet", "packets": "packet", "pack": "packet", "packs": "packet",
    "clove": "clove", "cloves": "clove", "can": "can", "cans": "can",
    "dash": "dash", "pinch": "pinch", "bag": "bag", "bunch": "bunch",
}

# Canonical ingredient names, checked in order (longest / most specific first).
# Each entry: (canonical name, regex matched against the lowercased line).
CANONICAL = [
    ("chocolate kiss", r"chocolate kiss"),
    ("peanut butter cup", r"peanut butter cups?|reese"),
    ("peanut butter", r"peanut butter"),
    ("unsalted butter", r"unsalted butter"),
    ("butter", r"\bbutter\b"),
    ("brown sugar", r"brown sugar"),
    ("powdered sugar", r"powdered sugar|confectioners.? sugar"),
    ("granulated sugar", r"granulated sugar|\bsugar\b"),
    ("all-purpose flour", r"all-purpose flour|\bflour\b"),
    ("rice flour", r"rice flour"),
    ("cornstarch", r"cornstarch|corn starch"),
    ("baking soda", r"baking soda"),
    ("baking powder", r"baking powder"),
    ("egg yolk", r"egg yolk"),
    ("egg", r"\beggs?\b"),
    ("vanilla extract", r"vanilla"),
    ("almond extract", r"almond extract"),
    ("sliced almonds", r"sliced almonds"),
    ("cinnamon", r"cinnamon"),
    ("cardamom", r"cardamom"),
    ("cream of tartar", r"cream of tartar"),
    ("garlic salt", r"garlic salt"),
    ("garlic", r"\bgarlic\b"),
    ("kosher salt", r"kosher salt"),
    ("flaky sea salt", r"flaky sea salt"),
    ("sea salt", r"sea salt|popcorn salt"),
    ("salt", r"\bsalt\b"),
    ("bell pepper", r"bell pepper"),
    ("black pepper", r"\bpepper\b(?! jack)(?!s)"),
    ("heavy cream", r"heavy cream"),
    ("milk", r"\bmilk\b|half and half"),
    ("parmesan cheese", r"parmesan"),
    ("romano cheese", r"romano"),
    ("cheddar cheese", r"cheddar|\bcheese\b"),
    ("chicken breast", r"chicken breasts?|chicken thighs?|\bchicken\b"),
    ("ground turkey", r"ground turkey"),
    ("panko", r"panko"),
    ("frying oil", r"frying oil|high-smoke point oil|vegetable oil|canola oil"),
    ("olive oil", r"olive oil"),
    ("fettuccine", r"fettuccine"),
    ("rice noodles", r"rice noodles"),
    ("pasta", r"\bpasta\b"),
    ("rice", r"\brice\b"),
    ("oats", r"\boats\b"),
    ("active dry yeast", r"yeast"),
    ("orange", r"\boranges?\b|orange juice|orange zest"),
    ("lemon", r"\blemons?\b|lemon juice"),
    ("lime", r"\blimes?\b|lime juice"),
    ("banana", r"banana"),
    ("avocado", r"avocado"),
    ("mango", r"mango"),
    ("yogurt", r"yogurt"),
    ("chickpeas", r"chickpea|garbanzo"),
    ("onion", r"\bonions?\b"),
    ("jalapeno", r"jalape"),
    ("tomato", r"tomato"),
    ("cilantro", r"cilantro"),
    ("spinach", r"spinach"),
    ("potato", r"potato"),
    ("frozen mixed vegetables", r"frozen vegetables"),
    ("kidney beans", r"kidney beans|\bbeans\b"),
    ("chili powder", r"chili powder"),
    ("cumin", r"cumin"),
    ("garam masala", r"garam masala"),
    ("parsley", r"parsley"),
    ("chocolate", r"chocolate"),
    ("cocoa powder", r"cocoa"),
    ("popcorn kernels", r"kernels|popping corn"),
    ("nutritional yeast", r"nutritional yeast"),
    ("fish sauce", r"fish sauce"),
    ("peanuts", r"\bpeanuts\b"),
    ("bean sprouts", r"bean sprouts"),
    ("tamarind", r"tamarind"),
    ("ginger", r"ginger"),
    ("curry roux", r"curry"),
    ("carrot", r"carrot"),
]
# nutritional yeast must win over plain yeast
CANONICAL.sort(key=lambda c: 0 if c[0] == "nutritional yeast" else 1)

NUM = r"(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?)"
QTY_RE = re.compile(rf"^\s*({NUM})(?:\s*(?:-|–|to)\s*({NUM}))?\s*")


def strip_md(text):
    """Remove markdown emphasis and wiki-link brackets."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"(?<![\w*])[*_](.+?)[*_](?![\w*])", r"\1", text)
    text = re.sub(r"\[\[(.+?)\]\]", r"\1", text)
    return text.strip()


def parse_quantity(line):
    """Return (quantity, unit, rest) from an ingredient line like '1 ½ cups flour'."""
    text = line
    for k, v in UNICODE_FRACTIONS.items():
        text = re.sub(rf"(\d){k}", rf"\1 {v}", text)  # '1½' -> '1 1/2'
        text = text.replace(k, v)
    m = QTY_RE.match(text)
    if not m:
        return None, None, line.strip()
    qty = float(sum(Fraction(p) for p in m.group(1).split()))
    rest = text[m.end():]
    unit = None
    um = re.match(r"([A-Za-z]+)\.?\b\s*", rest)
    if um and um.group(1).lower() in UNITS:
        unit = UNITS[um.group(1).lower()]
        rest = rest[um.end():]
    return round(qty, 3), unit, rest.strip()


def canonical_ingredient(line):
    low = line.lower()
    for name, pattern in CANONICAL:
        if re.search(pattern, low):
            return name
    return None


def parse_minutes(value):
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    if re.fullmatch(r"\d+", text):
        return int(text)
    total, found = 0.0, False
    for num, unit in re.findall(r"(\d+(?:\.\d+)?)\s*(hrs?|hours?|mins?|minutes?)", text):
        found = True
        total += float(num) * (60 if unit.startswith("h") else 1)
    return int(round(total)) if found else None


def as_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    return [str(v).strip() for v in value if v is not None and str(v).strip()]


BULLET_RE = re.compile(r"^[-*](?:\s+(.*))?$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def section_kind(heading):
    h = heading.lower()
    if "ingredient" in h:
        return "ingredients"
    if "direction" in h or "instruction" in h:
        return "directions"
    if "equipment" in h:
        return "equipment"
    if "nutrition" in h:
        return "nutrition"
    if "picture" in h:
        return "pictures"
    if h.startswith("notes") or "notes & tips" in h or h.endswith("notes & tips") or "notes" in h.split():
        return "notes"
    return None


def clean_section_title(text):
    return re.sub(r"^\d+\.\s*", "", strip_md(text)).strip() or None


def parse_body(body):
    out = {"description": None, "ingredients": [], "steps": [], "equipment": [],
           "notes": [], "nutrition": None, "images": []}
    mode, mode_level, sub = None, 0, None
    desc_lines, nutrition, extra = [], [], None  # extra = (title, lines) for other sections
    current_step = None

    def flush_extra():
        nonlocal extra
        if extra and any(l.strip() for l in extra[1]):
            body_text = "\n".join(l.rstrip() for l in extra[1]).strip()
            out["notes"].append({"title": extra[0], "body": strip_md(body_text)})
        extra = None

    for raw in body.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if stripped == "---":
            continue
        hm = HEADING_RE.match(stripped)
        if hm:
            level, text = len(hm.group(1)), hm.group(2).strip()
            kind = section_kind(text)
            if level == 1:
                flush_extra()
                mode, sub = "description", None
                continue
            if kind:
                flush_extra()
                mode, mode_level, sub, current_step = kind, level, None, None
                continue
            if mode in ("ingredients", "directions") and level > mode_level:
                sub = clean_section_title(text)
                current_step = None
                continue
            if mode == "pictures":
                continue
            flush_extra()
            mode, mode_level, sub = "extra", level, None
            extra = (strip_md(text), [])
            continue

        if mode == "description":
            if stripped:
                desc_lines.append(stripped)
        elif mode == "extra":
            extra[1].append(line)
        elif mode == "pictures":
            for img in re.findall(r"!\[\[(.+?)\]\]", line):
                out["images"].append(img)
        elif mode == "nutrition":
            t = re.sub(r"^[-*]\s*", "", stripped)
            if t and t.lower() != "j":
                nutrition.append(t)
        elif mode == "equipment":
            t = re.sub(r"^[-*]\s*", "", stripped)
            if t:
                out["equipment"].append(strip_md(t))
        elif mode == "notes":
            t = re.sub(r"^[-*]\s*", "", stripped)
            if t:
                out["notes"].append({"title": None, "body": strip_md(t)})
        elif mode == "ingredients":
            if not stripped:
                continue
            bullet = BULLET_RE.match(stripped)
            if bullet:
                t = strip_md(bullet.group(1) or "")
                if not t:
                    continue
                if sub and sub.lower() in ("materials", "equipment"):
                    out["equipment"].append(t)
                else:
                    out["ingredients"].append({"section": sub, "text": t})
            else:
                sub = strip_md(stripped).rstrip(":")
        elif mode == "directions":
            if not stripped:
                continue
            num = re.match(r"^\d+\.\s*(.*)$", stripped)
            bullet = BULLET_RE.match(stripped)
            indented = line.startswith((" ", "\t"))
            if num or (bullet and not indented):
                t = strip_md((num or bullet).group(1) or "")
                if t:
                    current_step = {"section": sub, "text": t}
                    out["steps"].append(current_step)
                else:
                    current_step = None
            elif current_step is not None:
                t = strip_md((bullet.group(1) or "") if bullet else stripped)
                current_step["text"] += " " + t
            else:
                current_step = {"section": sub, "text": strip_md(stripped)}
                out["steps"].append(current_step)
    flush_extra()
    if desc_lines:
        out["description"] = " ".join(strip_md(l) for l in desc_lines)
    if nutrition:
        out["nutrition"] = " ".join(nutrition)
    return out


def split_frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not m:
        return {}, text
    return yaml.safe_load(m.group(1)) or {}, m.group(2)


def parse_recipe_file(path: Path):
    text = path.read_text(encoding="utf-8")
    meta, body = split_frontmatter(text)
    title, _, attribution = path.stem.partition(" - ")
    parsed = parse_body(body)

    tags = [t.lower() for t in as_list(meta.get("tags")) if t.lower() != "recipe"]
    categories = [c.lower() for c in as_list(meta.get("category"))]
    if not categories and "snack" in tags:
        categories = ["snack or side"]
    cuisines = [c.title() for c in as_list(meta.get("cuisine"))]

    makes = meta.get("makes")
    servings = meta.get("servings")
    if servings is None and makes and re.match(r"^\s*(\d+)\s+servings?", str(makes)):
        servings = int(re.match(r"^\s*(\d+)", str(makes)).group(1))

    source = meta.get("source")
    source = str(source).strip() if source else None
    source_url = source if source and source.startswith("http") else None
    source_name = None
    if source_url:
        source_name = re.sub(r"^www\.", "", re.match(r"https?://([^/]+)", source_url).group(1))
    elif source and source.lower() != "lost":
        source_name = source
    if attribution and not source_name:
        source_name = attribution

    cover = meta.get("cover")
    cover = re.sub(r"^\[\[|\]\]$", "", str(cover).strip()) if cover else None

    kcal = meta.get("kcal/serving")
    made_it = meta.get("I made it")

    ingredients = []
    for i, ing in enumerate(parsed["ingredients"], start=1):
        qty, unit, _rest = parse_quantity(ing["text"])
        ingredients.append({"position": i, "section": ing["section"], "raw_text": ing["text"],
                            "quantity": qty, "unit": unit,
                            "ingredient": canonical_ingredient(ing["text"])})

    return {
        "file": path.name,
        "title": title.strip(),
        "description": parsed["description"],
        "prep_minutes": parse_minutes(meta.get("prep time", meta.get("prep_time"))),
        "cook_minutes": parse_minutes(meta.get("cook time", meta.get("cook_time"))),
        "total_minutes": parse_minutes(meta.get("total time", meta.get("total_time"))),
        "yield_text": str(makes).strip() if makes else (f"{servings} servings" if servings else None),
        "servings": int(servings) if servings else None,
        "kcal_per_serving": int(kcal) if kcal else None,
        "nutrition_text": parsed["nutrition"],
        "source_name": source_name,
        "source_url": source_url,
        "cover_image": cover,
        "made_it": made_it is True,
        "categories": categories,
        "cuisines": cuisines,
        "tags": tags,
        "ingredients": ingredients,
        "steps": [{"position": i, "section": s["section"], "body": s["text"]}
                  for i, s in enumerate(parsed["steps"], start=1)],
        "equipment": parsed["equipment"],
        "notes": parsed["notes"],
        "images": [img for img in parsed["images"] if img != cover],
    }
