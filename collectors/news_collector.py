"""Headlines from ~80 news feeds (wires, major outlets, central banks, governments, shipping, topic
searches), grouped into stories, for the News tab and for answering questions later.

Every run (every 15 minutes, all week):
  1. Read every direct RSS/Atom feed in shared/news_feeds.json, and half of the Google News
     searches (alternating halves, so each search is read every 30 minutes; Google is the source
     of Reuters, AP and Bloomberg headlines, which have no free feeds of their own).
  2. Keep items published in the last MAX_AGE_HOURS. One row per distinct headline: the same
     headline seen again (another feed, a later run) is not stored twice.
  3. Tag each headline with topics (regular expressions in the feeds file plus the feed's own
     category) and an alert flag (war, sanctions, default, ... unless it is clearly lifestyle).
  4. Group headlines about the same event into a story: word overlap (Jaccard) of at least
     SIMILARITY with a headline seen in the last STORY_WINDOW_HOURS, as World Monitor does.
     A story's importance grows with the number of distinct outlets carrying it, weighted by
     each outlet's rating, plus a bonus for alerts.
  5. Rate each headline's outlet (shared/source_ratings.json: 0-100 from MBFC and Ad Fontes;
     government sources are 'official', unknown outlets 'unrated') and give each story a trust
     score: its best outlet's rating, plus confirmation by other rated outlets, minus hedged
     wording ("reportedly", "sources say", a question mark ...) and denials. High >= 80,
     Medium 60-79, Low < 60; 'Official' when only government sources carry it. This measures
     how well sourced a story is, not whether it is true.

Stores headline, outlet, link, time and a short summary only (no article text: size and copyright).
Headlines are outside text: nothing here acts on them, and the dashboard escapes them.

Tables: news_items, news_stories, news_fts (full-text search), news_feed_status. ~1-3 MB a day.
Usage: python news_collector.py [all]    ("all" reads every Google search this run)
       python news_collector.py rescore  (re-rate every stored headline and story, fetch nothing)
"""

from __future__ import annotations

import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ElementTree
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from options_collector import ET, PROJECT_DIR, connect, finish_run, start_run

FEEDS_PATH = Path(__file__).resolve().parent / "news_feeds.json"  # the installed copy
if not FEEDS_PATH.exists():
    FEEDS_PATH = PROJECT_DIR / "shared" / "news_feeds.json"
RATINGS_PATH = Path(__file__).resolve().parent / "source_ratings.json"
if not RATINGS_PATH.exists():
    RATINGS_PATH = PROJECT_DIR / "shared" / "source_ratings.json"
GNEWS = "https://news.google.com/rss/search?hl=en-US&gl=US&ceid=US:en&q="
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) MarketDashboard/1.0 (personal RSS reader)"
MAX_AGE_HOURS = 72
SUMMARY_CHARS = 300
SIMILARITY = 0.5
STORY_WINDOW_HOURS = 36
GNEWS_PAUSE = 1.2  # seconds between Google searches
ALERT_BONUS = 3.0
OFFICIAL_WEIGHT = 3.0  # importance weight of a government source; a rated outlet weighs 1 + 2 x rating/100
CONFIRM_MIN = 60       # another outlet rated at least this counts as confirming a story
CONFIRM_POINTS, CONFIRM_MAX = 5, 15
HEDGE_POINTS, DENIAL_POINTS = 15, 10
TRUST_HIGH, TRUST_MEDIUM = 80, 60
HEDGE_RE = re.compile(r"\?|\b(reportedly|reports? (say|suggest)|sources? (say|said|tell)|according to sources|people familiar|"
                      r"could|might|alleged(ly)?|unconfirmed|rumou?rs?|purportedly|appears? to)\b", re.I)
# Not hedges on purpose: "may" (the month), "claims" (jobless claims).
DENIAL_RE = re.compile(r"\b(denies|denied|deny|disputes?|disputed|refutes?|debunk(ed|s)?|false|fake|no evidence|retract(s|ed|ion)?)\b", re.I)
# Kept for the old tier column only (no longer used for ranking or trust).
PUBLISHER_TIERS = {"reuters": 1, "associated press": 1, "ap news": 1, "bloomberg": 1, "bloomberg.com": 1,
                   "the wall street journal": 1, "wsj": 1, "financial times": 2, "cnbc": 2, "bbc": 2,
                   "the new york times": 2, "the washington post": 2, "cnn": 2, "politico": 2, "axios": 2,
                   "the guardian": 2, "al jazeera": 2, "npr": 2, "abc news": 2, "cbs news": 2, "nbc news": 2,
                   "fox news": 2, "the hill": 2, "kyiv independent": 2, "the kyiv independent": 2,
                   "ukrinform": 1, "federalreserve.gov": 1, "whitehouse.gov": 1, "the white house (.gov)": 1,
                   "u.s. department of state (.gov)": 1, "u.s. department of defense (.gov)": 1,
                   "u.s. department of the treasury (.gov)": 1, "lloyd's list": 3, "marketwatch": 2,
                   "barron's": 2, "the economist": 2, "nikkei asia": 2, "south china morning post": 2,
                   "the times of israel": 2, "dw": 2, "france 24": 2, "euronews": 2}
