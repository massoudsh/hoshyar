import json
from pathlib import Path
import unittest

from hoshyar.intent import extract_intent


EVALS = Path(__file__).resolve().parent.parent / "outputs" / "evals" / "intent-golden.json"


class IntentRegressionTests(unittest.TestCase):
    """Scores the extractor against a checked-in golden set so a change cannot silently lower accuracy."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.eval_set = json.loads(EVALS.read_text(encoding="utf-8"))

    def score(self, field: str) -> tuple[int, int, list[str]]:
        hits = total = 0
        misses = []
        for case in self.eval_set["cases"]:
            if field not in case["expected"]:
                continue
            total += 1
            expected = case["expected"][field]
            actual = getattr(extract_intent(case["text"]), field)
            if actual == expected:
                hits += 1
            else:
                misses.append(f"{case['text']!r}: {field} expected {expected!r}, got {actual!r}")
        return hits, total, misses

    def test_purpose_accuracy_meets_threshold(self) -> None:
        hits, total, misses = self.score("purpose")
        accuracy = hits / total
        self.assertGreaterEqual(
            accuracy, self.eval_set["thresholds"]["purpose_accuracy"],
            f"purpose accuracy {accuracy:.2%} ({hits}/{total}); misses:\n" + "\n".join(misses),
        )

    def test_field_accuracy_meets_threshold(self) -> None:
        hits = total = 0
        misses = []
        for field in ("price", "deposit", "rent", "neighborhood", "urgency", "confidence"):
            field_hits, field_total, field_misses = self.score(field)
            hits += field_hits
            total += field_total
            misses += field_misses
        accuracy = hits / total
        self.assertGreaterEqual(
            accuracy, self.eval_set["thresholds"]["field_accuracy"],
            f"field accuracy {accuracy:.2%} ({hits}/{total}); misses:\n" + "\n".join(misses),
        )

    def test_golden_set_covers_every_intent_field(self) -> None:
        covered = {field for case in self.eval_set["cases"] for field in case["expected"]}
        self.assertEqual(covered, {"purpose", "price", "deposit", "rent", "neighborhood", "urgency", "confidence"})

    def test_persian_and_arabic_digits_agree(self) -> None:
        persian = extract_intent("خرید در پونک تا ۸ میلیارد")
        arabic = extract_intent("خرید در پونک تا ٨ ميليارد")
        self.assertEqual(persian.price, arabic.price)
        self.assertEqual(persian.purpose, arabic.purpose)


if __name__ == "__main__":
    unittest.main()
