"""SQLite persistence: mastery state, sessions, and every graded response.

Kept deliberately boring. The graph and coverage are derived from the vault on
each run and never stored; what lives here is the part that cannot be
recomputed -- what was asked, what was answered, and how mastery moved.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from .config import MasteryParams
from .mastery import Mastery

SCHEMA = """
CREATE TABLE IF NOT EXISTS mastery (
    concept      TEXT PRIMARY KEY,
    strength     REAL NOT NULL,
    half_life    REAL NOT NULL,
    last_tested  TEXT,
    n_correct    INTEGER NOT NULL DEFAULT 0,
    n_total      INTEGER NOT NULL DEFAULT 0,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    topic        TEXT NOT NULL,
    goal         TEXT,
    targets      TEXT NOT NULL,          -- json list of concept ids
    phase        TEXT NOT NULL,          -- calibrating|exploring|examining|closed
    started_at   TEXT NOT NULL,
    closed_at    TEXT,
    summary      TEXT,
    material     TEXT                    -- json: notes/books offered
);

CREATE TABLE IF NOT EXISTS responses (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   INTEGER NOT NULL REFERENCES sessions(id),
    phase        TEXT NOT NULL,          -- calibration|exam
    concept      TEXT NOT NULL,
    question     TEXT NOT NULL,
    response     TEXT,
    verdict      TEXT NOT NULL,          -- correct|partial|incorrect
    note         TEXT,
    asked_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS questions (
    id           TEXT PRIMARY KEY,
    concept      TEXT NOT NULL,
    text         TEXT NOT NULL,
    kind         TEXT NOT NULL DEFAULT 'application',
    difficulty   INTEGER NOT NULL DEFAULT 3,
    asked        INTEGER NOT NULL DEFAULT 0,
    correct      INTEGER NOT NULL DEFAULT 0,
    streak       INTEGER NOT NULL DEFAULT 0,
    last_asked   TEXT,
    last_verdict TEXT,
    retired      INTEGER NOT NULL DEFAULT 0,
    source       TEXT NOT NULL DEFAULT 'session',
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reviews (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   INTEGER,
    concept      TEXT NOT NULL,
    language     TEXT,
    ratings      TEXT NOT NULL,         -- json: dimension -> 1..5
    issues       TEXT NOT NULL,         -- json list
    summary      TEXT,
    lines        INTEGER NOT NULL DEFAULT 0,
    overall      REAL NOT NULL,
    verdict      TEXT NOT NULL,
    reviewed_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_rev_concept ON reviews(concept);
CREATE INDEX IF NOT EXISTS ix_q_concept ON questions(concept);
CREATE INDEX IF NOT EXISTS ix_resp_session ON responses(session_id);
CREATE INDEX IF NOT EXISTS ix_resp_concept ON responses(concept);
CREATE INDEX IF NOT EXISTS ix_sessions_phase ON sessions(phase);
"""


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _dt(s: str | None) -> datetime | None:
    if not s:
        return None
    d = datetime.fromisoformat(s)
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def _row_to_question(r):
    from .questions import Question
    return Question(
        id=r["id"], concept=r["concept"], text=r["text"], kind=r["kind"],
        difficulty=r["difficulty"], asked=r["asked"], correct=r["correct"],
        streak=r["streak"], last_asked=_dt(r["last_asked"]),
        last_verdict=r["last_verdict"] or "", retired=bool(r["retired"]),
        source=r["source"])


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(SCHEMA)
        self._migrate()
        self.db.commit()

    def _migrate(self) -> None:
        """Additive migrations, so an existing database keeps working."""
        cols = {r["name"] for r in self.db.execute("PRAGMA table_info(responses)")}
        if "question_id" not in cols:
            self.db.execute("ALTER TABLE responses ADD COLUMN question_id TEXT")

    def close(self) -> None:
        self.db.close()

    # -- mastery --------------------------------------------------------
    def get_mastery(self, concept: str, p: MasteryParams) -> Mastery:
        r = self.db.execute("SELECT * FROM mastery WHERE concept=?", (concept,)).fetchone()
        if r is None:
            from .mastery import initial
            return initial(concept, p)
        return Mastery(concept=r["concept"], strength=r["strength"], half_life=r["half_life"],
                       last_tested=_dt(r["last_tested"]),
                       n_correct=r["n_correct"], n_total=r["n_total"])

    def all_mastery(self) -> dict:
        out = {}
        for r in self.db.execute("SELECT * FROM mastery"):
            out[r["concept"]] = Mastery(
                concept=r["concept"], strength=r["strength"], half_life=r["half_life"],
                last_tested=_dt(r["last_tested"]),
                n_correct=r["n_correct"], n_total=r["n_total"])
        return out

    def save_mastery(self, m: Mastery) -> None:
        self.db.execute(
            """INSERT INTO mastery(concept,strength,half_life,last_tested,n_correct,n_total,updated_at)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(concept) DO UPDATE SET
                 strength=excluded.strength, half_life=excluded.half_life,
                 last_tested=excluded.last_tested, n_correct=excluded.n_correct,
                 n_total=excluded.n_total, updated_at=excluded.updated_at""",
            (m.concept, m.strength, m.half_life, _iso(m.last_tested),
             m.n_correct, m.n_total, datetime.now(UTC).isoformat()))
        self.db.commit()

    def effective_map(self, at: datetime | None = None) -> dict:
        """concept id -> decayed strength, for the graph's frontier maths."""
        return {c: m.effective(at) for c, m in self.all_mastery().items()}

    # -- sessions -------------------------------------------------------
    def open_session(self, topic: str, targets: list, goal: str | None = None) -> int:
        cur = self.db.execute(
            """INSERT INTO sessions(topic,goal,targets,phase,started_at)
               VALUES(?,?,?,?,?)""",
            (topic, goal, json.dumps(targets), "calibrating",
             datetime.now(UTC).isoformat()))
        self.db.commit()
        return int(cur.lastrowid)

    def set_phase(self, sid: int, phase: str) -> None:
        self.db.execute("UPDATE sessions SET phase=? WHERE id=?", (phase, sid))
        self.db.commit()

    def set_material(self, sid: int, material: dict) -> None:
        self.db.execute("UPDATE sessions SET material=? WHERE id=?",
                        (json.dumps(material), sid))
        self.db.commit()

    def close_session(self, sid: int, summary: str) -> None:
        self.db.execute(
            "UPDATE sessions SET phase='closed', closed_at=?, summary=? WHERE id=?",
            (datetime.now(UTC).isoformat(), summary, sid))
        self.db.commit()

    def session(self, sid: int):
        r = self.db.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
        return dict(r) if r else None

    def active_session(self):
        r = self.db.execute(
            "SELECT * FROM sessions WHERE phase!='closed' ORDER BY id DESC LIMIT 1").fetchone()
        return dict(r) if r else None

    def recent_sessions(self, limit: int = 12) -> list:
        return [dict(r) for r in self.db.execute(
            "SELECT * FROM sessions ORDER BY id DESC LIMIT ?", (limit,))]

    # -- responses ------------------------------------------------------
    def add_response(self, sid: int, phase: str, concept: str, question: str,
                     response: str | None, verdict: str, note: str | None = None,
                     question_id: str | None = None) -> None:
        self.db.execute(
            """INSERT INTO responses(session_id,phase,concept,question,response,
                                     verdict,note,asked_at,question_id)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (sid, phase, concept, question, response, verdict, note,
             datetime.now(UTC).isoformat(), question_id))
        self.db.commit()

    # -- question bank ---------------------------------------------------
    def get_question(self, qid: str):
        r = self.db.execute("SELECT * FROM questions WHERE id=?", (qid,)).fetchone()
        return _row_to_question(r) if r else None

    def questions_for(self, concept: str, include_retired: bool = True) -> list:
        q = "SELECT * FROM questions WHERE concept=?"
        if not include_retired:
            q += " AND retired=0"
        return [_row_to_question(r) for r in self.db.execute(q, (concept,))]

    def all_questions(self) -> list:
        return [_row_to_question(r) for r in self.db.execute("SELECT * FROM questions")]

    def save_question(self, q) -> None:
        self.db.execute(
            """INSERT INTO questions(id,concept,text,kind,difficulty,asked,correct,
                                     streak,last_asked,last_verdict,retired,source,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 concept=excluded.concept, text=excluded.text, kind=excluded.kind,
                 difficulty=excluded.difficulty, asked=excluded.asked,
                 correct=excluded.correct, streak=excluded.streak,
                 last_asked=excluded.last_asked, last_verdict=excluded.last_verdict,
                 retired=excluded.retired""",
            (q.id, q.concept, q.text, q.kind, q.difficulty, q.asked, q.correct,
             q.streak, _iso(q.last_asked), q.last_verdict or None,
             1 if q.retired else 0, q.source,
             datetime.now(UTC).isoformat()))
        self.db.commit()

    # -- reviews ---------------------------------------------------------
    def add_review(self, r, session_id=None) -> int:
        cur = self.db.execute(
            """INSERT INTO reviews(session_id,concept,language,ratings,issues,
                                   summary,lines,overall,verdict,reviewed_at)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (session_id, r.concept, r.language, json.dumps(r.ratings),
             json.dumps(r.issues), r.summary, r.lines, r.overall, r.verdict,
             datetime.now(UTC).isoformat()))
        self.db.commit()
        return int(cur.lastrowid)

    def reviews_for(self, concept: str) -> list:
        from .review import Review
        out = []
        for row in self.db.execute(
                "SELECT * FROM reviews WHERE concept=? ORDER BY id DESC", (concept,)):
            out.append(Review(
                id=row["id"], concept=row["concept"], language=row["language"] or "",
                ratings=json.loads(row["ratings"]), issues=json.loads(row["issues"]),
                summary=row["summary"] or "", lines=row["lines"],
                reviewed_at=_dt(row["reviewed_at"])))
        return out

    def question_stats(self) -> dict:
        one = lambda q: self.db.execute(q).fetchone()[0]
        return {
            "questions": one("SELECT COUNT(*) FROM questions"),
            "reviews": one("SELECT COUNT(*) FROM reviews"),
            "retired": one("SELECT COUNT(*) FROM questions WHERE retired=1"),
            "never_asked": one("SELECT COUNT(*) FROM questions WHERE asked=0"),
            "missed_at_least_once": one(
                "SELECT COUNT(*) FROM questions WHERE asked>correct"),
        }

    def responses(self, sid: int, phase: str | None = None) -> list:
        q = "SELECT * FROM responses WHERE session_id=?"
        args: list = [sid]
        if phase:
            q += " AND phase=?"
            args.append(phase)
        return [dict(r) for r in self.db.execute(q + " ORDER BY id", args)]

    def history(self, concept: str, limit: int = 20) -> list:
        return [dict(r) for r in self.db.execute(
            """SELECT r.*, s.topic FROM responses r JOIN sessions s ON s.id=r.session_id
               WHERE r.concept=? ORDER BY r.id DESC LIMIT ?""", (concept, limit))]

    def stats(self) -> dict:
        one = lambda q: self.db.execute(q).fetchone()[0]
        return {
            **self.question_stats(),
            "sessions": one("SELECT COUNT(*) FROM sessions"),
            "closed": one("SELECT COUNT(*) FROM sessions WHERE phase='closed'"),
            "responses": one("SELECT COUNT(*) FROM responses"),
            "concepts_tracked": one("SELECT COUNT(*) FROM mastery"),
        }