STOPWORDS = set("""a an the and or but of to in on at for with from by as is are was were be been it its this that
these those after before over under into about amid against says say said new will would could may might can
up down out off more most than then not no yes his her their our your he she they we you who what why how when
where which while all any some just also live update updates latest report reports news us u.s""".split())

SCHEMA = """
CREATE TABLE IF NOT EXISTS news_items (
    id INTEGER PRIMARY KEY, title_key TEXT UNIQUE, title TEXT, source TEXT, feed TEXT, tier INTEGER,
    link TEXT, published_at TEXT, first_seen TEXT, summary TEXT, topics TEXT, alert INTEGER, story_id INTEGER
);
CREATE INDEX IF NOT EXISTS news_items_seen ON news_items (first_seen);
CREATE INDEX IF NOT EXISTS news_items_published ON news_items (published_at);
CREATE INDEX IF NOT EXISTS news_items_story ON news_items (story_id);
-- One row per event covered by one or more headlines. topics is ",a,b," so LIKE '%,fed,%' works.
CREATE TABLE IF NOT EXISTS news_stories (
    id INTEGER PRIMARY KEY, title TEXT, link TEXT, best_tier INTEGER, first_seen TEXT, last_seen TEXT,
    first_published TEXT, n_items INTEGER, n_sources INTEGER, sources TEXT, topics TEXT, alert INTEGER,
    importance REAL
);
CREATE INDEX IF NOT EXISTS news_stories_seen ON news_stories (last_seen);
CREATE VIRTUAL TABLE IF NOT EXISTS news_fts USING fts5(
    title, summary, source, content='news_items', content_rowid='id', tokenize='porter unicode61'
);
CREATE TABLE IF NOT EXISTS news_feed_status (
    feed TEXT PRIMARY KEY, last_try TEXT, last_ok TEXT, items INTEGER, error TEXT
);
"""
# Added 2026-11-10: outlet ratings and story trust. outlet = the rated outlet's name, 'official', or NULL (unrated).
ADDED = {"news_items": (("outlet", "TEXT"), ("rating", "REAL")),
         "news_stories": (("best_rating", "REAL"), ("trust", "REAL"), ("trust_label", "TEXT"), ("trust_why", "TEXT"))}


def load_ratings() -> dict:
    r = json.loads(RATINGS_PATH.read_text())
    r["alias_list"] = sorted(r["aliases"].items(), key=lambda kv: -len(kv[0]))
    return r


def rate_source(ratings: dict, *names: str) -> tuple[str | None, float | None]:
    """(outlet, rating) for a headline: ('official', None) for government sources, (None, unrated) if unknown.
    Tries each name (the publisher, then the feed) by exact alias, then by the longest alias it starts with."""
    for raw in names:
        name = (raw or "").strip().lower()
        if not name:
            continue
        if "(.gov)" in name or name.endswith(".gov") or any(name == o or name.startswith(o + " ") for o in ratings["official"]):
            return "official", None
        hit = ratings["aliases"].get(name) or next((v for k, v in ratings["alias_list"]
                                                    if name.startswith(k + " ") or name.startswith(k + " -")), None)
        if hit:
            return hit, float(ratings["outlets"][hit]["rating"])
    return None, float(ratings["unrated"])


