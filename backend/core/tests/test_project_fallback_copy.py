"""Pure presentation checks; no database, provider or new score calculation."""

from copy import deepcopy
from datetime import date
from types import SimpleNamespace
from unittest import TestCase

from core.project_insights import fallback_markdown


class ProjectFallbackCopyTests(TestCase):
    def report(self, count=12):
        sources = [
            {
                "id": "project-reference",
                "type": "project",
                "title": "API dönüşümü",
                "status": "IN_PROGRESS",
                "summary": "Amaç",
            },
            {
                "id": "metrics-reference",
                "type": "project_metrics",
                "title": "Hesaplanan değerler",
                "status": "DETERMINISTIC",
                "summary": '{"overall": null}',
            },
            {
                "id": "team-reference",
                "type": "project_team_plan",
                "title": "Uygulama Güvenliği",
                "status": "PLAN",
                "summary": "Ekip ağırlığı 3; ilerleme 62.5; kapsam {'quality_rated': 0}",
            },
        ]
        sources.extend(
            {
                "id": f"delivery-reference-{i}",
                "type": "project_deliverable",
                "version": 2,
                "title": f"Güvenlik kontrolü {i}",
                "status": "%50",
                "summary": "Ekip: OS; ağırlık: 1; kanıt: Onaylı test kaydı; kalite1–5: None; termin: None",
            }
            for i in range(count)
        )
        return SimpleNamespace(
            project=SimpleNamespace(title="API dönüşümü"),
            kind="WEEKLY",
            period_start=date(2026, 11, 16),
            period_end=date(2026, 11, 22),
            sources=sources,
            computed_values={
                "delivery": 62.5,
                "quality": None,
                "stakeholder": 75,
                "overall": None,
                "coverage": {
                    "teams": 4,
                    "deliverables": 8,
                    "quality_rated": 0,
                    "survey_invited": 5,
                    "survey_responded": 2,
                    "response_rate": 40,
                },
            },
        )

    def test_executive_copy_is_turkish_compact_and_preserves_numbers_and_sources(self):
        report = self.report()
        original_scores = deepcopy(report.computed_values)
        original_sources = deepcopy(report.sources)
        output = fallback_markdown(report)
        self.assertIn("Haftalık yönetim özeti", output)
        self.assertIn("Devam ediyor", output)
        self.assertIn("16.11.2026 – 22.11.2026", output)
        self.assertIn("4 ekip ve 8 teslimat", output)
        self.assertIn("2/5 yanıt (%40)", output)
        self.assertIn("Uygulama Güvenliği:** %62,5", output)
        self.assertIn("Proje başarı endeksi: Veri yok", output)
        self.assertIn("RULE_BASED", output)
        self.assertIn("kalan 4 kaydın", output)
        self.assertEqual(output.count("- K"), 8)
        self.assertNotIn("IN_PROGRESS", output)
        self.assertNotIn("DETERMINISTIC", output)
        self.assertNotIn("None", output)
        self.assertNotIn("quality_rated", output)
        self.assertNotIn('{"overall"', output)
        self.assertNotIn("delivery-reference-8", output)
        self.assertEqual(report.computed_values, original_scores)
        self.assertEqual(report.sources, original_sources)

    def test_absent_data_is_described_without_inventing_progress_or_satisfaction(self):
        report = self.report(count=0)
        report.computed_values = {
            "delivery": None,
            "quality": None,
            "stakeholder": None,
            "overall": None,
            "coverage": {
                "teams": 1,
                "deliverables": 0,
                "quality_rated": 0,
                "unplanned_teams": 1,
                "survey_invited": 0,
                "survey_responded": 0,
                "response_rate": None,
            },
        }
        report.sources = report.sources[:2]
        report.kind = "CLOSURE"
        output = fallback_markdown(report)
        self.assertIn("Kapanış değerlendirmesi", output)
        self.assertIn("1 katılımcı ekip için teslimat planı eksik", output)
        self.assertIn("yanıt oranı hesaplanamıyor", output)
        self.assertIn("Paydaş değerlendirmesi: Veri yok", output)
        self.assertNotIn("%0", output)
        self.assertNotIn("None", output)
