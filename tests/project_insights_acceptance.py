#!/usr/bin/env python3
"""onecs yeni özellikleri: yalnız yerel sentetik ortamda gerçek HTTP kabulü.

Haricî AI/LDAP ayarına dokunmaz. Raporlar açık RULE_BASED modunda istenir.
Bu dosyayı çalıştırmak root'un DB/HTTP test koordinasyonu GO kararını gerektirir.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
import unittest
import urllib.parse
import uuid
from pathlib import Path

from api_acceptance import ApiClient, EvidenceResult, person, records

CONFIG = {}


class ProjectInsightsAcceptance(unittest.TestCase):
    """Independent cookie jars; no ORM, God Mode, live-provider call or secret read."""

    @classmethod
    def setUpClass(cls):
        cls.run_key = "QA-INSIGHTS-" + uuid.uuid4().hex[:10]
        cls.clients = {}
        cls.users = {}
        for role in (
            "director",
            "unithead",
            "teammanager",
            "employee",
            "pm",
            "pm_head",
            "admin",
            "iamhead",
            "iamemployee",
            "fulladmin",
        ):
            client = ApiClient(CONFIG["base_url"])
            if client.login(role, CONFIG["password"]).status != 200:
                raise AssertionError(f"Sentetik rol girişi başarısız: {role}")
            response = client.request("GET", "auth/me/")
            if response.status != 200 or not isinstance(person(response.data), dict):
                raise AssertionError(f"Rol kimliği okunamadı: {role}")
            cls.clients[role] = client
            cls.users[role] = person(response.data)

    def api(self, role, method, path, payload=None, *, expected=(200,), **kwargs):
        response = self.clients[role].request(method, path, payload, **kwargs)
        # Do not put arbitrary response bodies (possibly real profile metadata)
        # in assertion messages or evidence files.
        self.assertIn(
            response.status, expected, f"{role} {method} {path}: HTTP {response.status}"
        )
        self.assertNotIn("Traceback (most recent call last)", response.text)
        return response

    def unique(self, label):
        return f"{self.run_key} {label} {uuid.uuid4().hex[:5]}"

    def uid(self, role):
        return self.users[role]["id"]

    def oid(self, role):
        return self.users[role]["primary_org_id"]

    def project(self, *, approve=True):
        obj = self.api(
            "employee",
            "POST",
            "projects/",
            {
                "title": self.unique("proje"),
                "description": "Sentetik ekip içgörü ve kaynak gizliliği doğrulaması.",
                "expected_outcome": "İnsan onaylı, kaynaklı yönetişim özeti",
                "pm_id": self.uid("pm"),
            },
            expected=(201,),
        ).data
        if approve:
            obj = self.api(
                "employee",
                "POST",
                f"projects/{obj['id']}/submit/",
                {
                    "version": obj["version"],
                },
            ).data
            obj = self.api(
                "pm",
                "POST",
                f"projects/{obj['id']}/review/",
                {
                    "version": obj["version"],
                    "decision": "APPROVE",
                    "note": "Sentetik QA onayı",
                },
            ).data
        return obj

    def fresh_project(self, project):
        return self.api("pm", "GET", f"projects/{project['id']}/").data

    def member(self, project, role="iamemployee", manager="iamhead"):
        current = self.fresh_project(project)
        request = self.api(
            "pm",
            "POST",
            f"projects/{project['id']}/members/",
            {
                "version": current["version"],
                "user_id": self.uid(role),
                "summary": "Sentetik kaynak kabulü",
            },
            expected=(201,),
        ).data
        self.api(
            manager,
            "POST",
            f"participation-requests/{request['id']}/decide/",
            {
                "version": request["version"],
                "decision": "ACCEPT",
                "note": "Kaynak ayrıldı",
            },
        )
        return self.fresh_project(project)

    def insights(self, project, role="pm"):
        return self.api(role, "GET", f"projects/{project['id']}/insights/").data

    def plan(self, project, role="employee", weight=1, actor="pm"):
        summary = self.api(
            actor,
            "POST",
            f"projects/{project['id']}/team-plans/",
            {
                "org_id": self.oid(role),
                "weight": weight,
            },
            expected=(201,),
        ).data
        return next(row for row in summary["teams"] if row["org_id"] == self.oid(role))

    def delivery(self, project, role="employee", actor="pm", **overrides):
        payload = {
            "title": self.unique("teslimat"),
            "org_id": self.oid(role),
            "kind": "DELIVERABLE",
            "weight": 1,
            "progress": 0,
            "evidence": "Sentetik tamamlanma kanıtı; gerçek kurum bilgisi içermez.",
        }
        payload.update(overrides)
        return self.api(
            actor,
            "POST",
            f"projects/{project['id']}/deliverables/",
            payload,
            expected=(201,),
        ).data

    def survey(self, project, *, invitees=None):
        return self.api(
            "pm",
            "POST",
            f"projects/{project['id']}/surveys/",
            {
                "title": self.unique("paydaş anketi"),
                "questions": ["Çıktı ihtiyacı karşıladı mı?"],
                "invitee_ids": invitees or [self.uid("iamemployee")],
                "closes_at": (
                    dt.datetime.now(dt.UTC) + dt.timedelta(days=1)
                ).isoformat(),
            },
            expected=(201,),
        ).data

    def report(self, project, kind="DAILY", **overrides):
        today = dt.date.today()
        payload = {
            "kind": kind,
            "period_start": today.isoformat(),
            "period_end": today.isoformat(),
            "generation_mode": "RULE_BASED",
        }
        payload.update(overrides)
        result = self.api(
            "pm",
            "POST",
            f"projects/{project['id']}/insight-reports/",
            payload,
            expected=(202,),
        ).data
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            result = self.api(
                "pm", "GET", f"projects/{project['id']}/insight-reports/{result['id']}/"
            ).data
            if result["status"] == "READY":
                self.assertEqual(result["mode"], "RULE_BASED")
                self.assertTrue(result["markdown"].strip())
                return result
            if result["status"] == "FAILED" or (result.get("job") or {}).get(
                "status"
            ) in ("FAILED", "BLOCKED", "CANCELLED"):
                self.fail("Kurallı proje raporu worker tarafından tamamlanamadı")
            time.sleep(0.2)
        self.fail("Kurallı proje raporu 45 saniyede READY olmadı; worker kanıtı yok")

    def report_path(self, project, report):
        return f"projects/{project['id']}/insight-reports/{report['id']}/"

    def grant(self, project, permissions, role="iamhead"):
        current = self.fresh_project(project)
        return self.api(
            "pm",
            "POST",
            f"projects/{project['id']}/authorities/",
            {
                "version": current["version"],
                "user_id": self.uid(role),
                "permissions": permissions,
                "expires_at": (
                    dt.datetime.now(dt.UTC) + dt.timedelta(days=1)
                ).isoformat(),
                "reason": "Sentetik sınırlı görev devri",
            },
            expected=(201,),
        ).data

    def test_01_new_endpoints_require_login_and_csrf(self):
        """PI01: yeni kaynaklar anonim ve CSRF'siz yazma ile açılmaz."""
        project = self.project()
        anonymous = ApiClient(CONFIG["base_url"])
        for path in (
            f"projects/{project['id']}/insights/",
            f"people/{self.uid('employee')}/workload/",
            f"people/{self.uid('employee')}/assignable-scope/",
        ):
            self.assertIn(anonymous.request("GET", path).status, (401, 403))
        self.api(
            "pm",
            "POST",
            f"projects/{project['id']}/team-plans/",
            {
                "org_id": self.oid("employee"),
                "weight": 60,
            },
            csrf=False,
            expected=(403,),
        )
        self.assertEqual(self.insights(project)["teams"], [])

    def test_02_two_level_weights_are_mathematically_correct(self):
        """PI02: teslimat ve ekip ağırlıkları iki ayrı paydada hesaplanır."""
        project = self.member(self.project())
        self.plan(project, weight=60)
        self.plan(project, "iamemployee", weight=40)
        self.delivery(project, progress=0, quality_rating=5)
        self.delivery(project, progress=100, quality_rating=3, kind="MILESTONE")
        self.delivery(project, "iamemployee", progress=100, quality_rating=1)
        summary = self.insights(project)
        self.assertEqual(summary["scores"]["delivery"], 70)
        self.assertEqual(summary["scores"]["quality"], 45)
        self.assertIsNone(summary["scores"]["stakeholder"])
        self.assertIsNone(summary["scores"]["overall"])
        self.assertEqual(summary["scores"]["coverage"]["deliverables"], 3)
        self.assertEqual(
            {row["org_id"]: row["progress"] for row in summary["teams"]},
            {
                self.oid("employee"): 50,
                self.oid("iamemployee"): 100,
            },
        )
        survey = self.survey(project)
        self.api(
            "iamemployee",
            "POST",
            f"projects/{project['id']}/surveys/{survey['id']}/respond/",
            {
                "version": survey["version"],
                "answers": {survey["questions"][0]["id"]: 5},
            },
        )
        final = self.insights(project)["scores"]
        self.assertEqual(final["stakeholder"], 100)
        self.assertEqual(final["overall"], 68.5)
        self.assertEqual(
            self.fresh_project(project)["progress"],
            project["progress"],
            "Beyan yüzdesi başarı endeksiyle sessizce değiştirilmemeli",
        )

    def test_03_missing_evidence_is_unknown_not_success(self):
        """PI02/CQ02: boş plan ve eksik kalite sıfır/100 uydurmaz."""
        project = self.project()
        blank = self.insights(project)["scores"]
        for field in ("delivery", "quality", "stakeholder", "overall"):
            self.assertIsNone(blank[field])
        self.plan(project)
        self.assertIsNone(self.insights(project)["scores"]["delivery"])
        self.delivery(project, progress=100)
        result = self.insights(project)["scores"]
        self.assertEqual(result["delivery"], 100)
        self.assertIsNone(result["quality"])
        self.assertIsNone(result["overall"])
        self.assertEqual(result["coverage"]["quality_rated"], 0)

    def test_04_invalid_plan_and_deliverable_leave_no_partial_record(self):
        """PI01/PI02: bilinmeyen ekip/geçersiz sayı/kanıtsız ilerleme atomik reddedilir."""
        project = self.project()
        path = f"projects/{project['id']}/team-plans/"
        for weight in (0, -1, 101, 1.5, True, None):
            with self.subTest(weight=weight):
                self.api(
                    "pm",
                    "POST",
                    path,
                    {"org_id": self.oid("employee"), "weight": weight},
                    expected=(400,),
                )
        self.api(
            "pm",
            "POST",
            path,
            {"org_id": self.oid("iamemployee"), "weight": 10},
            expected=(400,),
        )
        for changes in (
            {"progress": 101},
            {"progress": 1, "evidence": ""},
            {"quality_rating": 0},
            {"weight": 0},
            {"kind": "UNKNOWN"},
        ):
            payload = {
                "title": self.unique("geçersiz teslimat"),
                "org_id": self.oid("employee"),
                "evidence": "Sentetik kanıt",
            }
            payload.update(changes)
            self.api(
                "pm",
                "POST",
                f"projects/{project['id']}/deliverables/",
                payload,
                expected=(400,),
            )
        self.assertEqual(self.insights(project)["teams"], [])

    def test_05_org_management_does_not_grant_project_mutation(self):
        """PI01: personel UH'si, direktör ve teknik admin PM hakkı devralmaz."""
        project = self.member(self.project())
        for role in (
            "employee",
            "unithead",
            "teammanager",
            "iamhead",
            "director",
            "admin",
        ):
            with self.subTest(role=role):
                self.api(
                    role,
                    "POST",
                    f"projects/{project['id']}/team-plans/",
                    {
                        "org_id": self.oid("employee"),
                        "weight": 1,
                    },
                    expected=(403, 404),
                )
                self.api(
                    role,
                    "POST",
                    f"projects/{project['id']}/surveys/",
                    {
                        "title": self.unique("yetkisiz anket"),
                        "questions": ["QA?"],
                        "invitee_ids": [self.uid("iamemployee")],
                    },
                    expected=(403, 404),
                )
        # PM'nin gerçek governing UH'si mevcut özel hakkını korur.
        self.plan(project, actor="pm_head")

    def test_06_tasks_delegate_cannot_rate_or_survey(self):
        """PI01/CQ01: tasks devri kalite ve yönetici yayın yetkisi değildir."""
        project = self.project()
        self.grant(project, ["tasks"])
        delivery = self.delivery(project, actor="iamhead", progress=30)
        self.api(
            "iamhead",
            "PATCH",
            f"projects/{project['id']}/deliverables/{delivery['id']}/",
            {
                "version": delivery["version"],
                "quality_rating": 5,
            },
            expected=(403,),
        )
        self.api(
            "iamhead",
            "POST",
            f"projects/{project['id']}/surveys/",
            {
                "title": self.unique("yetkisiz kalite anketi"),
                "questions": ["QA?"],
                "invitee_ids": [self.uid("employee")],
            },
            expected=(403,),
        )
        current = self.insights(project)
        self.assertIsNone(current["teams"][0]["deliverables"][0]["quality_rating"])

    def test_07_plan_delivery_stale_version_and_duplicate_request(self):
        """PI03: eski sürüm yazamaz; request-id tekrarında tek plan kalır."""
        project = self.project()
        path = f"projects/{project['id']}/team-plans/"
        payload = {"org_id": self.oid("employee"), "weight": 10}
        headers = {"X-Request-ID": str(uuid.uuid4())}
        first = self.api(
            "pm", "POST", path, payload, headers=headers, expected=(201,)
        ).data
        replay = self.api(
            "pm", "POST", path, payload, headers=headers, expected=(201,)
        ).data
        self.assertEqual(first["teams"][0]["id"], replay["teams"][0]["id"])
        plan = self.insights(project)["teams"][0]
        self.api(
            "pm",
            "PATCH",
            f"{path}{plan['id']}/",
            {"version": plan["version"], "weight": 20},
        )
        self.api(
            "pm",
            "PATCH",
            f"{path}{plan['id']}/",
            {"version": plan["version"], "weight": 99},
            expected=(409,),
        )
        delivery = self.delivery(project, progress=10)
        updated = self.api(
            "pm",
            "PATCH",
            f"projects/{project['id']}/deliverables/{delivery['id']}/",
            {
                "version": delivery["version"],
                "progress": 60,
            },
        ).data
        self.api(
            "pm",
            "PATCH",
            f"projects/{project['id']}/deliverables/{delivery['id']}/",
            {
                "version": delivery["version"],
                "progress": 90,
            },
            expected=(409,),
        )
        summary = self.insights(project)
        self.assertEqual(len(summary["teams"]), 1)
        self.assertEqual(summary["teams"][0]["weight"], 20)
        self.assertEqual(
            summary["teams"][0]["deliverables"][0]["progress"], updated["progress"]
        )

    def test_08_survey_named_answers_are_management_only(self):
        """PS01–03: davetli oy verir; teknik üye toplu sonuç, PM isimli cevap okur."""
        project = self.member(self.project())
        survey = self.survey(project)
        path = f"projects/{project['id']}/surveys/{survey['id']}/respond/"
        payload = {
            "version": survey["version"],
            "answers": {survey["questions"][0]["id"]: 4},
        }
        answer = self.api("iamemployee", "POST", path, payload).data
        self.assertEqual(answer["responded"], 1)
        self.assertNotIn("responses", answer)
        duplicate = self.api("iamemployee", "POST", path, payload).data
        self.assertEqual(duplicate["responded"], 1)
        member_view = self.insights(project, "iamemployee")
        self.assertNotIn("responses", member_view["surveys"][0])
        manager_view = self.insights(project)
        self.assertEqual(
            manager_view["surveys"][0]["responses"][0]["user_id"],
            self.uid("iamemployee"),
        )
        self.assertEqual(self.insights(project, "employee")["surveys"], [])

    def test_09_survey_rejects_uninvited_invalid_and_closed_vote(self):
        """PS01/02: üyelik davet yerine geçmez; kapalı anket değiştirilemez."""
        project = self.member(self.project())
        survey = self.survey(project)
        path = f"projects/{project['id']}/surveys/{survey['id']}/respond/"
        answer = {survey["questions"][0]["id"]: 5}
        self.api(
            "employee",
            "POST",
            path,
            {"version": survey["version"], "answers": answer},
            expected=(403,),
        )
        for invalid in (
            {},
            {str(uuid.uuid4()): 5},
            {survey["questions"][0]["id"]: 6},
            {survey["questions"][0]["id"]: True},
        ):
            self.api(
                "iamemployee",
                "POST",
                path,
                {"version": survey["version"], "answers": invalid},
                expected=(400,),
            )
        closed = self.api(
            "pm",
            "POST",
            f"projects/{project['id']}/surveys/{survey['id']}/close/",
            {"version": survey["version"]},
        ).data
        self.assertEqual(closed["status"], "CLOSED")
        self.api(
            "iamemployee",
            "POST",
            path,
            {"version": closed["version"], "answers": answer},
            expected=(400,),
        )
        self.assertEqual(self.insights(project)["surveys"][0]["responded"], 0)

    def test_10_daily_offline_report_edit_preserves_original(self):
        """RP01–03: kurallı taslak düzenlenir; asıl snapshot ve endeks değişmez."""
        project = self.project()
        self.delivery(project, progress=50, quality_rating=4)
        report = self.report(project)
        original = report["original_markdown"]
        sources = report["sources"]
        computed = report["computed_values"]
        self.assertEqual(report["kind"], "DAILY")
        text = (
            "# "
            + self.unique("insan tarafından düzenlenmiş rapor")
            + "\n\nÖlçüm kapsamı QA sentetik veri."
        )
        updated = self.api(
            "pm",
            "PATCH",
            self.report_path(project, report),
            {
                "version": report["version"],
                "markdown": text,
                "reviewed_scores": {"overall": 72.5},
                "edit_reason": "Sentetik yönetici değerlendirmesi",
            },
        ).data
        self.assertEqual(updated["markdown"], text)
        self.assertEqual(updated["original_markdown"], original)
        self.assertEqual(updated["sources"], sources)
        self.assertEqual(updated["computed_values"], computed)
        self.assertEqual(updated["reviewed_scores"]["overall"], 72.5)
        self.assertGreater(updated["version"], report["version"])
        self.api(
            "pm",
            "PATCH",
            self.report_path(project, report),
            {
                "version": report["version"],
                "markdown": "Eski sürüm",
                "edit_reason": "QA",
            },
            expected=(409,),
        )
        download = self.api(
            "pm", "GET", self.report_path(project, report) + "markdown/"
        )
        self.assertIn(text, download.text)
        self.assertIn("72.5", download.text)

    def test_11_report_edits_and_publication_have_independent_rights(self):
        """RP03/04: tasks-only taslak okur; insan düzenleme/yayın yönetici yetkisidir."""
        project = self.project()
        self.grant(project, ["tasks"])
        report = self.report(project, "WEEKLY")
        path = self.report_path(project, report)
        self.api("iamhead", "GET", path)
        for role in ("iamhead", "unithead", "director", "admin", "employee"):
            self.api(
                role,
                "PATCH",
                path,
                {
                    "version": report["version"],
                    "markdown": "Yetkisiz",
                    "edit_reason": "QA",
                },
                expected=(403, 404),
            )
            self.api(
                role,
                "POST",
                path + "publish/",
                {"version": report["version"]},
                expected=(403, 404),
            )
        for values in (
            {"overall": -1},
            {"quality": 101},
            {"delivery": True},
            {"unknown": 5},
        ):
            self.api(
                "pm",
                "PATCH",
                path,
                {
                    "version": report["version"],
                    "reviewed_scores": values,
                    "edit_reason": "QA",
                },
                expected=(400,),
            )
        self.api(
            "pm",
            "PATCH",
            path,
            {"version": report["version"], "markdown": "Gerekçesiz"},
            expected=(400,),
        )
        current = self.api("pm", "GET", path).data
        self.assertEqual(current["markdown"], report["markdown"])
        self.assertEqual(current["version"], report["version"])
        published = self.api(
            "pm", "POST", path + "publish/", {"version": report["version"]}
        ).data
        self.assertEqual(published["status"], "PUBLISHED")
        self.assertIsNotNone(published["published_at"])
        self.api(
            "pm",
            "PATCH",
            path,
            {
                "version": published["version"],
                "markdown": "Onay sonrası",
                "edit_reason": "QA",
            },
            expected=(400, 409),
        )

    def test_12_changed_source_invalidates_report_review(self):
        """CQ03/RP04: yeni kanıt eski hazır taslağın yayın onayını boşa çıkarır."""
        project = self.project()
        delivery = self.delivery(project, progress=20)
        report = self.report(project)
        self.api(
            "pm",
            "PATCH",
            f"projects/{project['id']}/deliverables/{delivery['id']}/",
            {"version": delivery["version"], "progress": 80},
        )
        self.api(
            "pm",
            "POST",
            self.report_path(project, report) + "publish/",
            {"version": report["version"]},
            expected=(409,),
        )
        self.api(
            "pm",
            "PATCH",
            self.report_path(project, report),
            {
                "version": report["version"],
                "markdown": "Eski kaynak",
                "edit_reason": "QA",
            },
            expected=(409,),
        )
        unchanged = self.api("pm", "GET", self.report_path(project, report)).data
        self.assertEqual(unchanged["sources"], report["sources"])
        self.assertEqual(unchanged["markdown"], report["markdown"])
        self.assertEqual(unchanged["status"], "READY")

    def test_13_report_period_and_kind_validation(self):
        """RP01: geçersiz dönem/tür yan etkisiz reddedilir."""
        project = self.project()
        path = f"projects/{project['id']}/insight-reports/"
        for patch in (
            {"kind": "MONTHLY"},
            {"period_start": "bad-date"},
            {"period_start": "2026-11-19", "period_end": "2026-11-18"},
            {"period_start": "2020-01-01", "period_end": "2022-01-01"},
            {"generation_mode": "SILENT_PROVIDER"},
        ):
            payload = {
                "kind": "DAILY",
                "period_start": "2026-11-18",
                "period_end": "2026-11-18",
                "generation_mode": "RULE_BASED",
            }
            payload.update(patch)
            self.api("pm", "POST", path, payload, expected=(400,))
        self.assertEqual(self.insights(project)["reports"], [])

    def test_14_closure_publication_requires_human_completed_project(self):
        """CQ01/RP04: öneri projeyi kapatmaz; kapanış raporu insan kararı sonrası yayınlanır."""
        project = self.project()
        report = self.report(project, "CLOSURE")
        self.assertEqual(self.fresh_project(project)["status"], "PLANNED")
        self.api(
            "pm",
            "POST",
            self.report_path(project, report) + "publish/",
            {"version": report["version"]},
            expected=(400,),
        )
        current = self.fresh_project(project)
        closed = self.api(
            "pm",
            "POST",
            f"projects/{project['id']}/close/",
            {"version": current["version"], "summary": "Sentetik insan kapanış kararı"},
        ).data
        self.assertEqual(closed["status"], "COMPLETED")
        final = self.report(project, "CLOSURE")
        published = self.api(
            "pm",
            "POST",
            self.report_path(project, final) + "publish/",
            {"version": final["version"]},
        ).data
        self.assertEqual(published["status"], "PUBLISHED")
        self.assertEqual(published["computed_values"]["overall"], None)

    def test_15_workload_self_manager_and_foreign_scope(self):
        """PW01: kişi dizini okunabilirliği iş ayrıntısı hakkı oluşturmaz."""
        path = f"people/{self.uid('employee')}/workload/"
        for role in ("employee", "teammanager", "unithead", "director"):
            data = self.api(role, "GET", path).data
            self.assertTrue(data["permissions"]["can_view_workload"])
            self.assertEqual(data["person"]["id"], self.uid("employee"))
            self.assertEqual(
                set(data["summary"]["by_context"]),
                {"UNIT_WORK", "PROJECT_TASK", "CASE_ACTION"},
            )
        for role in ("iamhead", "iamemployee", "pm", "admin"):
            self.api(role, "GET", path, expected=(403, 404))

    def test_16_assignable_scope_drives_form_without_widening_rights(self):
        """PW02/03: kişi kartı hedefi sunucudan gelir; başka unit'e atama reddedilir."""
        path = f"people/{self.uid('employee')}/assignable-scope/"
        for role in ("unithead", "teammanager"):
            scope = self.api(role, "GET", path).data
            self.assertTrue(scope["permissions"]["can_assign_work"])
            self.assertEqual(
                scope["assignment"]["allowed_target"]["person_id"], self.uid("employee")
            )
            payload = dict(scope["assignment"]["suggested_payload"])
            payload.update(
                title=self.unique("karttan resmî atama"),
                description="Sentetik görev açıklaması",
            )
            work = self.api(role, "POST", "work/", payload, expected=(201,)).data
            self.assertEqual(work["assigned_to_id"], self.uid("employee"))
            self.assertEqual(work["owner_org_id"], self.oid("employee"))
            self.assertEqual(work["context"], "UNIT_WORK")
            self.assertTrue(work["formal"])
            self.assertIsNotNone(work["sla"])
            workload = self.api(
                role, "GET", f"people/{self.uid('employee')}/workload/"
            ).data
            self.assertIn(work["id"], {row["id"] for row in workload["works"]})
        for role in ("employee", "iamhead", "pm", "admin"):
            scope = self.api(role, "GET", path).data
            self.assertFalse(scope["permissions"]["can_assign_work"])
            self.assertIsNone(scope["assignment"]["allowed_target"])
            self.api(
                role,
                "POST",
                "work/",
                {
                    "title": self.unique("yetkisiz resmî atama"),
                    "assignee_id": self.uid("employee"),
                    "personal": False,
                },
                expected=(403,),
            )
        listed = records(
            self.api("teammanager", "GET", "people/?assignable=true&limit=500").data
        )
        self.assertIn(self.uid("employee"), {row["id"] for row in listed})
        self.assertNotIn(self.uid("iamemployee"), {row["id"] for row in listed})

    def test_17_personal_form_preserves_chosen_values(self):
        """PW03: çalışanın kişisel tarih/öncelik/açıklaması yeniden GET'te korunur."""
        scope = self.api(
            "employee", "GET", f"people/{self.uid('employee')}/assignable-scope/"
        ).data
        self.assertTrue(scope["permissions"]["can_create_personal_work"])
        due = (dt.datetime.now(dt.UTC) + dt.timedelta(days=3)).replace(microsecond=0)
        payload = {
            "title": self.unique("kişisel form"),
            "description": "Form açıklaması korunur",
            "personal": True,
            "priority": "HIGH",
            "due_at": due.isoformat(),
        }
        work = self.api("employee", "POST", "work/", payload, expected=(201,)).data
        persisted = self.api("employee", "GET", f"work/{work['id']}/").data
        self.assertFalse(persisted["formal"])
        self.assertFalse(persisted.get("sla"))
        self.assertEqual(persisted["assigned_to_id"], self.uid("employee"))
        self.assertEqual(persisted["priority"], "HIGH")
        self.assertEqual(persisted["description"], payload["description"])
        self.assertEqual(dt.datetime.fromisoformat(persisted["due_at"]), due)

    def test_18_person_workload_keeps_project_evidence_private(self):
        """PW01: personel sağlayan UH kişi kartından teknik proje kanıtını alamaz."""
        project = self.member(self.project())
        private = self.unique("özel teknik proje açıklaması")
        current = self.fresh_project(project)
        self.api(
            "pm",
            "POST",
            f"projects/{project['id']}/progress/",
            {
                "version": current["version"],
                "done": private,
                "next_step": private,
            },
        )
        current = self.fresh_project(project)
        task = self.api(
            "pm",
            "POST",
            f"projects/{project['id']}/tasks/",
            {
                "version": current["version"],
                "title": self.unique("proje görevi"),
                "assignee_id": self.uid("iamemployee"),
                "description": private,
            },
            expected=(201,),
        ).data
        member_view = self.api(
            "iamemployee", "GET", f"people/{self.uid('iamemployee')}/workload/"
        ).data
        self.assertIn(private, json.dumps(member_view, ensure_ascii=False))
        manager_view = self.api(
            "iamhead", "GET", f"people/{self.uid('iamemployee')}/workload/"
        ).data
        self.assertNotIn(private, json.dumps(manager_view, ensure_ascii=False))
        selected = next(row for row in manager_view["works"] if row["id"] == task["id"])
        self.assertEqual(selected["visibility"], "SUMMARY")
        self.assertFalse(selected["permissions"]["update"])

    def test_19_jwt_new_surfaces_keep_org_scope_and_read_only(self):
        """PI01/PW01: yeni nested API org kapsamını ve JWT salt okunurluğunu korur."""
        project = self.project()
        self.grant(project, ["read"], "fulladmin")
        clients = []
        bearer = ApiClient(CONFIG["base_url"])
        try:
            for role in ("employee", "iamemployee"):
                created = self.api(
                    "fulladmin",
                    "POST",
                    "api-clients/",
                    {
                        "name": self.unique("dar kapsamlı JWT"),
                        "scopes": ["projects:read", "people:read"],
                        "org_node_id": self.oid(role),
                    },
                    expected=(201,),
                ).data
                clients.append(created)
            allowed, outside = clients
            inside_headers = {"Authorization": "Bearer " + allowed["token"]}
            outside_headers = {"Authorization": "Bearer " + outside["token"]}
            path = f"projects/{project['id']}/insights/"
            self.assertEqual(
                bearer.request("GET", path, headers=inside_headers).status, 200
            )
            self.assertIn(
                bearer.request("GET", path, headers=outside_headers).status, (403, 404)
            )
            response = bearer.request(
                "GET",
                f"people/{self.uid('employee')}/workload/",
                headers=inside_headers,
            )
            self.assertEqual(response.status, 200)
            self.assertFalse(response.data["permissions"]["can_assign_work"])
            self.assertFalse(response.data["permissions"]["can_create_personal_work"])
            self.assertIn(
                bearer.request(
                    "GET",
                    f"people/{self.uid('employee')}/workload/",
                    headers=outside_headers,
                ).status,
                (403, 404),
            )
            self.assertEqual(
                bearer.request(
                    "POST",
                    f"projects/{project['id']}/team-plans/",
                    {
                        "org_id": self.oid("employee"),
                        "weight": 50,
                    },
                    headers=inside_headers,
                ).status,
                403,
            )
            self.api("fulladmin", "POST", f"api-clients/{allowed['id']}/revoke/", {})
            self.assertEqual(
                bearer.request("GET", path, headers=inside_headers).status, 401
            )
            clients.remove(allowed)
        finally:
            for client in clients:
                self.api("fulladmin", "POST", f"api-clients/{client['id']}/revoke/", {})

    def test_20_survey_versioned_change_keeps_one_person_one_response(self):
        """PS02/03: sürümlü cevap değişir, replay sayımı artırmaz, eski cevap yazamaz."""
        project = self.member(self.project())
        survey = self.survey(
            project, invitees=[self.uid("iamemployee"), self.uid("pm")]
        )
        path = f"projects/{project['id']}/surveys/{survey['id']}/respond/"
        question = survey["questions"][0]["id"]
        first = self.api(
            "iamemployee",
            "POST",
            path,
            {"version": survey["version"], "answers": {question: 3}},
        ).data
        self.assertEqual(first["responded"], 1)
        self.assertEqual(first["response_rate"], 50)
        self.assertIsInstance(first["my_response_version"], int)
        changed_payload = {
            "version": survey["version"],
            "response_version": first["my_response_version"],
            "answers": {question: 5},
        }
        changed = self.api("iamemployee", "POST", path, changed_payload).data
        self.assertGreater(changed["my_response_version"], first["my_response_version"])
        self.assertEqual(changed["my_answers"], {question: 5})
        self.assertEqual(changed["responded"], 1)
        replay = self.api("iamemployee", "POST", path, changed_payload).data
        self.assertEqual(replay["my_response_version"], changed["my_response_version"])
        self.assertEqual(replay["responded"], 1)
        self.api(
            "iamemployee",
            "POST",
            path,
            {
                "version": survey["version"],
                "response_version": first["my_response_version"],
                "answers": {question: 2},
            },
            expected=(409,),
        )
        self.assertEqual(
            self.insights(project)["surveys"][0]["responses"][0]["answers"],
            {question: 5},
        )
        second = self.api(
            "pm", "POST", path, {"version": survey["version"], "answers": {question: 1}}
        ).data
        self.assertEqual(second["responded"], 2)
        self.assertEqual(second["response_rate"], 100)
        self.assertEqual(second["results"][0]["average"], 3)

    def test_21_summary_source_privacy_and_read_grant_revocation(self):
        """RP04/PW01: özet okuyucusu iç kanıt/taslak alamaz; iptal yayınlı çıktıyı da kapatır."""
        project = self.project()
        marker = self.unique("özel teslim kanıtı")
        self.delivery(project, progress=50, evidence=marker)
        self.survey(project, invitees=[self.uid("pm")])
        grant = self.grant(project, ["read"])
        report = self.report(project)
        for role in ("employee", "director"):
            summary = self.insights(project, role)
            self.assertNotIn(marker, json.dumps(summary, ensure_ascii=False))
            self.assertEqual(summary["reports"], [])
            for suffix in ("", "markdown/"):
                self.api(
                    role,
                    "GET",
                    self.report_path(project, report) + suffix,
                    expected=(403, 404),
                )
        # The creator's ordinary UH has neither an accepted resource request
        # nor an explicit project read grant in this fixture.
        self.api(
            "unithead",
            "GET",
            f"projects/{project['id']}/insights/",
            expected=(403, 404),
        )
        self.api(
            "iamhead", "GET", self.report_path(project, report), expected=(403, 404)
        )
        published = self.api(
            "pm",
            "POST",
            self.report_path(project, report) + "publish/",
            {"version": report["version"]},
        ).data
        self.assertEqual(published["status"], "PUBLISHED")
        allowed = self.api("iamhead", "GET", self.report_path(project, report)).data
        self.assertIn(marker, json.dumps(allowed["sources"], ensure_ascii=False))
        current = self.fresh_project(project)
        self.api(
            "pm",
            "POST",
            f"projects/{project['id']}/authority-revoke/",
            {
                "version": current["version"],
                "grant_id": grant["id"],
                "reason": "Sentetik okuma süresi sona erdi",
            },
        )
        for suffix in ("", "markdown/"):
            self.api(
                "iamhead",
                "GET",
                self.report_path(project, report) + suffix,
                expected=(403, 404),
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--password-env", default="ONECS_DEMO_PASSWORD")
    parser.add_argument(
        "--env-file", default=str(Path(__file__).resolve().parents[1] / ".env")
    )
    parser.add_argument("--allow-mutations", action="store_true")
    parser.add_argument(
        "--output", default="tests/artifacts/project-insights-acceptance.json"
    )
    parser.add_argument("--test", action="append", dest="test_names")
    args = parser.parse_args()
    if not args.allow_mutations:
        parser.error(
            "Yalnız koordine edilmiş sentetik ortamda --allow-mutations ile çalıştırın"
        )
    target = urllib.parse.urlparse(args.base_url)
    if target.scheme not in ("http", "https") or target.hostname not in (
        "localhost",
        "127.0.0.1",
        "::1",
    ):
        parser.error("Bu koşucu yalnız yerel sentetik ortam içindir")
    password = os.environ.get(args.password_env)
    if not password and Path(args.env_file).is_file():
        for line in Path(args.env_file).read_text().splitlines():
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            key, value = line.split("=", 1)
            if key.strip() == args.password_env:
                password = value.strip()
                if (
                    len(password) > 1
                    and password[0] == password[-1]
                    and password[0] in ("'", '"')
                ):
                    password = password[1:-1]
                break
    if not password:
        parser.error(f"{args.password_env} tanımlı olmalı; parola kaydedilmez")
    CONFIG.update(base_url=args.base_url.rstrip("/"), password=password)
    names = unittest.defaultTestLoader.getTestCaseNames(ProjectInsightsAcceptance)
    if args.test_names:
        unknown = set(args.test_names) - set(names)
        if unknown:
            parser.error("Bilinmeyen test: " + ", ".join(sorted(unknown)))
        names = list(dict.fromkeys(args.test_names))
    started = time.monotonic()
    suite = unittest.TestSuite(ProjectInsightsAcceptance(name) for name in names)
    result = unittest.TextTestRunner(verbosity=2, resultclass=EvidenceResult).run(suite)
    evidence = {
        "application": "onecs",
        "run_key": ProjectInsightsAcceptance.run_key,
        "suite": "project-insights-and-person-workload",
        "timestamp_utc": dt.datetime.now(dt.UTC).isoformat(),
        "base_url": args.base_url,
        "duration_seconds": round(time.monotonic() - started, 3),
        "tests_run": result.testsRun,
        "successful": result.wasSuccessful(),
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "selection": args.test_names or "all",
        "results": result.evidence,
        "generation_mode": "RULE_BASED",
        "external_integrations_verified": False,
        "baseline_not_rerun": {
            "backend_tests": 193,
            "backend_subtests": 41,
            "http_tests": 46,
            "frontend_tests": 9,
        },
    }
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    return 0 if result.wasSuccessful() and result.testsRun and not result.skipped else 1


if __name__ == "__main__":
    sys.exit(main())
