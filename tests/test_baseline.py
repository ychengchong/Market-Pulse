"""Regression checks for section boundaries and evaluation integrity."""
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from evals.run import evaluate, load_suite, score_prediction
from scripts.lock_dependencies import render_lock
from scripts.environment import verify_environment
from src.summarizer import create_summary, extract_mda_section, find_primary_8k_item

ROOT = Path(__file__).resolve().parents[1]
HEADING = "Management's Discussion and Analysis of Financial Condition and Results of Operations"
EVIDENCE = "Revenue increased 12% to $120 million during the quarter as customer demand increased."


class SectionTests(unittest.TestCase):
    def test_8k_toc_cannot_hide_real_disclosure(self):
        text = ("TABLE OF CONTENTS\nItem 5.02 Leadership\n3\nSIGNATURES\n4\n"
                "Item 5.02 Leadership\n"
                "Example Corporation appointed Morgan Lee as chief financial officer effective November 1, 2026.\n"
                "SIGNATURES\nExcluded signature text.")
        result = create_summary(text, form="8-K")
        self.assertEqual(result["event_type"], "leadership")
        self.assertIn("appointed Morgan Lee", result["summary"])
        self.assertNotIn("Excluded signature", result["summary"])

    def test_8k_preserves_first_body_item_despite_longer_later_event(self):
        lines = ["Item 2.02 Results", "3", "Item 5.02 Leadership", "4", "SIGNATURES", "5",
                 "Item 2.02 Results", "The company announced its quarterly results.",
                 "Item 5.02 Leadership", "A later leadership disclosure contains much more text. " * 10]
        index, item = find_primary_8k_item(lines)
        self.assertEqual((index, item), (6, "2.02"))

    def test_8k_wrapped_toc_title_does_not_replace_longer_body(self):
        lines = ["Item 8.01", "OTHER EVENTS.", "3", "Item 9.01 Exhibits", "4",
                 "Item 8.01", "The company completed a financing transaction to support expansion of its operations.",
                 "Item 9.01 Exhibits"]
        self.assertEqual(find_primary_8k_item(lines), (5, "8.01"))

    def test_8k_without_substantive_body_retains_fallback(self):
        result = create_summary("Item 2.02 Results\n3\nItem 9.01 Exhibits\n4", form="8-K")
        self.assertEqual(result["event_type"], "earnings/results")
        self.assertTrue(result["summary"].startswith("No suitable"))

    def test_cross_reference_is_not_a_section_heading(self):
        text = (f"Item 2. {HEADING}\n{EVIDENCE}\n"
                f"Refer to Item 7, {HEADING} in our previous annual report.\n"
                "Item 3. Quantitative and Qualitative Disclosures About Market Risk\n"
                "Revenue increased 99% to $999 million during an unrelated scenario.")
        section = extract_mda_section(text)
        self.assertIn(EVIDENCE, section)
        self.assertNotIn("$999 million", section)
        self.assertIn(EVIDENCE, create_summary(text, form="10-Q")["summary"])

    def test_toc_is_not_selected_over_body(self):
        text = (f"Item 2.\n{HEADING}\n25\nItem 3.\nMarket Risk\n"
                f"Item 2.\n{HEADING}\n{EVIDENCE}\nItem 3.\nMarket Risk")
        self.assertEqual(extract_mda_section(text), EVIDENCE)

    def test_split_uppercase_heading_and_crlf(self):
        title = HEADING.upper().replace("ANALYSIS OF", "ANALYSIS\r\nOF")
        text = f"ITEM 2. {title}\r\n{EVIDENCE}\r\nITEM 3. Market Risk\r\nExcluded."
        self.assertEqual(extract_mda_section(text), EVIDENCE)

    def test_curly_apostrophe_and_nonbreaking_spaces(self):
        title = HEADING.replace("'", "\u2019").replace(" ", "\u00a0")
        text = f"Item 2. {title}\n{EVIDENCE}\nPart II. Other Information\nExcluded."
        self.assertEqual(extract_mda_section(text), EVIDENCE)

    def test_missing_heading_retains_existing_whole_text_fallback(self):
        self.assertEqual(extract_mda_section(EVIDENCE), EVIDENCE)

    def test_market_risk_sentence_never_enters_summary(self):
        case = next(case for case, text in load_suite(ROOT / "evals/cases.json")[1] if case["id"] == "10q-boundary")
        text = (ROOT / "evals" / case["fixture"]).read_text(encoding="utf-8")
        summary = create_summary(text, form="10-Q")["summary"]
        self.assertNotIn("$999 million", summary)


