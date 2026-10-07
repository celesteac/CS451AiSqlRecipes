"""Ask the recipe database questions in plain English.

Flow: question + schema -> OpenAI -> SQL -> run read-only on Postgres -> rows
      -> OpenAI -> friendly answer.

Usage:
    python bot/db_bot.py                         # run every question with every strategy
    python bot/db_bot.py --strategy zero_shot    # one strategy, all questions
    python bot/db_bot.py --ask "Which desserts take under 45 minutes?"
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import psycopg
from openai import OpenAI

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCHEMA_SQL = (ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
# The model only needs the CREATE TABLE statements and their comments.
SCHEMA_FOR_PROMPT = re.sub(r"(?s)DROP TABLE.*?;\n|CREATE INDEX[^\n]*\n|-- Run order[^\n]*\n", "",
                           SCHEMA_SQL).strip()


def load_config():
    cfg = {}
    path = HERE / "config.json"
    if path.exists():
        cfg = json.loads(path.read_text())
    return {
        "openaiKey": os.environ.get("OPENAI_API_KEY", cfg.get("openaiKey")),
        "model": os.environ.get("OPENAI_MODEL", cfg.get("model", "gpt-4o-mini")),
        "databaseUrl": os.environ.get("DATABASE_URL", cfg.get("databaseUrl")),
    }


# ---------------------------------------------------------------------------
# Database (always read-only)
# ---------------------------------------------------------------------------
class Database:
    def __init__(self, url):
        self.conn = psycopg.connect(url, autocommit=True)

    def run(self, query, limit=50):
        with self.conn.transaction():
            with self.conn.cursor() as cur:
                cur.execute("SET TRANSACTION READ ONLY")
                cur.execute("SET LOCAL statement_timeout = '5s'")
                cur.execute(query)
                columns = [d.name for d in cur.description] if cur.description else []
                rows = cur.fetchmany(limit) if cur.description else []
        return columns, [[to_json(v) for v in row] for row in rows]

    def sample_rows(self, per_table=3):
        """A few rows from each table, as the paper's 'table content' prompt section."""
        out = []
        tables = re.findall(r"CREATE TABLE (\w+)", SCHEMA_SQL)
        for t in tables:
            cols, rows = self.run(f"SELECT * FROM {t} LIMIT {per_table}")
            out.append(f"/*\n{per_table} example rows from {t}:\n" + "\t".join(cols) + "\n" +
                       "\n".join("\t".join(str(v) for v in r) for r in rows) + "\n*/")
        return "\n".join(out)


def to_json(value):
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


# ---------------------------------------------------------------------------
# Prompting strategies (Chang & Fosler-Lussier 2023, arXiv:2305.11853)
# ---------------------------------------------------------------------------
SQL_ONLY = ("Write one PostgreSQL SELECT statement that answers the question. "
            "Respond with only the SQL in a ```sql code block, no explanation. "
            "When the question says 'I' or 'me', it means the user with username 'celeste'.")

# Single-domain: worked examples written against THIS database.
SINGLE_DOMAIN_EXAMPLES = [
    ("Which public recipes use chicken?",
     """SELECT DISTINCT r.title
FROM recipe r
JOIN recipe_ingredient ri ON ri.recipe_id = r.recipe_id
JOIN ingredient i ON i.ingredient_id = ri.ingredient_id
WHERE r.visibility = 'public' AND i.name ILIKE '%chicken%';"""),
    ("Who has Maya shared recipes with?",
     """SELECT r.title, u2.display_name AS shared_with, s.permission
FROM recipe_share s
JOIN recipe r ON r.recipe_id = s.recipe_id
JOIN app_user owner ON owner.user_id = r.owner_id
JOIN app_user u2 ON u2.user_id = s.shared_with_user_id
WHERE owner.username = 'maya_bakes';"""),
]

# Cross-domain: worked examples from a DIFFERENT database (the class dog-show example).
CROSS_DOMAIN_SCHEMA = """CREATE TABLE person (person_id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL);
CREATE TABLE dog (dog_id INTEGER PRIMARY KEY, name VARCHAR(100), breed VARCHAR(100));
CREATE TABLE person_dog (person_id INTEGER REFERENCES person, dog_id INTEGER REFERENCES dog);
CREATE TABLE award (award_id INTEGER PRIMARY KEY, dog_id INTEGER REFERENCES dog, title VARCHAR(100), year INTEGER);"""
CROSS_DOMAIN_EXAMPLES = [
    ("Which people own more than one dog?",
     """SELECT p.name, COUNT(*) AS dogs
FROM person p JOIN person_dog pd ON pd.person_id = p.person_id
GROUP BY p.name HAVING COUNT(*) > 1;"""),
    ("Which dogs have never won an award?",
     """SELECT d.name FROM dog d
LEFT JOIN award a ON a.dog_id = d.dog_id
WHERE a.award_id IS NULL;"""),
]


def format_examples(examples):
    return "\n\n".join(f"Question: {q}\n```sql\n{s}\n```" for q, s in examples)


