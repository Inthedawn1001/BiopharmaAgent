import unittest

from biopharma_agent.analytics.report import DeterministicTextAnalytics
from biopharma_agent.analytics.risk import RuleBasedRiskScorer
from biopharma_agent.analytics.sentiment import KeywordSentimentAnalyzer
from biopharma_agent.analytics.timeseries import TimeSeriesAnalyzer
from biopharma_agent.analytics.topic import KeywordTopicAnalyzer


class AnalyticsTest(unittest.TestCase):
    def test_topic_terms(self):
        terms = KeywordTopicAnalyzer().top_terms("PD-1 PD-1 融资 融资 临床")
        term_counts = dict(terms)

        self.assertEqual(term_counts["pd-1"], 2)
        self.assertEqual(term_counts["融资"], 2)

    def test_sentiment(self):
        result = KeywordSentimentAnalyzer().analyze("公司获批并增长，但存在风险")

        self.assertEqual(result["label"], "positive")

    def test_risk(self):
        result = RuleBasedRiskScorer().score("项目临床失败并被暂停")

        self.assertEqual(result["severity"], "high")

    def test_timeseries(self):
        result = TimeSeriesAnalyzer(outlier_zscore=1.5).summarize([1, 2, 3, 100])

        self.assertEqual(result["trend"], "up")
        self.assertTrue(result["outliers"])

    def test_combined_report(self):
        report = DeterministicTextAnalytics().analyze("测试生物融资增长")

        self.assertIn("top_terms", report)
        self.assertIn("sentiment", report)
        self.assertIn("risk", report)


if __name__ == "__main__":
    unittest.main()