class EvaluationTests(unittest.TestCase):
    def test_environment_mismatch_is_rejected(self):
        with patch("scripts.environment.importlib.metadata.version", return_value="0.0.0"):
            with self.assertRaisesRegex(ValueError, "does not match lock"):
                verify_environment(ROOT)

    def test_all_frozen_development_cases_are_retained(self):
        report = evaluate(ROOT / "evals/cases.json")
        self.assertEqual(report["total"], 15)
        self.assertEqual(report["passed"], 15)
        self.assertEqual(report["errors"], 0)
        self.assertEqual(report["fallback_count"], 2)

    def test_failed_prediction_stays_in_denominator(self):
        def failing_predictor(*args, **kwargs):
            raise ValueError("synthetic provider failure")
        report = evaluate(ROOT / "evals/cases.json", predictor=failing_predictor)
        self.assertEqual((report["total"], report["passed"], report["errors"]), (15, 0, 15))
        self.assertEqual(len(report["results"]), 15)

    def test_scorer_detects_missing_and_forbidden_evidence(self):
        reference = dict(event_type="earnings/results", expect_fallback=False,
                         required_evidence=["$120 million"], forbidden_evidence=["$999 million"])
        result = score_prediction(dict(event_type="earnings/results", summary="Revenue was $999 million."), reference)
        self.assertFalse(result["passed"])
        self.assertFalse(result["checks"]["required_evidence_present"])
        self.assertFalse(result["checks"]["forbidden_evidence_absent"])

    def test_changed_fixture_is_detected(self):
        manifest = json.loads((ROOT / "evals/cases.json").read_text(encoding="utf-8"))
        manifest["cases"][0]["input_sha256"] = "0" * 64
        with patch("evals.run.json.loads", return_value=manifest):
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                load_suite(ROOT / "evals/cases.json")

    def test_reference_must_be_supported_by_input(self):
        manifest = json.loads((ROOT / "evals/cases.json").read_text(encoding="utf-8"))
        manifest["cases"][0]["reference"]["required_evidence"] = ["Invented reference fact"]
        with patch("evals.run.json.loads", return_value=manifest):
            with self.assertRaisesRegex(ValueError, "absent from input"):
                load_suite(ROOT / "evals/cases.json")


class LockTests(unittest.TestCase):
    def setUp(self):
        self.requirements = b"example==1.0\n"
        self.report = dict(environment=dict(python_full_version="3.14.5", sys_platform="win32", platform_machine="AMD64"),
                           install=[dict(metadata=dict(name="example", version="1.0"),
                                         download_info=dict(url="https://files.example.test/example.whl",
                                                            archive_info=dict(hashes=dict(sha256="a" * 64))))])

    def test_lock_retains_version_and_artifact_hash(self):
        lock = render_lock(self.report, self.requirements)
        self.assertIn("example==1.0 --hash=sha256:" + "a" * 64, lock)

    def test_lock_rejects_missing_direct_dependency(self):
        with self.assertRaisesRegex(ValueError, "missing from report"):
            render_lock(self.report, b"other==1.0\n")

    def test_lock_rejects_unsupported_target(self):
        self.report["environment"]["sys_platform"] = "linux"
        with self.assertRaisesRegex(ValueError, "Windows AMD64"):
            render_lock(self.report, self.requirements)

    def test_lock_rejects_source_distributions(self):
        self.report["install"][0]["download_info"]["url"] = "https://files.example.test/example.tar.gz"
        with self.assertRaisesRegex(ValueError, "wheels"):
            render_lock(self.report, self.requirements)


if __name__ == "__main__":
    unittest.main()
