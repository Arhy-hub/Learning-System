"""Tests for the mentor engine.

Every test runs against a throwaway brain in tmp_path, so the suite never
touches a real one.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from mentor.brain import Brain, parse, slug
from mentor.config import Config, MasteryParams
from mentor.engine import Engine
from mentor.graph import ConceptGraph
from mentor.mastery import Mastery, apply_result, initial, now
from mentor.text import canon, content_words, decamel, jaccard, transliterate


@pytest.fixture()
def engine(tmp_path):
    return Engine(Config(data_dir=tmp_path))


@pytest.fixture()
def taught(engine):
    """An engine with one real session behind it."""
    engine.session_start("Compactness", track="Analysis",
                         prereqs=["Open and closed sets", "Sequences"])
    engine.calibration_submit([
        {"concept": "Compactness", "question": "define it",
         "response": "closed and bounded", "verdict": "partial"},
        {"concept": "Open and closed sets", "question": "is [0,1) open?",
         "response": "no", "verdict": "correct"}])
    engine.exam_submit([
        {"concept": "Compactness", "question": "show (0,1) is not compact",
         "response": "cover by (1/n,1)", "verdict": "correct"}])
    engine.session_end("open-cover definition now leads", concepts={
        "Compactness": {"understanding": "Holds the open-cover definition.",
                        "slips": "- Reaches for closed-and-bounded first.",
                        "worked": "A non-compact set in a general metric space.",
                        "open": "- Sequential compactness?",
                        "prereqs": ["Open and closed sets", "Sequences"],
                        "track": "Analysis"}})
    return engine


# ---------------------------------------------------------------------- text
class TestText:
    def test_canon(self):
        assert canon("Metric Spaces") == "metric space"
        assert canon("  Linear   Maps ") == "linear map"

    def test_word_order_differs_but_words_match(self):
        a, b = "Eigenvalues and eigenvectors", "Eigenvectors and Eigenvalues"
        assert canon(a) != canon(b)
        assert content_words(a) == content_words(b)

    def test_maths_symbols_survive_as_words(self):
        assert canon("σ-algebras") == "sigma algebra"
        assert canon("Completeness of ℝ") == "completeness of r"
        assert canon("Itô calculus") == "ito calculus"
        assert "R" in transliterate("ℝ")

    def test_gloss_after_dash_is_dropped(self):
        assert canon("Variational Autoencoders (VAEs) — ELBO derivation") \
            == "variational autoencoder vae"

    def test_acronym_plurals_stay_whole(self):
        assert decamel("StochasticProcesses") == "Stochastic Processes"
        assert canon("CNNs") == "cnn"

    def test_jaccard(self):
        assert jaccard(frozenset("ab"), frozenset("ab")) == 1.0
        assert jaccard(frozenset(), frozenset("a")) == 0.0


# --------------------------------------------------------------------- brain
class TestBrain:
    def test_creates_a_real_obsidian_vault(self, tmp_path):
        b = Brain(tmp_path / "brain")
        assert (b.root / ".obsidian" / "app.json").exists()
        assert (b.root / "README.md").exists()
        assert (b.root / "Concepts").is_dir()

    def test_roundtrips_frontmatter_and_sections(self, tmp_path):
        b = Brain(tmp_path / "brain")
        p = b.write(b.concept_path("Compactness", "Analysis"), "Compactness",
                    {"concept": "compactness", "prereqs": ["Open sets"], "attempts": 2},
                    {"Understanding": "solid", "History": "| a |"})
        page = parse(p)
        assert page.frontmatter["attempts"] == 2
        assert page.prereqs == ["Open sets"]
        assert page.section("Understanding") == "solid"

    def test_preserves_sections_it_does_not_own(self, tmp_path):
        b = Brain(tmp_path / "brain")
        path = b.concept_path("X", "T")
        b.write(path, "X", {}, {"Understanding": "v1"})
        path.write_text(path.read_text(encoding="utf-8") + "\n## My own notes\n\nkeep me\n",
                        encoding="utf-8")
        b.write(path, "X", {}, {"Understanding": "v2"})
        page = parse(path)
        assert page.section("Understanding") == "v2", "owned section is rewritten"
        assert page.section("My own notes") == "keep me", "hand edits survive"

    def test_finds_a_page_wherever_it_was_filed(self, tmp_path):
        b = Brain(tmp_path / "brain")
        b.write(b.concept_path("Compactness", "Analysis"), "Compactness",
                {"concept": "compactness"}, {})
        moved = b.root / "Concepts" / "Elsewhere" / "Compactness.md"
        moved.parent.mkdir(parents=True)
        moved.write_text((b.root / "Concepts" / "Analysis" / "Compactness.md")
                         .read_text(encoding="utf-8"), encoding="utf-8")
        (b.root / "Concepts" / "Analysis" / "Compactness.md").unlink()
        assert b.find("compactness") is not None

    def test_slug_strips_path_hostile_characters(self):
        assert "/" not in slug("a/b") and "#" not in slug("a#b")


# --------------------------------------------------------------------- graph
class TestGraph:
    def test_empty_brain_is_an_empty_graph(self, tmp_path):
        g = ConceptGraph(Brain(tmp_path / "b"))
        assert g.nodes == {} and g.cycles == []

    def test_prereqs_come_from_frontmatter(self, taught):
        n = taught.graph.get("Compactness")
        assert set(taught.graph.prereqs(n.id)) == {"open and closed set", "sequence"}

    def test_dependents_are_the_inverse(self, taught):
        assert "compactness" in taught.graph.dependents("open and closed set")

    def test_no_cycles_from_a_normal_session(self, taught):
        assert taught.graph.cycles == []

    def test_cycle_is_reported_not_silently_broken(self, tmp_path):
        b = Brain(tmp_path / "brain")
        b.write(b.concept_path("A", "T"), "A", {"concept": "a", "prereqs": ["B"]}, {})
        b.write(b.concept_path("B", "T"), "B", {"concept": "b", "prereqs": ["A"]}, {})
        assert ConceptGraph(b).cycles, "a two-node cycle must be detected"

    def test_unresolved_prereq_is_surfaced(self, tmp_path):
        b = Brain(tmp_path / "brain")
        b.write(b.concept_path("A", "T"), "A",
                {"concept": "a", "prereqs": ["Nonexistent"]}, {})
        assert ConceptGraph(b).unresolved

    def test_path_is_topologically_ordered(self, taught):
        p = taught.graph.path_to("compactness", {})
        assert p.index("open and closed set") < p.index("compactness")

    def test_frontier_non_empty_on_a_cold_graph(self, taught):
        assert taught.graph.frontier({}, None, 5)


# ------------------------------------------------------------------- mastery
class TestMastery:
    P = MasteryParams()

    def test_untested_reads_zero(self):
        assert initial("x", self.P).effective() == 0.0

    def test_correct_raises_strength_and_stretches_half_life(self):
        m = initial("x", self.P)
        a = apply_result(m, "correct", self.P)
        assert a.strength > m.strength and a.half_life > m.half_life

    def test_miss_drops_strength_and_collapses_half_life(self):
        m = apply_result(initial("x", self.P), "correct", self.P)
        a = apply_result(m, "incorrect", self.P)
        assert a.strength < m.strength and a.half_life < m.half_life

    def test_decay_halves_over_one_half_life(self):
        t = now()
        m = Mastery("x", strength=0.8, half_life=10.0, last_tested=t, n_total=1)
        assert m.effective(t + timedelta(days=10)) == pytest.approx(0.4, abs=1e-3)

    def test_becomes_due_once_decayed(self):
        t = now()
        m = Mastery("x", strength=0.95, half_life=2.0, last_tested=t, n_total=1)
        assert not m.is_due(self.P, t)
        assert m.is_due(self.P, t + timedelta(days=8))

    def test_calibration_counts_for_less_than_an_exam(self):
        m = initial("x", self.P)
        assert apply_result(m, "correct", self.P, weight=0.6).strength \
            < apply_result(m, "correct", self.P, weight=1.0).strength

    def test_partial_sits_between(self):
        m = initial("x", self.P)
        assert apply_result(m, "incorrect", self.P).strength \
            < apply_result(m, "partial", self.P).strength \
            < apply_result(m, "correct", self.P).strength


# ----------------------------------------------------------------- knowledge
class TestKnowledge:
    def test_untested_concept_is_never_called_known(self, taught):
        from mentor.knowledge import PRIOR_CEILING
        for k in taught.knowledge.all().values():
            if not k.verified:
                assert k.estimate <= PRIOR_CEILING
                assert k.label in ("inferred", "unknown")

    def test_testing_marks_a_concept_verified(self, taught):
        assert taught.knowledge.of("compactness").verified

    def test_estimate_carries_its_signals(self, taught):
        k = taught.knowledge.of("compactness")
        assert set(k.signals) >= {"transfer", "support"}

    def test_open_questions_lower_the_estimate(self, taught):
        """The page records an unresolved question, so it counts against."""
        assert taught.knowledge.of("compactness").signals.get("open", 0) < 0


# ---------------------------------------------------------------- similarity
class TestSimilarity:
    def test_reports_which_component_drove_the_match(self, taught):
        near = taught.similarity.nearest("compactness", 3)
        assert near and all(s.why in
                            ("content", "structural", "lexical", "link") for s in near)

    def test_a_prerequisite_scores_structurally_close(self, taught):
        s = taught.similarity.between("compactness", "open and closed set")
        assert s.structural >= 0.5

    def test_latex_noise_is_not_content(self, taught):
        vocab = {t for v in taught.similarity._tfidf.values() for t in v}
        assert not ({"mathbb", "text", "frac", "cdot"} & vocab)


# -------------------------------------------------------------------- engine
class TestEngine:
    def test_starts_empty(self, engine):
        assert engine.graph.nodes == {}
        assert engine.brain.stats()["concepts"] == 0

    def test_concepts_are_created_on_first_mention(self, engine):
        engine.session_start("Compactness", track="Analysis")
        assert engine.graph.get("Compactness") is not None

    def test_prerequisites_are_materialised_immediately(self, engine):
        s = engine.session_start("Compactness", track="Analysis",
                                 prereqs=["Open and closed sets"])
        assert [p["name"] for p in s["prerequisites"]] == ["Open and closed sets"]

    def test_first_time_flag(self, engine):
        assert engine.session_start("Compactness")["first_time"] is True
        engine.session_end("done")
        assert engine.session_start("Compactness")["first_time"] is False

    def test_session_id_is_implicit(self, engine):
        engine.session_start("Compactness")
        out = engine.exam_submit([{"concept": "Compactness", "question": "q",
                                   "verdict": "correct"}])
        assert "error" not in out and out["session_id"]

    def test_submitting_with_no_session_is_an_error_not_a_crash(self, engine):
        assert "error" in engine.exam_submit([{"concept": "X", "verdict": "correct"}])

    def test_unknown_concept_in_an_item_is_created(self, engine):
        engine.session_start("Compactness")
        out = engine.exam_submit([{"concept": "Brand New Idea", "question": "q",
                                   "verdict": "correct"}])
        assert out["concepts_created"] == ["Brand New Idea"]
        assert engine.graph.get("Brand New Idea") is not None

    def test_full_session_writes_the_brain(self, taught):
        page = taught.brain.find("Compactness")
        assert page is not None
        assert "open-cover" in page.section("Understanding")
        assert "closed-and-bounded" in page.section("Where he slips")
        assert page.frontmatter["attempts"] == 2
        assert (taught.brain.root / "Index.md").exists()
        assert len(taught.brain.pages("Sessions")) == 1

    def test_history_accumulates_across_sessions(self, taught):
        before = taught.brain.find("Compactness").section("History").count("\n")
        taught.session_start("Compactness")
        taught.exam_submit([{"concept": "Compactness", "question": "again",
                             "verdict": "correct"}])
        taught.session_end("second pass")
        after = taught.brain.find("Compactness").section("History").count("\n")
        assert after > before, "history is appended, not replaced"

    def test_prose_survives_a_session_that_does_not_restate_it(self, taught):
        taught.session_start("Compactness")
        taught.exam_submit([{"concept": "Compactness", "question": "q",
                             "verdict": "correct"}])
        taught.session_end("no new judgement")
        assert "open-cover" in taught.brain.find("Compactness").section("Understanding")

    def test_recall_returns_what_was_written(self, taught):
        r = taught.brain.recall("Compactness")
        assert r["understanding"] and r["slips"]

    def test_session_start_hands_back_prior_memory(self, taught):
        assert taught.session_start("Compactness")["recall"]["understanding"]

    def test_mastery_persists_across_engine_instances(self, taught):
        again = Engine(taught.cfg)
        assert again.describe("compactness", deep=False)["attempts"] == 2

    def test_editing_a_page_changes_the_graph(self, taught):
        """The markdown is the source of truth, so editing it edits the system."""
        page = taught.brain.find("Compactness")
        taught.brain.write(page.path, page.title, {"prereqs": ["Sequences"]}, {})
        taught._refresh()
        assert taught.graph.prereqs("compactness") == ["sequence"]

    def test_path_to_unknown_goal_reports_rather_than_guesses(self, engine):
        assert "error" in engine.path_to("Nonexistent Concept")

    def test_status_and_report_do_not_crash_when_empty(self, engine):
        assert engine.status()["graph"]["concepts"] == 0
        assert engine.report()["mastery"]["tracked"] == 0


# ----------------------------------------------------------------- questions
class TestQuestionBank:
    def test_asking_banks_the_question(self, engine):
        engine.session_start("Compactness")
        engine.calibration_submit([{"concept": "Compactness", "kind": "definition",
                                    "difficulty": 2, "question": "Define compactness.",
                                    "verdict": "partial"}])
        bank = engine.store.questions_for("compactness")
        assert len(bank) == 1
        assert bank[0].kind == "definition" and bank[0].asked == 1

    def test_reworded_question_is_the_same_question(self, engine):
        engine.session_start("Compactness")
        engine.calibration_submit([{"concept": "Compactness",
                                    "question": "Show that (0,1) is not compact.",
                                    "verdict": "correct"}])
        out = engine.bank_question("Compactness", "show that (0,1) is NOT compact")
        assert out.get("duplicate_of")
        assert len(engine.store.questions_for("compactness")) == 1

    def test_a_just_asked_question_is_not_offered_again(self, engine):
        engine.session_start("Compactness")
        engine.calibration_submit([{"concept": "Compactness", "question": "Define it.",
                                    "verdict": "correct"}])
        sel = engine.questions_for("Compactness", 5)
        assert sel["ask"] == [], "re-asking now would measure recall of the answer"
        assert len(sel["cooling"]) == 1

    def test_a_miss_comes_back_sooner_than_a_hit(self, engine):
        from mentor.questions import Question
        hit = Question("q1", "c", "a", streak=1, last_verdict="correct")
        miss = Question("q2", "c", "b", streak=0, last_verdict="incorrect")
        assert miss.cooldown_days < hit.cooldown_days

    def test_cooldown_lengthens_with_a_streak(self):
        from mentor.questions import Question
        prev = 0
        for streak in range(5):
            q = Question("q", "c", "t", streak=streak, last_verdict="correct")
            assert q.cooldown_days > prev
            prev = q.cooldown_days

    def test_selection_leads_with_what_was_missed(self, engine):
        from datetime import timedelta

        from mentor import questions as qb
        engine.session_start("Compactness")
        engine.calibration_submit([
            {"concept": "Compactness", "question": "Define it.",
             "kind": "definition", "verdict": "correct"},
            {"concept": "Compactness", "question": "Closed bounded non-compact?",
             "kind": "edge", "verdict": "incorrect"}])
        pool = engine.store.questions_for("compactness")
        picked = qb.select(pool, 2, at=qb.now() + timedelta(days=30))
        assert picked[0].last_verdict == "incorrect"

    def test_selection_spreads_across_kinds(self, engine):
        from datetime import timedelta

        from mentor import questions as qb
        engine.session_start("Compactness")
        engine.calibration_submit([
            {"concept": "Compactness", "question": f"q{i}", "kind": k,
             "verdict": "correct"}
            for i, k in enumerate(["definition", "definition", "definition",
                                   "application", "edge"])])
        pool = engine.store.questions_for("compactness")
        picked = qb.select(pool, 3, at=qb.now() + timedelta(days=30))
        assert len({q.kind for q in picked}) >= 3, "should not stack one kind"

    def test_a_question_always_answered_correctly_retires(self, engine):
        engine.session_start("Compactness")
        for _ in range(6):
            engine.calibration_submit([{"concept": "Compactness",
                                        "question": "Define compactness.",
                                        "verdict": "correct"}])
        q = engine.store.questions_for("compactness")[0]
        assert q.retired, "a question nobody gets wrong has stopped discriminating"

    def test_retired_questions_are_never_selected(self, engine):
        from mentor import questions as qb
        engine.session_start("Compactness")
        engine.calibration_submit([{"concept": "Compactness", "question": "Q",
                                    "verdict": "correct"}])
        q = engine.store.questions_for("compactness")[0]
        q.retired = True
        engine.store.save_question(q)
        assert qb.select(engine.store.questions_for("compactness"), 5,
                         allow_cooling=True) == []

    def test_responses_link_back_to_the_bank(self, engine):
        s = engine.session_start("Compactness")
        engine.calibration_submit([{"concept": "Compactness", "question": "Define it.",
                                    "verdict": "correct"}])
        rows = engine.store.responses(s["session_id"])
        assert rows[0]["question_id"] == engine.store.questions_for("compactness")[0].id

    def test_bank_is_rendered_onto_the_concept_page(self, taught):
        page = taught.brain.find("Compactness")
        section = page.section("Questions")
        assert "|" in section and "define it" in section.lower()

    def test_session_start_offers_the_bank(self, taught):
        assert "questions" in taught.session_start("Compactness")

    def test_ids_are_stable_across_whitespace(self):
        from mentor.questions import qid
        assert qid("Define  compactness. ") == qid("define compactness.")


# ------------------------------------------------------------------ mathtext
class TestMathText:
    def test_greek_and_blackboard(self):
        from mentor.mathtext import to_unicode
        assert to_unicode(r"$\alpha \in \mathbb{R}$") == "α ∈ ℝ"

    def test_quantifiers_and_relations(self):
        from mentor.mathtext import to_unicode
        assert to_unicode(r"$\forall \epsilon>0\ \exists \delta$") == "∀ ε>0 ∃ δ"
        assert to_unicode(r"$a \leq b \neq c$") == "a ≤ b ≠ c"

    def test_scripts(self):
        from mentor.mathtext import to_unicode
        assert to_unicode(r"$x_n^2$") == "xₙ²"
        assert to_unicode(r"$\mathbb{R}^n$") == "ℝⁿ"

    def test_unrepresentable_script_stays_readable(self):
        """Unicode has no subscript theta; the fallback must not mangle it."""
        from mentor.mathtext import to_unicode
        assert to_unicode(r"$\nabla_\theta$") == "∇_θ"

    def test_fractions_and_roots(self):
        from mentor.mathtext import to_unicode
        assert to_unicode(r"$\frac{1}{2}$") == "½"
        assert to_unicode(r"$\sqrt{x^2+y^2}$") == "√(x²+y²)"

    def test_operators_followed_by_underscore(self):
        """\b does not fire before "_", which is where these always sit."""
        from mentor.mathtext import to_unicode
        assert to_unicode(r"$\lim_{n \to \infty}$").startswith("lim")
        assert "\\" not in to_unicode(r"$\arg\max_\theta$")

    def test_big_operators_survive_the_size_stripper(self):
        """\big must not eat the front of \bigcup."""
        from mentor.mathtext import to_unicode
        assert to_unicode(r"$\bigcup_\alpha$").startswith("⋃")
        assert to_unicode(r"$\left( x \right)$") == "( x )"

    def test_accents_attach_to_the_symbol_not_the_word(self):
        from mentor.mathtext import to_unicode
        assert to_unicode(r"$\hat{\theta}$") == "θ\u0302"
        assert "theta" not in to_unicode(r"$\hat{\theta}$")

    def test_escaped_braces_are_content(self):
        from mentor.mathtext import to_unicode
        assert to_unicode(r"$\{0\}$") == "{0}"
        assert to_unicode(r"$\{x : x \in S\}$") == "{x : x ∈ S}"

    def test_prose_is_untouched(self):
        from mentor.mathtext import to_unicode
        text = "Plain prose, no maths, costs nothing."
        assert to_unicode(text) == text

    def test_maths_inside_prose_only(self):
        from mentor.mathtext import to_unicode
        assert to_unicode(r"A map $d: X \to \mathbb{R}$ is a metric") \
            == "A map d: X → ℝ is a metric"

    def test_unknown_command_is_left_alone_not_destroyed(self):
        from mentor.mathtext import to_unicode
        out = to_unicode(r"$\notarealcommand{x}$")
        assert out.startswith("\\notarealcommand"), out

    def test_has_latex(self):
        from mentor.mathtext import has_latex
        assert has_latex(r"$x$") and not has_latex("plain text")


# ----------------------------------------------------------------- resources
class TestLibrary:
    def test_resource_is_a_page_in_the_vault(self, engine):
        engine.add_resource("Rudin", kind="book", author="Walter Rudin",
                            where="Books/Rudin.pdf", covers=["Compactness"])
        names = [r["name"] for r in engine.resources()]
        assert names == ["Rudin"]
        assert (engine.brain.root / "Resources" / "Rudin.md").exists()

    def test_resource_survives_a_reload(self, engine):
        engine.add_resource("Munkres", kind="book", where="shelf")
        again = Engine(engine.cfg)
        assert [r["name"] for r in again.resources()] == ["Munkres"]

    def test_material_is_assigned_to_a_concept(self, engine):
        engine.session_start("Compactness", track="Analysis")
        engine.assign_material("Compactness", ["[[Rudin]] 2.31-2.37"])
        assert engine.material_for("Compactness") == ["[[Rudin]] 2.31-2.37"]

    def test_material_lands_on_the_page_and_in_frontmatter(self, engine):
        engine.session_start("Compactness", track="Analysis")
        engine.assign_material("Compactness", ["[[Rudin]] 2.31-2.37"])
        page = engine.brain.find("Compactness")
        assert "Rudin" in page.section("Material")
        assert page.frontmatter["material"] == ["[[Rudin]] 2.31-2.37"]

    def test_material_survives_a_session_that_does_not_mention_it(self, engine):
        engine.session_start("Compactness", track="Analysis")
        engine.assign_material("Compactness", ["[[Rudin]] 2.31-2.37"])
        engine.exam_submit([{"concept": "Compactness", "question": "q",
                             "verdict": "correct"}])
        engine.session_end("done")
        assert engine.material_for("Compactness") == ["[[Rudin]] 2.31-2.37"]

    def test_assign_can_append_instead_of_replacing(self, engine):
        engine.session_start("Compactness", track="Analysis")
        engine.assign_material("Compactness", ["[[Rudin]] 2.31"])
        engine.assign_material("Compactness", ["[[Munkres]] 26"], replace=False)
        assert len(engine.material_for("Compactness")) == 2

    def test_unassigned_concept_says_so_rather_than_being_blank(self, engine):
        engine.session_start("Compactness", track="Analysis")
        page = engine.brain.find("Compactness")
        assert "Resources" in page.section("Material")

    def test_session_start_hands_over_the_library(self, engine):
        engine.add_resource("Rudin", where="Books/Rudin.pdf")
        s = engine.session_start("Compactness")
        assert [r["name"] for r in s["library"]] == ["Rudin"]
        assert "material" in s


# ------------------------------------------------------------------ obsidian
class TestObsidian:
    def test_graph_view_is_configured(self, tmp_path):
        import json
        b = Brain(tmp_path / "brain")
        cfg = json.loads((b.root / ".obsidian" / "graph.json").read_text(encoding="utf-8"))
        assert cfg["colorGroups"], "state should be visible in Obsidian's graph"
        assert cfg["showArrow"] is True, "prerequisite direction carries meaning"

    def test_existing_graph_config_is_not_clobbered(self, tmp_path):
        b = Brain(tmp_path / "brain")
        g = b.root / ".obsidian" / "graph.json"
        g.write_text('{"mine": true}', encoding="utf-8")
        Brain(tmp_path / "brain")
        assert g.read_text(encoding="utf-8") == '{"mine": true}'


# --------------------------------------------------------- one at a time
class TestAskLoop:
    def test_ask_next_returns_a_single_question(self, engine):
        engine.session_start("Compactness")
        engine.answer("correct", question="Define it.", kind="definition")
        out = engine.ask_next()
        assert "question" in out and not isinstance(out.get("question"), list)

    def test_answer_records_one_and_offers_the_next(self, engine):
        engine.session_start("Compactness")
        out = engine.answer("partial", question="Define compactness.",
                            response="closed and bounded", kind="definition")
        assert out["recorded"]["verdict"] == "partial"
        assert "next" in out

    def test_a_question_is_not_offered_twice_in_one_phase(self, engine):
        engine.session_start("Compactness")
        engine.answer("correct", question="Q one", kind="definition")
        engine.answer("correct", question="Q two", kind="application")
        nxt = engine.ask_next()
        asked = {"Q one", "Q two"}
        got = (nxt.get("question") or {}).get("text")
        assert got not in asked

    def test_answering_with_no_session_is_an_error(self, engine):
        assert "error" in engine.answer("correct", question="q")

    def test_exam_phase_is_weighted_more_than_calibration(self, engine):
        engine.session_start("A")
        cal = engine.answer("correct", question="q1", phase="calibration")
        engine.session_end("x")
        engine.session_start("B")
        ex = engine.answer("correct", question="q2", phase="exam")
        assert ex["recorded"]["tested_after"] > cal["recorded"]["tested_after"]


# ---------------------------------------------------------------- reviews
class TestReview:
    def test_review_moves_mastery(self, engine):
        engine.session_start("Dynamic programming", track="Algorithms")
        out = engine.submit_review(
            "Dynamic programming", language="Python", lines=40,
            ratings={"correctness": 4, "complexity": 2, "clarity": 3,
                     "idiom": 4, "robustness": 2},
            issues=[{"severity": "major", "where": "solve()",
                     "what": "recomputes overlapping subproblems"}],
            summary="Correct but naive.")
        assert out["overall"] == 3.0 and out["verdict"] == "partial"
        assert out["tested_after"] > out["tested_before"]

    def test_weakest_dimension_is_identified(self, engine):
        engine.session_start("X")
        out = engine.submit_review("X", ratings={
            "correctness": 5, "complexity": 1, "clarity": 4,
            "idiom": 4, "robustness": 4})
        assert out["weakest"] == "complexity"

    def test_rating_scale_is_clamped_and_filtered(self, engine):
        engine.session_start("X")
        out = engine.submit_review("X", ratings={
            "correctness": 99, "clarity": -3, "vibes": 5})
        assert out["ratings"] == {"correctness": 5, "clarity": 1}

    def test_a_fix_field_is_discarded(self, engine):
        """The reviewer rates and names; it does not repair."""
        engine.session_start("X")
        out = engine.submit_review("X", ratings={"correctness": 3}, issues=[
            {"severity": "major", "what": "no memoisation",
             "fix": "wrap it in functools.lru_cache"}])
        assert "fix" not in out["issues"][0]

    def test_issues_sort_by_severity(self, engine):
        engine.session_start("X")
        out = engine.submit_review("X", ratings={"correctness": 3}, issues=[
            {"severity": "note", "what": "c"},
            {"severity": "blocker", "what": "a"},
            {"severity": "minor", "what": "b"}])
        assert [i["severity"] for i in out["issues"]] == ["blocker", "minor", "note"]

    def test_review_lands_on_the_concept_page(self, engine):
        engine.session_start("X")
        engine.submit_review("X", language="Rust", ratings={"correctness": 4},
                             summary="Reads well.")
        assert "Rust" in engine.brain.find("X").section("Reviews")

    def test_empty_ratings_are_refused(self, engine):
        engine.session_start("X")
        assert "error" in engine.submit_review("X", ratings={"nonsense": 3})