def score_story(rows: list) -> tuple[float | None, str, str, float | None, float]:
    """rows: (title, source, outlet, rating) per headline. Returns trust, label, why, best rating, importance weight."""
    by_outlet: dict[str, float | None] = {}
    for title, source, outlet, rating in rows:
        key = outlet or f"unrated:{(source or '').lower()}"
        if key not in by_outlet or (rating or 0) > (by_outlet[key] or 0):
            by_outlet[key] = rating
    weight = sum(OFFICIAL_WEIGHT if k == "official" else 1 + 2 * (v or 0) / 100 for k, v in by_outlet.items())
    rated = sorted((v for k, v in by_outlet.items() if k != "official" and v is not None), reverse=True)
    official = "official" in by_outlet
    if not rated:
        return None, "Official", "only government sources", None, weight
    best = rated[0]
    confirmers = sum(1 for v in rated[1:] if v >= CONFIRM_MIN) + (1 if official else 0)
    lead = rows[0][0]
    hedged = bool(HEDGE_RE.search(lead))
    denied = any(DENIAL_RE.search(r[0]) for r in rows)
    trust = best + min(CONFIRM_MAX, CONFIRM_POINTS * confirmers) - (HEDGE_POINTS if hedged else 0) - (DENIAL_POINTS if denied else 0)
    trust = max(0.0, min(100.0, trust))
    label = "High" if trust >= TRUST_HIGH else "Medium" if trust >= TRUST_MEDIUM else "Low"
    why = [f"best outlet {best:.0f}"]
    if confirmers:
        why.append(f"+{min(CONFIRM_MAX, CONFIRM_POINTS * confirmers)} confirmed by {confirmers} more")
    if hedged:
        why.append(f"-{HEDGE_POINTS} hedged wording")
    if denied:
        why.append(f"-{DENIAL_POINTS} denial or dispute")
    return trust, label, "; ".join(why), best, weight


def update_story(db, sid: int, last_seen: str | None) -> None:
    rows = db.execute("SELECT title, link, source, outlet, rating, topics, alert, published_at, tier FROM news_items "
                      "WHERE story_id = ? ORDER BY (outlet = 'official'), rating DESC, published_at", (sid,)).fetchall()
    if not rows:
        return
    # A story's topics: those carried by at least a third of its headlines (one stray
    # mention in one summary doesn't make an espionage story a Fed story).
    counts: dict[str, int] = {}
    for r in rows:
        for t in r[5].strip(",").split(","):
            if t:
                counts[t] = counts.get(t, 0) + 1
    topics = sorted(t for t, c in counts.items() if c >= max(1, len(rows) / 3))
    alert = int(any(r[6] for r in rows))
    trust, label, why, best, weight = score_story([(r[0], r[2], r[3], r[4]) for r in rows])
    importance = weight + (ALERT_BONUS if alert else 0)
    sources = sorted({r[2] for r in rows})
    lead = rows[0]  # best-rated outlet, then earliest: the headline shown for the story
    db.execute("UPDATE news_stories SET title=?, link=?, best_tier=?, last_seen=COALESCE(?, last_seen), first_published=?, "
               "n_items=?, n_sources=?, sources=?, topics=?, alert=?, importance=?, best_rating=?, trust=?, trust_label=?, "
               "trust_why=? WHERE id=?",
               (lead[0], lead[1], min(r[8] for r in rows), last_seen, min(r[7] for r in rows), len(rows), len(sources),
                json.dumps(sources[:30]), "," + ",".join(topics) + ",", alert, importance, best, trust, label, why, sid))


def ensure_columns(db) -> None:
    for table, columns in ADDED.items():
        have = {r[1] for r in db.execute(f"PRAGMA table_info({table})")}
        for col, typ in columns:
            if col not in have:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
    db.commit()


def rescore(db) -> int:
    """Re-rate every stored headline and story from the current ratings file. Fetches nothing."""
    ratings = load_ratings()
    feeds = {r[0]: r[1] for r in db.execute("SELECT id, feed FROM news_items")}
    for iid, source in db.execute("SELECT id, source FROM news_items").fetchall():
        outlet, rating = rate_source(ratings, source, feeds[iid])
        db.execute("UPDATE news_items SET outlet=?, rating=? WHERE id=?", (outlet, rating, iid))
    sids = [r[0] for r in db.execute("SELECT id FROM news_stories")]
    for sid in sids:
        update_story(db, sid, None)
    db.commit()
    return len(sids)