def build_strategies(db):
    return {
        "zero_shot": f"{SCHEMA_FOR_PROMPT}\n\n{SQL_ONLY}",
        "zero_shot_with_rows": f"{SCHEMA_FOR_PROMPT}\n\n{db.sample_rows()}\n\n{SQL_ONLY}",
        "single_domain_few_shot": (f"{SCHEMA_FOR_PROMPT}\n\nExamples for this database:\n\n"
                                   f"{format_examples(SINGLE_DOMAIN_EXAMPLES)}\n\n{SQL_ONLY}"),
        "cross_domain_few_shot": (f"Here are examples from a different database:\n{CROSS_DOMAIN_SCHEMA}\n\n"
                                  f"{format_examples(CROSS_DOMAIN_EXAMPLES)}\n\n"
                                  f"Now use this database instead:\n{SCHEMA_FOR_PROMPT}\n\n{SQL_ONLY}"),
    }


QUESTIONS = [
    "Which recipes use butter?",
    "What are the three highest rated recipes, and who owns them?",
    "Which of my private recipes have I shared, and with whom?",
    "Which desserts can be made in under 45 minutes total?",
    "Which recipes were forked from someone else's recipe, and what was the original?",
    "Which ingredients appear in the most recipes?",
    "What is in the Halloween Party collection?",
    "Who has cooked other people's recipes the most?",
    "Which recipes have I made that nobody has rated?",
    "Which Italian dishes have more than 900 calories per serving?",
]


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------
class Chat:
    def __init__(self, key, model):
        self.client = OpenAI(api_key=key)
        self.model = model

    def ask(self, content):
        resp = self.client.chat.completions.create(
            model=self.model, messages=[{"role": "user", "content": content}])
        return resp.choices[0].message.content or ""


def extract_sql(text):
    m = re.search(r"```(?:sql|postgresql|postgres)?\s*\n(.*?)```", text, re.S | re.I)
    return (m.group(1) if m else text).strip()


def friendly_prompt(question, sql, columns, rows):
    return (
        "You are answering a question about a recipe-sharing database.\n"
        f"Question: {question}\n"
        f"SQL that was run:\n{sql}\n"
        f"Columns: {columns}\n"
        f"Rows ({len(rows)}): {json.dumps(rows, ensure_ascii=False)}\n"
        "Answer the question in one or two friendly sentences using only these rows. "
        "Use names, not ids. If there are no rows, say nothing matched. "
        "The user 'celeste' is the person asking, so refer to her as 'you'."
    )


def answer(question, strategy_name, prefix, db, chat):
    result = {"question": question, "strategy": strategy_name, "sql": None,
              "columns": None, "rows": None, "friendlyResponse": None, "error": None}
    try:
        result["sql"] = extract_sql(chat.ask(f"{prefix}\n\nQuestion: {question}"))
        result["columns"], result["rows"] = db.run(result["sql"])
        result["friendlyResponse"] = chat.ask(
            friendly_prompt(question, result["sql"], result["columns"], result["rows"]))
    except Exception as err:  # noqa: BLE001 - every failure is a data point here
        result["error"] = f"{type(err).__name__}: {err}"
    return result


def print_result(r):
    print("~" * 70)
    print(f"[{r['strategy']}] {r['question']}")
    print(r["sql"])
    if r["error"]:
        print("ERROR:", r["error"])
    else:
        print("Rows:", r["rows"][:10], "..." if len(r["rows"]) > 10 else "")
        print("Answer:", r["friendlyResponse"])


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ask", help="ask a single question")
    parser.add_argument("--strategy", help="only run this strategy")
    args = parser.parse_args()

    cfg = load_config()
    missing = [k for k in ("openaiKey", "databaseUrl") if not cfg[k]]
    if missing:
        sys.exit(f"Missing {', '.join(missing)}: copy bot/config.example.json to bot/config.json "
                 "or set OPENAI_API_KEY / DATABASE_URL.")

    db = Database(cfg["databaseUrl"])
    chat = Chat(cfg["openaiKey"], cfg["model"])
    strategies = build_strategies(db)
    if args.strategy:
        strategies = {args.strategy: strategies[args.strategy]}
    questions = [args.ask] if args.ask else QUESTIONS

    out_dir = HERE / "results"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    all_results = []
    for name, prefix in strategies.items():
        print("#" * 70, f"\nStrategy: {name}")
        results = []
        for q in questions:
            r = answer(q, name, prefix, db, chat)
            print_result(r)
            results.append(r)
            all_results.append(r)
        if not args.ask:
            path = out_dir / f"response_{name}_{stamp}.json"
            path.write_text(json.dumps({"strategy": name, "model": cfg["model"],
                                        "prompt_prefix": prefix, "results": results},
                                       indent=2, ensure_ascii=False))
            print(f"Saved {path.relative_to(ROOT)}")
    if not args.ask:
        path = out_dir / f"examples_{stamp}.md"
        path.write_text(examples_markdown(all_results, cfg["model"]), encoding="utf-8")
        print(f"Saved {path.relative_to(ROOT)} (paste the good and bad ones into the README)")


def examples_markdown(results, model):
    """Every question/SQL/answer as markdown, grouped by question, for the class post."""
    lines = [f"# Example runs ({model})", ""]
    for q in dict.fromkeys(r["question"] for r in results):
        lines += [f"## {q}", ""]
        for r in (x for x in results if x["question"] == q):
            lines += [f"**{r['strategy']}**", "", "```sql", r["sql"] or "", "```", ""]
            if r["error"]:
                lines += [f"Error: `{r['error']}`", ""]
            else:
                lines += [f"Rows: `{json.dumps(r['rows'][:10], ensure_ascii=False)}`", "",
                          f"Answer: {r['friendlyResponse']}", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
