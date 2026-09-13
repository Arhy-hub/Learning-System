"""Configuration.

There is one path that matters: the brain, which is the mentor's own Obsidian
vault and its only source of truth. The user's personal vault is deliberately
not read — inferring "he understands this" from the existence of a note proved
misleading, so the mentor knows only what it has actually tested.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("MENTOR_DATA", PKG_ROOT / "data"))

# Sections of a concept page the mentor maintains. Anything else a human adds
# to a page is preserved untouched.
OWNED_SECTIONS = ("Material", "Understanding", "Where he slips", "What worked",
                  "Open questions", "Prerequisites", "Similar", "Questions",
                  "Reviews", "History")


@dataclass(frozen=True)
class MasteryParams:
    """Tunables for the strength/half-life model. See mastery.py."""
    initial_strength: float = 0.30
    initial_half_life: float = 3.0
    min_half_life: float = 1.0
    max_half_life: float = 365.0
    success_growth: float = 1.8      # half-life multiplier on a correct answer
    failure_shrink: float = 0.4      # half-life multiplier on a miss
    strength_gain: float = 0.35      # move toward 1.0 by this fraction on success
    strength_loss: float = 0.50      # move toward 0.0 by this fraction on failure
    mastered_at: float = 0.80        # effective strength counting as mastered
    due_at: float = 0.60             # effective strength below which review is due


@dataclass(frozen=True)
class Config:
    data_dir: Path = field(default_factory=lambda: DATA_DIR)
    mastery: MasteryParams = field(default_factory=MasteryParams)

    @property
    def brain_dir(self) -> Path:
        """The mentor's Obsidian vault: its memory, and the only thing it reads."""
        return Path(os.environ.get("MENTOR_BRAIN", self.data_dir / "brain"))

    @property
    def db_path(self) -> Path:
        return self.data_dir / "mentor.db"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.brain_dir.mkdir(parents=True, exist_ok=True)


_cfg: Config | None = None


def get_config() -> Config:
    global _cfg
    if _cfg is None:
        _cfg = Config()
        _cfg.ensure_dirs()
    return _cfg
