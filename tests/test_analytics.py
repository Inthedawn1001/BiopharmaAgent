import unittest

from biopharma_agent.analytics.report import DeterministicTextAnalytics
from biopharma_agent.analytics.brief import IntelligenceBriefBuilder
from biopharma_agent.analytics.risk import RuleBasedRiskScorer
from biopharma_agent.analytics.sentiment import KeywordSentimentAnalyzer
from biopharma_agent.analytics.timeseries import TimeSeriesAnalyzer
from biopharma_agent.analytics.topic import KeywordTopicAnalyzer


class AnalyticsTest(unittest.TestCase):
    def test_topic_terms(self):
        terms = KeywordTopicAnalyzer().top_terms("PD-1 PD-1 financing financing clinical")
        term_counts = dict(terms)

        self.assertEqual(term_counts["pd-1"], 2)
        self.assertEqual(term_counts["financing"], 2)

    def test_topic_terms_ignore_common_function_words(self):
        terms = KeywordTopicAnalyzer().top_terms("FDA approval of the drug in clinical development")
        term_names = {term for term, _ in terms}

        self.assertIn("approval", term_names)
        self.assertNotIn("of", term_names)
        self.assertNotIn("in", term_names)

    def test_sentiment(self):
        result = KeywordSentimentAnalyzer().analyze("The company gained approval and growth, but risk remains")

        self.assertEqual(result["label"], "positive")

    def test_risk(self):
        result = RuleBasedRiskScorer().score("The project had clinical failure and a clinical hold")

        self.assertEqual(result["severity"], "high")

    def test_timeseries(self):
        result = TimeSeriesAnalyzer(outlier_zscore=1.5).summarize([1, 2, 3, 100])

        self.assertEqual(result["trend"], "up")
        self.assertTrue(result["outliers"])

    def test_combined_report(self):
        report = DeterministicTextAnalytics().analyze("TestBio financing growth")

        self.assertIn("top_terms", report)
        self.assertIn("sentiment", report)
        self.assertIn("risk", report)

    def test_intelligence_brief_summarizes_records(self):
        records = [
            _pipeline_record(
                title="FDA clinical hold",
                source="fda_press_releases",
                event_type="regulatory",
                risk="high",
                summary="FDA placed a clinical hold on a trial.",
            ),
            _pipeline_record(
                title="Biotech financing",
                source="biopharma_dive_news",
                event_type="financing",
                risk="low",
                summary="Company raised financing for a PD-1 program.",
            ),
        ]

        brief = IntelligenceBriefBuilder().build(records)

        self.assertEqual(brief["document_count"], 2)
        self.assertIn("Biopharma Intelligence Brief", brief["markdown"])
        self.assertEqual(brief["risk_counts"][0]["name"], "high")
        self.assertTrue(brief["risk_watchlist"])


def _pipeline_record(title, source, event_type, risk, summary):
    return {
        "document": {
            "raw": {
                "document_id": title.lower().replace(" ", "-"),
                "title": title,
                "url": f"https://example.test/{title}",
                "source": {"name": source, "kind": "test"},
            },
            "text": f"{title}. {summary}",
            "checksum": title,
        },
        "provider": "test",
        "model": "test-model",
        "created_at": "2026-05-01T00:00:00+00:00",
        "insight": {
            "summary": summary,
            "events": [{"event_type": event_type, "title": event_type.upper()}],
            "risk_signals": [{"severity": risk, "risk_type": "test"}],
            "needs_human_review": risk == "high",
        },
    }


if __name__ == "__main__":
    unittest.main()