def load_config() -> dict:
    cfg = json.loads(FEEDS_PATH.read_text())
    cfg["topic_res"] = {k: re.compile(v, re.I) for k, v in cfg["topics"].items() if not k.startswith("_")}
    words = "|".join(re.escape(w) for w in cfg["alert_keywords"])
    cfg["alert_re"] = re.compile(rf"\b({words})", re.I)
    cfg["exclude_re"] = re.compile("|".join(re.escape(w) for w in cfg["alert_exclusions"]), re.I)
    return cfg


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/xml, text/xml, */*"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def clean(text: str | None) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def parse_date(text: str | None) -> datetime | None:
    if not text:
        return None
    text = re.sub(r"\s+", " ", text).strip()
    try:
        d = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        try:
            d = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            for fmt in ("%A, %B %d, %Y - %H:%M", "%B %d, %Y", "%Y-%m-%d %H:%M:%S", "%d %B %Y", "%y-%m-%d %H:%M"):
                try:
                    d = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
            else:
                return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def parse_feed(raw: bytes) -> list[dict]:
    """RSS 2.0, RSS 1.0 (RDF) and Atom. Returns title, link, summary, published, publisher."""
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError:
        # Some feeds have stray characters before the XML or unescaped ampersands.
        fixed = re.sub(rb"&(?!(amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)", b"&amp;", raw.lstrip())
        root = ElementTree.fromstring(fixed)
    items = []
    for el in root.iter():
        if local(el.tag) not in ("item", "entry"):
            continue
        rec = {"title": "", "link": "", "summary": "", "published": None, "publisher": None}
        for child in el:
            name = local(child.tag)
            if name == "title":
                rec["title"] = clean("".join(child.itertext()))
            elif name == "link":
                rec["link"] = rec["link"] or (child.get("href") or (child.text or "")).strip()
            elif name in ("description", "summary", "content", "encoded") and not rec["summary"]:
                rec["summary"] = clean("".join(child.itertext()))
            elif name in ("pubdate", "published", "updated", "date") and rec["published"] is None:
                rec["published"] = parse_date(child.text)
            elif name == "source":
                rec["publisher"] = clean(child.text) or None
        if rec["title"]:
            items.append(rec)
    return items


def title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()[:300]


def tokens(title: str) -> frozenset:
    return frozenset(w for w in re.findall(r"[a-z0-9]+", title.lower()) if len(w) > 2 and w not in STOPWORDS)


def jaccard(a: frozenset, b: frozenset) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def split_publisher(title: str, publisher: str | None, is_gnews: bool) -> tuple[str, str | None]:
    """Google News titles end with ' - Outlet'; take it off and use it as the outlet."""
    if is_gnews and " - " in title:
        head, tail = title.rsplit(" - ", 1)
        if len(tail) <= 60:
            return head.strip(), publisher or tail.strip()
    return title, publisher


def classify(cfg: dict, title: str, summary: str, category: str) -> tuple[str, int]:
    text = f"{title} {summary}"
    # The feed's own category only when nothing else fits: a WSJ Markets spy story is not markets.
    topics = {k for k, rx in cfg["topic_res"].items() if rx.search(text)} or {category}
    alert = int(bool(cfg["alert_re"].search(title)) and not cfg["exclude_re"].search(title))
    return "," + ",".join(sorted(topics)) + ",", alert


def read_feeds(cfg: dict, read_all: bool) -> tuple[list[tuple[dict, list[dict]]], dict[str, str]]:
    feeds = cfg["feeds"]
    direct = [f for f in feeds if not f["url"].startswith("gnews:")]
    searches = [f for f in feeds if f["url"].startswith("gnews:")]
    if not read_all:
        half = (datetime.now(ET).hour * 4 + datetime.now(ET).minute // 15) % 2
        searches = searches[half::2]
    results, errors = [], {}

    def one(feed):
        url = GNEWS + urllib.parse.quote(feed["url"][6:]) if feed["url"].startswith("gnews:") else feed["url"]
        try:
            return feed, parse_feed(fetch(url)), None
        except urllib.error.HTTPError as e:
            return feed, [], f"HTTP {e.code}"
        except Exception as e:  # network, parse: record and move on, one feed never stops the run
            return feed, [], f"{type(e).__name__}: {str(e)[:120]}"

    with ThreadPoolExecutor(max_workers=8) as pool:
        out = list(pool.map(one, direct))
    for feed in searches:
        out.append(one(feed))
        time.sleep(GNEWS_PAUSE)
    for feed, items, err in out:
        if err:
            errors[feed["name"]] = err
        else:
            results.append((feed, items))
    return results, errors


def main() -> int:
    db = connect()
    db.executescript(SCHEMA)
    ensure_columns(db)
    if len(sys.argv) > 1 and sys.argv[1] == "rescore":
        run_id = start_run(db, "news")
        n = rescore(db)
        finish_run(db, run_id, "ok", n, f"rescored {n} stories from {RATINGS_PATH.name}")
        print(f"rescored {n} stories")
        return 0
    # The search index isn't backed up; after a restore (or if it ever drifts) rebuild it from news_items.
    if db.execute("SELECT count(*) FROM news_fts_docsize").fetchone()[0] != db.execute("SELECT count(*) FROM news_items").fetchone()[0]:
        db.execute("INSERT INTO news_fts (news_fts) VALUES ('rebuild')")
        db.commit()
    run_id = start_run(db, "news")
    now = datetime.now(ET)
    now_s = now.isoformat(timespec="seconds")
    try:
        cfg = load_config()
        ratings = load_ratings()
        results, errors = read_feeds(cfg, len(sys.argv) > 1 and sys.argv[1] == "all")
        cutoff = now - timedelta(hours=MAX_AGE_HOURS)

        # Recent headlines, for grouping new ones into stories.
        window = (now - timedelta(hours=STORY_WINDOW_HOURS)).isoformat(timespec="seconds")
        recent = [(tokens(t), sid) for t, sid in db.execute(
            "SELECT title, story_id FROM news_items WHERE first_seen >= ?", (window,))]

        read_before = {r[0] for r in db.execute("SELECT feed FROM news_feed_status WHERE last_ok IS NOT NULL")}
        new_items = 0
        touched: set[int] = set()
        for feed, items in results:
            is_gnews = feed["url"].startswith("gnews:")
            for rec in items:
                pub = rec["published"]
                if pub is None and feed["name"] not in read_before:
                    continue  # undated items on a feed's first read are old backlog, not news
                if pub is None or pub > now + timedelta(hours=1):
                    pub = now  # undated (on a feed read before) or future-dated: treat as seen now
                if pub < cutoff:
                    continue
                title, publisher = split_publisher(rec["title"], rec["publisher"], is_gnews)
                key = title_key(title)
                if not key or db.execute("SELECT 1 FROM news_items WHERE title_key = ?", (key,)).fetchone():
                    continue
                source = publisher or feed["name"]
                tier = PUBLISHER_TIERS.get(source.lower(), feed["tier"]) if is_gnews else feed["tier"]
                outlet, rating = rate_source(ratings, source, feed["name"])
                summary = rec["summary"]
                if summary.lower().startswith(title.lower()[:40]):  # Google repeats the title as the summary
                    summary = ""
                summary = summary[:SUMMARY_CHARS]
                topics, alert = classify(cfg, title, summary, feed["category"])

                toks = tokens(title)
                best, best_sim = None, 0.0
                for other, sid in recent:
                    sim = jaccard(toks, other)
                    if sim > best_sim:
                        best, best_sim = sid, sim
                if best is None or best_sim < SIMILARITY:
                    best = db.execute("INSERT INTO news_stories (title, link, best_tier, first_seen, first_published, "
                                      "n_items, n_sources, sources, topics, alert, importance) VALUES (?,?,?,?,?,0,0,'[]',?,?,0)",
                                      (title, rec["link"], tier, now_s, pub.astimezone(ET).isoformat(timespec="seconds"),
                                       topics, alert)).lastrowid
                cur = db.execute("INSERT INTO news_items (title_key, title, source, feed, tier, link, published_at, "
                                 "first_seen, summary, topics, alert, story_id, outlet, rating) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                 (key, title, source, feed["name"], tier, rec["link"],
                                  pub.astimezone(ET).isoformat(timespec="seconds"), now_s, summary, topics, alert, best,
                                  outlet, rating))
                db.execute("INSERT INTO news_fts (rowid, title, summary, source) VALUES (?,?,?,?)",
                           (cur.lastrowid, title, summary, source))
                recent.append((toks, best))
                touched.add(best)
                new_items += 1

        for sid in touched:
            update_story(db, sid, now_s)

        for feed, items in results:
            db.execute("INSERT INTO news_feed_status VALUES (?,?,?,?,NULL) ON CONFLICT(feed) DO UPDATE SET "
                       "last_try=excluded.last_try, last_ok=excluded.last_ok, items=excluded.items, error=NULL",
                       (feed["name"], now_s, now_s, len(items)))
        for name, err in errors.items():
            db.execute("INSERT INTO news_feed_status (feed, last_try, error) VALUES (?,?,?) ON CONFLICT(feed) DO UPDATE "
                       "SET last_try=excluded.last_try, error=excluded.error", (name, now_s, err))
        db.commit()

        tried = len(results) + len(errors)
        # A few dead feeds are normal (sites change); only a run where most fail is a problem.
        status = "ok" if len(results) >= 0.6 * tried else ("partial" if results else "failed")
        detail = (f"feeds_ok={len(results)}/{tried} new_headlines={new_items} stories_touched={len(touched)}"
                  + (f" failing: {'; '.join(f'{k} ({v})' for k, v in sorted(errors.items()))}" if errors else ""))
    except Exception as ex:
        db.rollback()
        status, new_items, detail = "failed", 0, f"{type(ex).__name__}: {ex}"
    finish_run(db, run_id, status, new_items, detail)
    print(f"[{datetime.now(ET):%Y-%m-%d %H:%M:%S}] news run {run_id}: {status} {detail[:500]}")
    return 0 if status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
