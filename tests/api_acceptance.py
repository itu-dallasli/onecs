#!/usr/bin/env python3
"""Atlas canlı HTTP kabul testleri; yalnız ayrı, sentetik test ortamında çalıştırın."""

from __future__ import annotations

import argparse
import datetime as dt
import http.cookiejar
import json
import os
import sys
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ApiResponse:
    def __init__(self, status, headers, body):
        self.status = status
        self.headers = dict(headers)
        self.text = body.decode("utf-8", errors="replace")
        try:
            self.data = json.loads(self.text) if self.text else None
        except json.JSONDecodeError:
            self.data = None

    def brief(self):
        # Never include auth payloads, cookies or request headers in a report.
        content_type = self.headers.get("Content-Type", "")
        body = self.text
        if isinstance(self.data, dict):
            sensitive = {
                "token",
                "password",
                "secret",
                "csrf_token",
                "access_token",
                "refresh_token",
            }
            body = json.dumps(
                {
                    k: "[MASKED]" if k.lower() in sensitive else v
                    for k, v in self.data.items()
                },
                ensure_ascii=False,
                default=str,
            )
        return f"HTTP {self.status}; content-type={content_type}; response={body[:350]}"


class ApiClient:
    def __init__(self, base_url, prefix="/api/v1"):
        self.base_url = base_url.rstrip("/")
        self.prefix = prefix.rstrip("/")
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar), NoRedirect()
        )

    def csrf(self):
        cookies = {cookie.name: cookie.value for cookie in self.jar}
        return cookies.get("atlas_csrftoken") or cookies.get("csrftoken", "")

    def request(self, method, path, payload=None, *, csrf=True, headers=None):
        target = path if path.startswith("/") else f"{self.prefix}/{path.lstrip('/')}"
        request_headers = {"Accept": "application/json", "Origin": self.base_url}
        if payload is not None:
            request_headers["Content-Type"] = "application/json"
        if csrf and self.csrf():
            request_headers["X-CSRFToken"] = self.csrf()
        request_headers.update(headers or {})
        encoded = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            f"{self.base_url}{target}",
            data=encoded,
            method=method,
            headers=request_headers,
        )
        try:
            with self.opener.open(req, timeout=20) as response:
                return ApiResponse(response.status, response.headers, response.read())
        except urllib.error.HTTPError as error:
            return ApiResponse(error.code, error.headers, error.read())

    def login(self, username, password):
        self.request("GET", "auth/csrf/")
        return self.request(
            "POST",
            "auth/login/",
            {"username": username, "password": password, "method": "local"},
        )


CONFIG = {}


def records(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("results", "items", "data"):
            if isinstance(data.get(key), list):
                return data[key]
    raise AssertionError(
        "API liste cevabı JSON dizi veya results/items/data dizisi olmalı"
    )


def person(data):
    if isinstance(data, dict):
        for key in ("user", "person"):
            if isinstance(data.get(key), dict):
                return data[key]
    return data


class AtlasApiAcceptance(unittest.TestCase):
    """All callers use real independent sessions; no God Mode or database writes."""

    @classmethod
    def setUpClass(cls):
        cls.run_key = "QA-" + uuid.uuid4().hex[:10]
        cls.observations = {}
        cls.clients = {}
        cls.users = {}
        for username in (
            "director",
            "unithead",
            "teammanager",
            "employee",
            "pm",
            "pm_head",
            "admin",
            "iamhead",
            "iamemployee",
        ):
            client = ApiClient(CONFIG["base_url"])
            response = client.login(username, CONFIG["password"])
            if response.status != 200:
                raise AssertionError(
                    f"Sentetik rol giriş yapamadı: {username}, HTTP {response.status}"
                )
            me = client.request("GET", "auth/me/")
            if me.status != 200:
                # The planned API also permits /me/ as its public identity endpoint.
                me = client.request("GET", "me/")
            if me.status != 200 or not isinstance(person(me.data), dict):
                raise AssertionError(
                    f"Kullanıcı kimliği okunamadı: {username}, HTTP {me.status}"
                )
            cls.clients[username] = client
            cls.users[username] = person(me.data)

    def api(self, role, method, path, payload=None, *, expected=(200,), **kwargs):
        result = self.clients[role].request(method, path, payload, **kwargs)
        self.assertIn(
            result.status, expected, f"{role} {method} {path}: {result.brief()}"
        )
        self.assertNotIn("Traceback (most recent call last)", result.text)
        return result

    def unique(self, text):
        return f"{self.run_key} {text} {uuid.uuid4().hex[:5]}"

    def user_id(self, role):
        self.assertIn(
            "id", self.users[role], "me cevabında kalıcı kullanıcı id bekleniyor"
        )
        return self.users[role]["id"]

    def create_project(self, role="employee"):
        return self.api(
            role,
            "POST",
            "projects/",
            {
                "title": self.unique("proje"),
                "description": "Sentetik kabul projesi; yetki ve kaynak tahsisi doğrulaması.",
                "expected_outcome": "Kaynak bağlı yönetim görünümü",
                "pm_id": self.user_id("pm"),
            },
            expected=(201,),
        ).data

    def submit_project(self, project, role="employee"):
        return self.api(
            role,
            "POST",
            f"projects/{project['id']}/submit/",
            {"version": project["version"]},
        ).data

    def approved_project(self):
        project = self.submit_project(self.create_project())
        return self.api(
            "pm",
            "POST",
            f"projects/{project['id']}/review/",
            {
                "version": project["version"],
                "decision": "APPROVE",
                "note": "QA kapsamı onaylandı",
            },
        ).data

    def create_work(self, role="employee", **overrides):
        payload = {"title": self.unique("iş"), "description": "Sentetik QA işi"}
        payload.update(overrides)
        return self.api(role, "POST", "work/", payload, expected=(201,)).data

    def get_work(self, role, work_id):
        return self.api(role, "GET", f"work/{work_id}/?all_contexts=true").data

    def test_01_role_sessions(self):
        """K01: sentetik rol oturumları ayrı kullanıcı kimlikleri taşır."""
        ids = [self.user_id(role) for role in self.users]
        self.assertEqual(len(ids), len(set(ids)))
        for role in self.clients:
            dashboard = self.api(role, "GET", "dashboard/")
            self.assertIsInstance(dashboard.data, dict)

    def test_02_unauthenticated_surfaces_rejected(self):
        """K14: login olmadan yönetim verisi hiçbir modülde okunamaz."""
        anonymous = ApiClient(CONFIG["base_url"])
        for path in (
            "dashboard/",
            "projects/",
            "work/",
            "cases/",
            "organization/",
            "people/",
            "reports/",
            "credentials/",
            "notifications/",
            "activity/",
        ):
            with self.subTest(path=path):
                response = anonymous.request("GET", path)
                self.assertIn(
                    response.status, (401, 403), f"{path}: {response.brief()}"
                )
                self.assertNotIn("Traceback", response.text)

    def test_03_mutation_requires_csrf(self):
        """Session oturumunda CSRF başlığı eksik yazma reddedilir."""
        response = self.api(
            "employee",
            "POST",
            "work/",
            {"title": self.unique("CSRF engeli")},
            expected=(403,),
            csrf=False,
        )
        self.assertNotIn("Traceback", response.text)

    def test_04_logout_revokes_session(self):
        """Çıkış yapılan cookie tekrar API okuma hakkı taşımaz."""
        isolated = ApiClient(CONFIG["base_url"])
        self.assertEqual(isolated.login("employee", CONFIG["password"]).status, 200)
        self.assertIn(isolated.request("POST", "auth/logout/", {}).status, (200, 204))
        self.assertIn(isolated.request("GET", "dashboard/").status, (401, 403))

    def test_05_bad_login_has_no_session(self):
        """Yanlış parola rol oturumu oluşturamaz ve teknik traceback döndürmez."""
        isolated = ApiClient(CONFIG["base_url"])
        response = isolated.login("employee", "Atlas-invalid-" + uuid.uuid4().hex)
        self.assertIn(response.status, (400, 401, 403))
        self.assertNotIn("Traceback", response.text)
        self.assertIn(isolated.request("GET", "dashboard/").status, (401, 403))

    def test_06_bad_identifiers_never_crash_api(self):
        """Hatalı istemci kimliği JSON 4xx üretir; uygulama/DB traceback üretmez."""
        for resource in (
            "projects",
            "work",
            "cases",
            "events",
            "credentials",
            "reports",
        ):
            with self.subTest(resource=resource):
                response = self.api(
                    "employee",
                    "GET",
                    f"{resource}/not-a-uuid/",
                    expected=(400, 403, 404),
                )
                self.assertIsInstance(response.data, dict, response.brief())

    def test_07_invalid_mutation_is_validation_error(self):
        """Zorunlu başlığı boş bir iş yaratma isteği kontrollü doğrulama hatasıdır."""
        response = self.api(
            "employee", "POST", "work/", {"title": ""}, expected=(400, 422)
        )
        self.assertIsInstance(response.data, dict, response.brief())

    def test_08_login_requires_csrf(self):
        """Anonim login de CSRF'siz sessiz oturum oluşturamaz."""
        isolated = ApiClient(CONFIG["base_url"])
        isolated.request("GET", "auth/csrf/")
        response = isolated.request(
            "POST",
            "auth/login/",
            {"username": "employee", "password": CONFIG["password"], "method": "local"},
            csrf=False,
        )
        self.assertEqual(
            response.status, 403, "Login CSRF başlığı olmadan reddedilmeli"
        )
        self.assertIn(isolated.request("GET", "dashboard/").status, (401, 403))

    def test_10_private_draft_and_pm_routing(self):
        """K02/K14: özel taslak gönderilene kadar PM veya diğer yöneticiye açılmaz."""
        project = self.create_project()
        self.assertEqual(project["status"], "DRAFT")
        for role in ("pm", "director", "unithead", "iamhead", "admin"):
            with self.subTest(role=role):
                self.api(role, "GET", f"projects/{project['id']}/", expected=(403, 404))
                found = self.api(
                    role,
                    "GET",
                    "projects/?search=" + urllib.parse.quote(project["title"]),
                )
                self.assertNotIn(
                    project["id"], {str(row["id"]) for row in records(found.data)}
                )
        submitted = self.submit_project(project)
        self.assertEqual(submitted["status"], "SUBMITTED")
        self.api("pm", "GET", f"projects/{project['id']}/")
        self.api(
            "iamhead",
            "POST",
            f"projects/{project['id']}/review/",
            {"version": submitted["version"], "decision": "APPROVE"},
            expected=(403, 404),
        )
        current = self.api("employee", "GET", f"projects/{project['id']}/").data
        self.assertEqual(current["status"], "SUBMITTED")
        self.assertEqual(current["version"], submitted["version"])

    def test_11_project_revision_approval_and_stale_version(self):
        """K03/K38: düzeltme/yeniden gönderme sürümlüdür; eski sürüm kararı işlemez."""
        project = self.submit_project(self.create_project())
        revised = self.api(
            "pm",
            "POST",
            f"projects/{project['id']}/review/",
            {
                "version": project["version"],
                "decision": "REVISION",
                "note": "Çıktıyı netleştirin",
            },
        ).data
        self.assertEqual(revised["status"], "REVISION")
        revised = self.api(
            "employee",
            "PATCH",
            f"projects/{project['id']}/",
            {
                "version": revised["version"],
                "expected_outcome": "Kaynakları doğrulanmış haftalık özet",
            },
        ).data
        submitted = self.submit_project(revised)
        self.api(
            "pm",
            "POST",
            f"projects/{project['id']}/review/",
            {"version": project["version"], "decision": "APPROVE"},
            expected=(409,),
        )
        approved = self.api(
            "pm",
            "POST",
            f"projects/{project['id']}/review/",
            {"version": submitted["version"], "decision": "APPROVE"},
        ).data
        self.assertEqual(approved["status"], "PLANNED")
        self.assertEqual(approved["published_revision"], 2)
        self.api(
            "pm",
            "POST",
            f"projects/{project['id']}/review/",
            {"version": submitted["version"], "decision": "APPROVE"},
            expected=(409,),
        )

    def test_12_project_self_and_implicit_director_approval_denied(self):
        """K04/K05: gerçek başvuran kendi onaylayıcısı olamaz; direktör otomatik PM değildir."""
        own = self.submit_project(self.create_project("pm"), "pm")
        self.api(
            "pm",
            "POST",
            f"projects/{own['id']}/review/",
            {"version": own["version"], "decision": "APPROVE"},
            expected=(403,),
        )
        approved_own = self.api(
            "pm_head",
            "POST",
            f"projects/{own['id']}/review/",
            {
                "version": own["version"],
                "decision": "APPROVE",
                "note": "Bağımsız PM Unit Head kararı",
            },
        ).data
        self.assertEqual(approved_own["status"], "PLANNED")
        project = self.submit_project(self.create_project())
        self.api(
            "director",
            "POST",
            f"projects/{project['id']}/review/",
            {"version": project["version"], "decision": "APPROVE"},
            expected=(403, 404),
        )
        current = self.api("pm", "GET", f"projects/{project['id']}/").data
        self.assertEqual(current["status"], "SUBMITTED")
        self.assertEqual(current["version"], project["version"])

    def test_13_project_resource_acceptance_does_not_grant_management(self):
        """K05/K07/K20: IAM kaynak kabulü proje yönetimi değildir; görev PM bağlamındadır."""
        project = self.approved_project()
        resource = self.api(
            "pm",
            "POST",
            f"projects/{project['id']}/members/",
            {
                "version": project["version"],
                "user_id": self.user_id("iamemployee"),
                "summary": "Sentetik IAM kaynak kabulü",
            },
            expected=(201,),
        ).data
        current = self.api("pm", "GET", f"projects/{project['id']}/").data
        self.api(
            "pm",
            "POST",
            f"projects/{project['id']}/tasks/",
            {
                "version": current["version"],
                "assignee_id": self.user_id("iamemployee"),
                "title": self.unique("kabul öncesi görev"),
            },
            expected=(403,),
        )
        accepted = self.api(
            "iamhead",
            "POST",
            f"participation-requests/{resource['id']}/decide/",
            {
                "version": resource["version"],
                "decision": "ACCEPT",
                "note": "Kaynak ayrıldı",
            },
        ).data
        self.assertEqual(accepted["status"], "ACCEPTED")
        project = self.api("pm", "GET", f"projects/{project['id']}/").data
        task = self.api(
            "pm",
            "POST",
            f"projects/{project['id']}/tasks/",
            {
                "version": project["version"],
                "assignee_id": self.user_id("iamemployee"),
                "title": self.unique("IAM proje görevi"),
            },
            expected=(201,),
        ).data
        self.assertEqual(task["context"], "PROJECT_TASK")
        self.assertFalse(task["formal"])
        self.assertFalse(task.get("sla"), "PM tarihi unit SLA'sı başlatmamalı")
        before = self.get_work("iamemployee", task["id"])
        self.api(
            "iamhead",
            "PATCH",
            f"work/{task['id']}/?all_contexts=true",
            {
                "version": before["version"],
                "title": "Yetkisiz kaynak yöneticisi değişikliği",
            },
            expected=(403, 404),
        )
        after = self.get_work("iamemployee", task["id"])
        self.assertEqual(after["title"], before["title"])
        self.assertEqual(after["version"], before["version"])
        unit_list = records(self.api("iamemployee", "GET", "work/").data)
        self.assertNotIn(task["id"], {row["id"] for row in unit_list})
        assigned = records(
            self.api("iamemployee", "GET", "work/?mine=true&all_contexts=true").data
        )
        self.assertIn(task["id"], {row["id"] for row in assigned})

    def test_14_project_audience_cannot_read_full_contributions(self):
        """K14: yayın özeti okuyucusu üyelik gerektiren tam katkıları devralmaz."""
        project = self.approved_project()
        secret_marker = self.unique("üye teknik ayrıntısı")
        project = self.api(
            "pm",
            "POST",
            f"projects/{project['id']}/progress/",
            {
                "version": project["version"],
                "done": secret_marker,
                "next_step": "Sadece proje üyelerine yönelik teknik adım",
                "progress": 20,
            },
        ).data
        # The author is an audience member after publication but has not accepted project membership.
        public_summary = self.api("employee", "GET", f"projects/{project['id']}/").data
        self.assertNotIn(secret_marker, json.dumps(public_summary, ensure_ascii=False))
        self.assertEqual(public_summary.get("contributions", []), [])

    def test_15_project_delegation_scope_and_revocation(self):
        """K05/K17: açık read yetkisi yönetim değildir; devredilemez ve iptal hemen uygulanır."""
        project = self.approved_project()
        expires = (dt.datetime.now(dt.UTC) + dt.timedelta(days=1)).isoformat()
        grant = self.api(
            "pm",
            "POST",
            f"projects/{project['id']}/authorities/",
            {
                "version": project["version"],
                "user_id": self.user_id("iamhead"),
                "permissions": ["read"],
                "expires_at": expires,
                "reason": "Süreli salt okunur inceleme",
            },
            expected=(201,),
        ).data
        delegated = self.api("iamhead", "GET", f"projects/{project['id']}/").data
        self.assertFalse(delegated["permissions"]["manage"])
        self.api(
            "iamhead",
            "PATCH",
            f"projects/{project['id']}/",
            {
                "version": delegated["version"],
                "progress_note": "Salt okunur yetkiyle yazılamaz",
            },
            expected=(403,),
        )
        self.api(
            "iamhead",
            "POST",
            f"projects/{project['id']}/authorities/",
            {
                "version": delegated["version"],
                "user_id": self.user_id("iamemployee"),
                "permissions": ["manage"],
                "expires_at": expires,
                "reason": "Yetkisiz yeniden devir",
            },
            expected=(403,),
        )
        current = self.api("pm", "GET", f"projects/{project['id']}/").data
        self.api(
            "pm",
            "POST",
            f"projects/{project['id']}/authority-revoke/",
            {
                "version": current["version"],
                "grant_id": grant["id"],
                "reason": "İnceleme sona erdi",
            },
        )
        self.api("iamhead", "GET", f"projects/{project['id']}/", expected=(403, 404))

    def test_16_significant_project_change_keeps_published_revision(self):
        """K36/K38: önemli değişiklik bağımsız karara gider; eski yayın karar öncesi korunur."""
        project = self.approved_project()
        proposed_title = self.unique("yeni ana kapsam")
        proposed = self.api(
            "pm",
            "POST",
            f"projects/{project['id']}/propose-change/",
            {
                "version": project["version"],
                "title": proposed_title,
                "expected_outcome": "Genişletilmiş sentetik çıktı",
                "reason": "Ana kapsam genişliyor",
            },
            expected=(201,),
        ).data
        old_view = self.api("employee", "GET", f"projects/{project['id']}/").data
        self.assertEqual(old_view["title"], project["title"])
        self.assertEqual(old_view["published_revision"], project["published_revision"])
        self.api(
            "pm",
            "POST",
            f"projects/{project['id']}/review/",
            {"version": proposed["version"], "decision": "APPROVE"},
            expected=(403,),
        )
        approved = self.api(
            "pm_head",
            "POST",
            f"projects/{project['id']}/review/",
            {
                "version": proposed["version"],
                "decision": "APPROVE",
                "note": "Bağımsız kapsam kararı",
            },
        ).data
        self.assertEqual(approved["title"], proposed_title)
        self.assertEqual(
            approved["published_revision"], project["published_revision"] + 1
        )

    def test_17_project_totals_distinguish_managed_and_contributing_units(self):
        """K12: iki unit katkı verir; proje bir kez sayılır ve PM birimi yönetim portföyüdür."""
        before = self.api("director", "GET", "dashboard/").data
        before_units = {row["id"]: row for row in before["unit_summaries"]}
        project = self.approved_project()
        for employee_role, manager_role in (
            ("employee", "unithead"),
            ("iamemployee", "iamhead"),
        ):
            project = self.api("pm", "GET", f"projects/{project['id']}/").data
            resource = self.api(
                "pm",
                "POST",
                f"projects/{project['id']}/members/",
                {
                    "version": project["version"],
                    "user_id": self.user_id(employee_role),
                    "summary": "Çok unitli proje sayımı için sentetik kaynak talebi",
                },
                expected=(201,),
            ).data
            self.api(
                manager_role,
                "POST",
                f"participation-requests/{resource['id']}/decide/",
                {"version": resource["version"], "decision": "ACCEPT"},
            )
        after = self.api("director", "GET", "dashboard/").data
        after_units = {row["id"]: row for row in after["unit_summaries"]}
        for manager_role in ("unithead", "iamhead"):
            unit_id = self.users[manager_role]["primary_org_id"]
            self.assertEqual(
                after_units[unit_id]["project_contributions"],
                before_units[unit_id]["project_contributions"] + 1,
            )
            self.assertEqual(
                after_units[unit_id]["projects"], before_units[unit_id]["projects"]
            )
            self.assertTrue(after_units[unit_id]["manager_name"])
        pmo = self.users["pm_head"]["primary_org_id"]
        self.assertEqual(
            after_units[pmo]["projects"], before_units[pmo]["projects"] + 1
        )
        all_projects = records(self.api("director", "GET", "projects/").data)
        self.assertEqual(sum(row["id"] == project["id"] for row in all_projects), 1)

    def test_20_personal_work_and_formal_adoption(self):
        """K24: kişisel hedef SLA değildir; yönetici benimsemesinde resmî saat başlar."""
        work = self.create_work(personal=True, due_at="2026-12-31T20:59:59Z")
        self.assertFalse(work["formal"])
        self.assertFalse(work.get("sla"))
        original_created = work["created_at"]
        adopted = self.api(
            "unithead",
            "POST",
            f"work/{work['id']}/adopt/",
            {"version": work["version"], "priority": "CRITICAL"},
        ).data
        self.assertTrue(adopted["formal"])
        self.assertEqual(adopted["created_at"], original_created)
        sla = adopted["sla"]
        start = dt.datetime.fromisoformat(sla["started_at"])
        due = dt.datetime.fromisoformat(sla["original_due_at"])
        self.assertEqual(due - start, dt.timedelta(hours=24))
        self.api(
            "employee",
            "PATCH",
            f"work/{work['id']}/",
            {"version": adopted["version"], "formal": False},
            expected=(400, 403),
        )
        unchanged = self.get_work("employee", work["id"])
        self.assertTrue(unchanged["formal"])
        self.assertEqual(unchanged["sla"]["started_at"], sla["started_at"])

    def test_21_formal_completion_requires_independent_acceptance(self):
        """K27: tamamlanma bildirimi SLA'yı durdurmaz; yönetici kabulü durdurur."""
        work = self.create_work(
            "unithead", assignee_id=self.user_id("employee"), priority="HIGH"
        )
        self.assertTrue(work["formal"])
        start = work["sla"]["started_at"]
        original_due = work["sla"]["original_due_at"]
        verifying = self.api(
            "employee",
            "POST",
            f"work/{work['id']}/status/",
            {
                "version": work["version"],
                "status": "COMPLETED",
                "result": "Sentetik çıktı tamamlandı",
            },
        ).data
        self.assertEqual(verifying["status"], "VERIFYING")
        self.assertIsNone(verifying["sla"]["stopped_at"])
        self.api(
            "employee",
            "POST",
            f"work/{work['id']}/accept/",
            {"version": verifying["version"]},
            expected=(403,),
        )
        completed = self.api(
            "unithead",
            "POST",
            f"work/{work['id']}/accept/",
            {"version": verifying["version"]},
        ).data
        self.assertEqual(completed["status"], "COMPLETED")
        self.assertIsNotNone(completed["sla"]["stopped_at"])
        reopened = self.api(
            "unithead",
            "POST",
            f"work/{work['id']}/status/",
            {
                "version": completed["version"],
                "status": "OPEN",
                "reason": "Ek doğrulama gerekiyor",
            },
        ).data
        self.assertEqual(reopened["sla"]["started_at"], start)
        self.assertEqual(reopened["sla"]["original_due_at"], original_due)
        self.assertIsNone(reopened["sla"]["stopped_at"])

    def test_22_personal_work_completes_without_manager_acceptance(self):
        """K27: çalışanın kişisel işi doğrudan tamamlanır."""
        work = self.create_work(personal=True)
        done = self.api(
            "employee",
            "POST",
            f"work/{work['id']}/status/",
            {
                "version": work["version"],
                "status": "COMPLETED",
                "result": "Kişisel çıktı",
            },
        ).data
        self.assertEqual(done["status"], "COMPLETED")
        self.assertFalse(done.get("sla"))

    def test_23_unit_scope_and_private_parent(self):
        """K19/K22: alt iş üst sorumluyu değiştirmez; çalışan üst özel metni okuyamaz."""
        marker = self.unique("direktör özel taahhüdü")
        parent = self.create_work(
            "director",
            assignee_id=self.user_id("unithead"),
            title=marker,
            kind="COMMITMENT",
            expected_outcome="Yönetim çıktısı",
        )
        middle = self.create_work(
            "unithead",
            assignee_id=self.user_id("teammanager"),
            parent_id=parent["id"],
            shared_parent_summary="Paylaşılabilir hedef",
        )
        child = self.create_work(
            "teammanager",
            assignee_id=self.user_id("employee"),
            parent_id=middle["id"],
            shared_parent_summary="Sadece verilen hedef",
        )
        self.assertEqual(parent["assigned_to_id"], self.user_id("unithead"))
        current_parent = self.get_work("director", parent["id"])
        self.assertEqual(current_parent["assigned_to_id"], self.user_id("unithead"))
        self.api("employee", "GET", f"work/{parent['id']}/", expected=(403, 404))
        self.assertNotIn(
            marker,
            json.dumps(self.get_work("employee", child["id"]), ensure_ascii=False),
        )
        self.api(
            "unithead",
            "POST",
            f"work/{parent['id']}/status/",
            {
                "version": current_parent["version"],
                "status": "COMPLETED",
                "result": "Erken tamamlanma",
            },
            expected=(400,),
        )
        self.assertEqual(self.get_work("director", parent["id"])["status"], "OPEN")

    def test_24_cross_unit_reassignment_denied_and_sla_not_reset(self):
        """K14/K25: unit yöneticisi kardeş unit çalışanına atayamaz; reddetme kaydı değiştirmez."""
        work = self.create_work(
            "unithead", assignee_id=self.user_id("employee"), priority="CRITICAL"
        )
        self.api(
            "unithead",
            "POST",
            f"work/{work['id']}/assign/",
            {"version": work["version"], "assignee_id": self.user_id("iamemployee")},
            expected=(403,),
        )
        after = self.get_work("employee", work["id"])
        self.assertEqual(after["assigned_to_id"], work["assigned_to_id"])
        self.assertEqual(after["version"], work["version"])
        self.assertEqual(after["sla"]["started_at"], work["sla"]["started_at"])
        self.assertEqual(
            after["sla"]["original_due_at"], work["sla"]["original_due_at"]
        )
        self.api("iamemployee", "GET", f"work/{work['id']}/", expected=(403, 404))

    def test_25_rejected_creation_is_atomic(self):
        """K16: doğrulaması reddedilen geçersiz iş kaydı kısmen veritabanına düşmez."""
        title = self.unique("atomik invalid kind")
        self.api(
            "employee",
            "POST",
            "work/",
            {"title": title, "kind": "INVALID_KIND"},
            expected=(400,),
        )
        found = records(
            self.api(
                "employee", "GET", "work/?search=" + urllib.parse.quote(title)
            ).data
        )
        self.assertEqual(found, [], "4xx dönen oluşturma isteği geride iş bıraktı")

    def test_26_idempotency_deduplicates_and_does_not_skip_csrf(self):
        """K16: aynı istek tek iş/bildirim yaratır; replay auth/CSRF'yi atlayamaz."""
        key = str(uuid.uuid4())
        title = self.unique("tek mantıksal atama")
        payload = {
            "title": title,
            "assignee_id": self.user_id("employee"),
            "priority": "HIGH",
        }
        first = self.api(
            "unithead",
            "POST",
            "work/",
            payload,
            expected=(201,),
            headers={"X-Request-ID": key},
        ).data
        second = self.api(
            "unithead",
            "POST",
            "work/",
            payload,
            expected=(200, 201),
            headers={"X-Request-ID": key},
        ).data
        self.assertEqual(first["id"], second["id"])
        self.api(
            "unithead",
            "POST",
            "work/",
            payload,
            expected=(403,),
            csrf=False,
            headers={"X-Request-ID": key},
        )
        self.api(
            "unithead",
            "POST",
            "work/",
            {**payload, "title": title + " changed"},
            expected=(409,),
            headers={"X-Request-ID": key},
        )
        found = records(
            self.api(
                "unithead", "GET", "work/?search=" + urllib.parse.quote(title)
            ).data
        )
        self.assertEqual([row["id"] for row in found], [first["id"]])
        notifications = records(self.api("employee", "GET", "notifications/").data)
        matches = [row for row in notifications if row["resource_id"] == first["id"]]
        self.assertEqual(len(matches), 1)

    def test_27_contribution_authorship_is_server_owned(self):
        """K06: istemcinin yazar alanı geçmişi başka kullanıcı adına yazamaz."""
        work = self.create_work(personal=True)
        changed = self.api(
            "employee",
            "POST",
            f"work/{work['id']}/progress/",
            {
                "version": work["version"],
                "done": "Sentetik çalışma katkısı",
                "next_step": "Kontrol",
                "author_id": self.user_id("director"),
            },
            expected=(200, 400),
        ).data
        if "contributions" in changed:
            self.assertEqual(len(changed["contributions"]), 1)
            self.assertEqual(
                changed["contributions"][0]["author"]["id"], self.user_id("employee")
            )
        self.api(
            "iamhead",
            "GET",
            f"people/{self.user_id('employee')}/contributions/",
            expected=(403, 404),
        )

    def test_28_sla_reassignment_adjustment_and_self_extension(self):
        """K25/K37: resmî saat devirde sıfırlanmaz; ilk tarih korunur, kendi uzatması reddedilir."""
        work = self.create_work(
            "director", assignee_id=self.user_id("unithead"), priority="CRITICAL"
        )
        later = (dt.datetime.now(dt.UTC) + dt.timedelta(days=3)).isoformat()
        self.api(
            "unithead",
            "POST",
            f"work/{work['id']}/sla-adjust/",
            {
                "version": work["version"],
                "due_at": later,
                "reason": "Kendi uzatması engeli",
            },
            expected=(403,),
        )
        adjusted = self.api(
            "director",
            "POST",
            f"work/{work['id']}/sla-adjust/",
            {
                "version": work["version"],
                "due_at": later,
                "reason": "Bağımsız planlama kararı",
            },
        ).data
        self.assertEqual(
            adjusted["sla"]["original_due_at"], work["sla"]["original_due_at"]
        )
        self.assertEqual(adjusted["sla"]["started_at"], work["sla"]["started_at"])
        self.assertNotEqual(
            adjusted["sla"]["current_due_at"], work["sla"]["current_due_at"]
        )
        reassigned = self.api(
            "unithead",
            "POST",
            f"work/{work['id']}/assign/",
            {
                "version": adjusted["version"],
                "assignee_id": self.user_id("teammanager"),
            },
        ).data
        self.assertEqual(reassigned["sla"]["started_at"], work["sla"]["started_at"])
        self.assertEqual(
            reassigned["sla"]["original_due_at"], work["sla"]["original_due_at"]
        )
        self.assertEqual(
            reassigned["sla"]["current_due_at"], adjusted["sla"]["current_due_at"]
        )

    def test_29_contribution_revision_preserves_original_author(self):
        """K06: katkı düzeltmesi yeni sürümdür; eski yazar/ekip kaydı silinmez."""
        work = self.create_work(personal=True)
        progressed = self.api(
            "employee",
            "POST",
            f"work/{work['id']}/progress/",
            {
                "version": work["version"],
                "done": "İlk sentetik katkı",
                "next_step": "Sonraki adım",
            },
        ).data
        entry = progressed["contributions"][0]
        revised = self.api(
            "employee",
            "PATCH",
            f"contributions/{entry['id']}/",
            {
                "version": entry["version"],
                "done": "Düzeltilmiş sentetik katkı",
                "next_step": "Yeni sonraki adım",
            },
        ).data
        self.assertEqual(revised["previous_id"], entry["id"])
        self.assertEqual(revised["author"]["id"], entry["author"]["id"])
        self.assertEqual(revised["author_org_name"], entry["author_org_name"])
        current = self.get_work("employee", work["id"])
        contributions = {row["id"]: row for row in current["contributions"]}
        self.assertEqual(contributions[entry["id"]]["done"], "İlk sentetik katkı")
        self.assertEqual(
            contributions[revised["id"]]["done"], "Düzeltilmiş sentetik katkı"
        )
        self.api(
            "unithead",
            "PATCH",
            f"contributions/{entry['id']}/",
            {
                "version": entry["version"],
                "done": "Yönetici başkasının katkısını yazamaz",
            },
            expected=(403, 409),
        )

    def test_30_case_roles_notice_and_independent_verification(self):
        """K08: UH vakası SLA başlatır; ihbar resmî vaka değildir; kendi kapanışı doğrulanamaz."""
        for role in ("employee", "teammanager"):
            self.api(
                role,
                "POST",
                "cases/",
                {"title": self.unique("yetkisiz vaka")},
                expected=(403,),
            )
        notice = self.api(
            "employee",
            "POST",
            "case-notices/",
            {
                "title": self.unique("vaka bildirimi"),
                "description": "Sentetik ihbar, müdahale kanalı yerine geçmez",
            },
            expected=(201,),
        ).data
        self.assertEqual(notice["status"], "PENDING")
        self.assertFalse(notice.get("case_id"))
        case = self.api(
            "unithead",
            "POST",
            "cases/",
            {
                "title": self.unique("kritik vaka"),
                "description": "Sentetik vaka",
                "priority": "CRITICAL",
                "coordinator_id": self.user_id("unithead"),
            },
            expected=(201,),
        ).data
        due = dt.datetime.fromisoformat(case["sla"]["original_due_at"])
        start = dt.datetime.fromisoformat(case["sla"]["started_at"])
        self.assertEqual(due - start, dt.timedelta(hours=24))
        action = self.api(
            "unithead",
            "POST",
            f"cases/{case['id']}/actions/",
            {
                "version": case["version"],
                "assignee_id": self.user_id("unithead"),
                "title": self.unique("zorunlu vaka aksiyonu"),
            },
            expected=(201,),
        ).data
        current = self.api("unithead", "GET", f"cases/{case['id']}/").data
        self.api(
            "unithead",
            "POST",
            f"cases/{case['id']}/request-close/",
            {
                "version": current["version"],
                "summary": "Henüz kapatılamaz",
                "evidence": "Sentetik kanıt",
            },
            expected=(400,),
        )
        self.api(
            "unithead",
            "POST",
            f"work/{action['id']}/status/?all_contexts=true",
            {
                "version": action["version"],
                "status": "COMPLETED",
                "result": "Aksiyon tamamlandı",
            },
        )
        current = self.api("unithead", "GET", f"cases/{case['id']}/").data
        verifying = self.api(
            "unithead",
            "POST",
            f"cases/{case['id']}/request-close/",
            {
                "version": current["version"],
                "summary": "Aksiyonlar tamamlandı",
                "evidence": "Kontrollü kanıt bağlantısı",
            },
        ).data
        self.assertEqual(verifying["status"], "VERIFYING")
        self.assertIsNone(verifying["sla"]["stopped_at"])
        self.api(
            "unithead",
            "POST",
            f"cases/{case['id']}/verify-close/",
            {"version": verifying["version"], "evidence": "Kendi doğrulaması"},
            expected=(403,),
        )
        closed = self.api(
            "director",
            "POST",
            f"cases/{case['id']}/verify-close/",
            {
                "version": verifying["version"],
                "evidence": "Bağımsız yönetim doğrulaması",
            },
        ).data
        self.assertEqual(closed["status"], "CLOSED")
        self.assertIsNotNone(closed["sla"]["stopped_at"])
        self.api("iamemployee", "GET", f"cases/{case['id']}/", expected=(403, 404))

    def test_40_announcement_targeting(self):
        """K09: seçilen ekipteki anons kardeş uniti hedeflemez."""
        announcement = self.api(
            "unithead",
            "POST",
            "announcements/",
            {
                "title": self.unique("Hedef ekip anonsu"),
                "body": "Yalnız hedef ekip için sentetik bilgilendirme",
                "all_cs": False,
                "audience_org_ids": [self.users["employee"]["primary_org_id"]],
            },
            expected=(201,),
        ).data
        self.api(
            "employee",
            "POST",
            f"announcements/{announcement['id']}/publish/",
            {"version": announcement["version"]},
            expected=(403, 404),
        )
        published = self.api(
            "unithead",
            "POST",
            f"announcements/{announcement['id']}/publish/",
            {"version": announcement["version"]},
        ).data
        self.assertEqual(published["status"], "PUBLISHED")
        self.api("employee", "GET", f"announcements/{announcement['id']}/")
        self.api(
            "iamemployee",
            "GET",
            f"announcements/{announcement['id']}/",
            expected=(403, 404),
        )

    def test_41_poll_rsvp_and_attendance_are_distinct(self):
        """K10/K11: tek etkin oy; oy değişimi, RSVP ve gerçekleşen katılım birbirini ezmez."""
        event = self.api(
            "unithead",
            "POST",
            "events/",
            {
                "title": self.unique("bilgi paylaşımı"),
                "description": "Sentetik etkinlik",
                "invitee_ids": [self.user_id("employee"), self.user_id("teammanager")],
                "starts_at": (
                    dt.datetime.now(dt.UTC) + dt.timedelta(days=2)
                ).isoformat(),
            },
            expected=(201,),
        ).data
        poll = self.api(
            "unithead",
            "POST",
            f"events/{event['id']}/poll/",
            {
                "version": event["version"],
                "question": "Hangi konu?",
                "options": ["IAM", "Vaka yönetimi"],
                "max_choices": 1,
                "closes_at": (
                    dt.datetime.now(dt.UTC) + dt.timedelta(days=1)
                ).isoformat(),
            },
            expected=(201,),
        ).data
        first, second = (option["id"] for option in poll["options"])
        payload = {"poll_id": poll["id"], "choices": [first]}
        self.api("employee", "POST", f"events/{event['id']}/poll-response/", payload)
        duplicate = self.api(
            "employee", "POST", f"events/{event['id']}/poll-response/", payload
        ).data
        self.assertEqual(duplicate["result"]["responded"], 1)
        self.assertEqual(duplicate["result"]["eligible"], 2)
        self.assertEqual(duplicate["result"]["unanswered"], 1)
        changed = self.api(
            "employee",
            "POST",
            f"events/{event['id']}/poll-response/",
            {"poll_id": poll["id"], "choices": [second]},
        ).data
        self.assertEqual(changed["result"]["responded"], 1)
        self.assertEqual(changed["result"]["options"][first], 0)
        self.assertEqual(changed["result"]["options"][second], 1)
        self.api(
            "employee",
            "POST",
            f"events/{event['id']}/poll-response/",
            {"poll_id": poll["id"], "choices": [first, second]},
            expected=(400,),
        )
        self.api(
            "iamemployee",
            "POST",
            f"events/{event['id']}/poll-response/",
            payload,
            expected=(403, 404),
        )
        rsvp = self.api(
            "employee", "POST", f"events/{event['id']}/rsvp/", {"answer": "NO"}
        ).data
        self.assertEqual(rsvp["rsvp"], "NO")
        self.assertEqual(rsvp["counts"]["attended"], 0)
        self.assertEqual(rsvp["polls"][0]["result"]["responded"], 1)
        current = self.api("unithead", "GET", f"events/{event['id']}/").data
        attendance = self.api(
            "unithead",
            "POST",
            f"events/{event['id']}/attendance/",
            {
                "version": current["version"],
                "user_id": self.user_id("employee"),
                "present": True,
            },
        ).data
        self.assertEqual(attendance["counts"]["attended"], 1)
        mine = self.api("employee", "GET", f"events/{event['id']}/").data
        self.assertEqual(mine["rsvp"], "NO")
        self.assertEqual(mine["polls"][0]["my_choices"], [second])

    def test_42_community_public_card_keeps_source_private(self):
        """K28/K29: temiz paylaşım kaynağı açmaz; ilgi göstermek iş veya üyelik yaratmaz."""
        case = self.api(
            "unithead",
            "POST",
            "cases/",
            {
                "title": self.unique("özel operasyon vakası"),
                "description": "Bu metin paylaşım kartına kopyalanmamalı",
                "priority": "NORMAL",
            },
            expected=(201,),
        ).data
        card = self.api(
            "unithead",
            "POST",
            "community/",
            {
                "title": self.unique("paylaşılabilir öğrenim"),
                "body": "Genel öğrenim: sorumluyu erken netleştirmek ekipler arası koordinasyonu kolaylaştırır.",
                "kind": "LESSON",
                "all_cs": True,
                "source_type": "case",
                "source_id": case["id"],
            },
            expected=(201,),
        ).data
        card = self.api(
            "unithead",
            "POST",
            f"community/{card['id']}/publish/",
            {"version": card["version"]},
        ).data
        public = self.api("iamemployee", "GET", f"community/{card['id']}/").data
        self.assertFalse(public["source_accessible"])
        self.assertIsNone(public["source_id"])
        self.assertIsNone(public["source_type"])
        self.assertNotIn(case["title"], json.dumps(public, ensure_ascii=False))
        self.api("iamemployee", "GET", f"cases/{case['id']}/", expected=(403, 404))
        before = self.api(
            "iamemployee", "GET", "work/?mine=true&all_contexts=true"
        ).data["count"]
        interested = self.api(
            "iamemployee",
            "POST",
            f"community/{card['id']}/interest/",
            {"interested": True},
        ).data
        repeated = self.api(
            "iamemployee",
            "POST",
            f"community/{card['id']}/interest/",
            {"interested": True},
        ).data
        self.assertEqual(interested["interest_count"], repeated["interest_count"])
        self.assertTrue(repeated["interested"])
        after = self.api(
            "iamemployee", "GET", "work/?mine=true&all_contexts=true"
        ).data["count"]
        self.assertEqual(after, before)
        self.api(
            "unithead",
            "POST",
            f"community/{card['id']}/withdraw/",
            {"version": card["version"]},
        )
        self.api("iamemployee", "GET", f"community/{card['id']}/", expected=(403, 404))

    def test_43_credential_claim_verification_and_scope(self):
        """K34: çalışan beyanı doğrulanmış sayılmaz; önem yetkisi yöneticiye aittir."""
        credential = self.api(
            "employee",
            "POST",
            "credentials/",
            {
                "name": self.unique("yetkinlik"),
                "issuer": "Sentetik Test Kurumu",
                "no_expiry": True,
            },
            expected=(201,),
        ).data
        self.assertEqual(credential["verification_status"], "DECLARED")
        self.assertFalse(credential["important"])
        self.assertTrue(credential["no_expiry"])
        employee_view = self.api(
            "employee", "GET", f"credentials/{credential['id']}/"
        ).data
        manager_view = self.api(
            "unithead", "GET", f"credentials/{credential['id']}/"
        ).data
        self.assertFalse(employee_view["permissions"]["manage"])
        self.assertTrue(manager_view["permissions"]["manage"])
        self.api(
            "employee",
            "PATCH",
            f"credentials/{credential['id']}/",
            {
                "version": credential["version"],
                "verification_status": "VERIFIED",
                "important": True,
            },
            expected=(403,),
        )
        verified = self.api(
            "unithead",
            "PATCH",
            f"credentials/{credential['id']}/",
            {
                "version": credential["version"],
                "verification_status": "VERIFIED",
                "important": True,
            },
        ).data
        self.assertEqual(verified["verification_status"], "VERIFIED")
        self.assertTrue(verified["important"])
        self.api(
            "iamhead", "GET", f"credentials/{credential['id']}/", expected=(403, 404)
        )
        self.api(
            "employee",
            "POST",
            "credentials/",
            {
                "name": self.unique("hatalı sertifika"),
                "issuer": "Sentetik Test Kurumu",
                "issued_on": "2026-11-18",
                "expires_on": "2025-11-18",
            },
            expected=(400,),
        )

    def test_44_closed_poll_rejects_late_response(self):
        """K10: kapanıştan sonra oy kabul edilmez ve payda/yanıt sayısı değişmez."""
        event = self.api(
            "unithead",
            "POST",
            "events/",
            {
                "title": self.unique("kapanış sınırı"),
                "invitee_ids": [self.user_id("employee")],
            },
            expected=(201,),
        ).data
        closes = dt.datetime.now(dt.UTC) + dt.timedelta(seconds=1.5)
        poll = self.api(
            "unithead",
            "POST",
            f"events/{event['id']}/poll/",
            {
                "version": event["version"],
                "question": "Kapanış kontrolü?",
                "options": ["Evet", "Hayır"],
                "closes_at": closes.isoformat(),
            },
            expected=(201,),
        ).data
        while dt.datetime.now(dt.UTC) <= closes + dt.timedelta(milliseconds=100):
            time.sleep(0.1)
        self.api(
            "employee",
            "POST",
            f"events/{event['id']}/poll-response/",
            {"poll_id": poll["id"], "choices": [poll["options"][0]["id"]]},
            expected=(400,),
        )
        after = self.api("employee", "GET", f"events/{event['id']}/").data
        self.assertEqual(after["polls"][0]["result"]["responded"], 0)
        self.assertEqual(after["polls"][0]["result"]["eligible"], 1)

    def test_45_search_filters_hidden_resources(self):
        """K14/K18: gerçek arama gizli proje/iş varlığını başlık veya id ile sızdırmaz."""
        project = self.create_project()
        work = self.create_work(personal=True)
        for role in ("iamemployee", "admin"):
            for item in (project, work):
                response = self.api(
                    role, "GET", "search/?q=" + urllib.parse.quote(item["title"])
                ).data
                self.assertNotIn(item["id"], json.dumps(response, ensure_ascii=False))
                self.assertNotIn(
                    item["title"], json.dumps(response, ensure_ascii=False)
                )
        own = self.api(
            "employee", "GET", "search/?q=" + urllib.parse.quote(work["title"])
        ).data
        self.assertIn(work["id"], {row["id"] for row in own["results"]})

    def test_46_project_card_separates_content_and_audience_approval(self):
        """K28: PM metni onaylar; kaynak erişimi edinmeden Unit Head hedef yayını onaylar."""
        project = self.approved_project()
        card = self.api(
            "employee",
            "POST",
            "community/",
            {
                "title": self.unique("proje öğrenimi"),
                "body": "Paylaşılabilir sentetik proje kazanımı.",
                "kind": "SUCCESS",
                "source_type": "project",
                "source_id": project["id"],
                "all_cs": True,
            },
            expected=(201,),
        ).data
        submitted = self.api(
            "employee",
            "POST",
            f"community/{card['id']}/submit/",
            {"version": card["version"]},
        ).data
        content = self.api(
            "pm",
            "POST",
            f"community/{card['id']}/approve-content/",
            {"version": submitted["version"]},
        ).data
        self.assertEqual(content["status"], "CONTENT_APPROVED")
        self.api(
            "pm",
            "POST",
            f"community/{card['id']}/publish/",
            {"version": content["version"]},
            expected=(403,),
        )
        published = self.api(
            "unithead",
            "POST",
            f"community/{card['id']}/publish/",
            {"version": content["version"]},
        ).data
        self.assertEqual(published["status"], "PUBLISHED")
        unrelated = self.api("iamemployee", "GET", f"community/{card['id']}/").data
        self.assertFalse(unrelated["source_accessible"])
        self.assertIsNone(unrelated["source_id"])
        self.api(
            "iamemployee", "GET", f"projects/{project['id']}/", expected=(403, 404)
        )

    def test_47_full_text_search_reads_body_and_preserves_scope(self):
        """K14/K18: gövde kelimeleri farklı sırada bulunur; gizli kayıt varlığı açılmaz."""
        token = "atlasgovde" + uuid.uuid4().hex[:12]
        work = self.create_work(
            personal=True,
            description=f"{token} için kurum içi karşılaştırmalı yönetişim deneyi.",
        )
        # Neither query word occurs in the title, and their order differs from the
        # source. A title-only or whole-query substring filter cannot pass this.
        query = urllib.parse.quote(f"karşılaştırmalı {token}")
        own = self.api("employee", "GET", f"search/?q={query}").data
        self.assertIn(work["id"], {row["id"] for row in own["results"]})
        for role in ("iamemployee", "admin"):
            hidden = self.api(role, "GET", f"search/?q={query}").data
            self.assertNotIn(work["id"], json.dumps(hidden, ensure_ascii=False))
            self.assertNotIn(token, json.dumps(hidden, ensure_ascii=False))

        prefix = urllib.parse.quote(work["title"][:-2])
        partial = self.api("employee", "GET", f"search/?q={prefix}").data
        self.assertIn(work["id"], {row["id"] for row in partial["results"]})
        empty = self.api("employee", "GET", "search/?q=").data
        self.assertEqual(empty["results"], [])

    def test_48_notification_read_is_recipient_scoped(self):
        """K14/K19: bildirim yalnız alıcısında okunur ve başka kişi okundu yapamaz."""
        work = self.create_work(
            "unithead", assignee_id=self.user_id("employee"), priority="HIGH"
        )
        rows = records(self.api("employee", "GET", "notifications/").data)
        matches = [row for row in rows if row["resource_id"] == work["id"]]
        self.assertEqual(len(matches), 1)
        notification = matches[0]
        self.assertIsNone(notification["read_at"])
        unread = records(
            self.api("employee", "GET", "notifications/?status=unread").data
        )
        read_rows = records(
            self.api("employee", "GET", "notifications/?status=read").data
        )
        self.assertIn(notification["id"], {row["id"] for row in unread})
        self.assertNotIn(notification["id"], {row["id"] for row in read_rows})
        for role in ("iamemployee", "admin"):
            self.api(
                role,
                "GET",
                f"notifications/{notification['id']}/",
                expected=(403, 404),
            )
            self.api(
                role,
                "POST",
                f"notifications/{notification['id']}/read/",
                {},
                expected=(403, 404),
            )
        unchanged = self.api(
            "employee", "GET", f"notifications/{notification['id']}/"
        ).data
        self.assertIsNone(unchanged["read_at"])
        read = self.api(
            "employee", "POST", f"notifications/{notification['id']}/read/", {}
        ).data
        self.assertTrue(read["read_at"])
        self.assertEqual(read["resource_id"], work["id"])
        reread = self.api(
            "employee", "GET", f"notifications/{notification['id']}/"
        ).data
        self.assertTrue(reread["read_at"])
        read_rows = records(
            self.api("employee", "GET", "notifications/?status=read").data
        )
        self.assertIn(notification["id"], {row["id"] for row in read_rows})
        unread = records(
            self.api("employee", "GET", "notifications/?status=unread").data
        )
        self.assertNotIn(notification["id"], {row["id"] for row in unread})
        reset = self.api(
            "employee",
            "POST",
            f"notifications/{notification['id']}/read/",
            {"read": False},
        ).data
        self.assertIsNone(reset["read_at"])

    def test_49_official_units_and_reference_people(self):
        """K01: yedi resmî unit; bilinen aktörler doğru kişi/ekip ilişkisini taşır."""
        dashboard = self.api("director", "GET", "dashboard/").data
        units = dashboard["unit_summaries"]
        self.assertEqual(len(units), 7)
        self.assertEqual(len({unit["id"] for unit in units}), 7)
        for unit in units:
            self.assertTrue(unit["manager_name"], "Her resmî unit yöneticisi görünmeli")
        expected_people = {
            "director": "Emin İslam Tatlı",
            "teammanager": "Emre Uzun",
            "employee": "Muhammed Eren Uygun",
        }
        for role, expected_name in expected_people.items():
            actual = " ".join(self.users[role]["display_name"].split()).casefold()
            self.assertEqual(actual, expected_name.casefold())
        self.assertEqual(
            self.users["employee"]["primary_org_id"],
            self.users["teammanager"]["primary_org_id"],
        )

    def test_50_report_star_sources_and_generation(self):
        """K30/K32: yıldızlı ve kritik adaylar kaynaklıdır; kalıcı job raporu tamamlar."""
        work = self.create_work(
            "unithead", assignee_id=self.user_id("employee"), priority="CRITICAL"
        )
        team_work = self.create_work("employee", personal=True, priority="NORMAL")
        today = dt.datetime.now(dt.timezone(dt.timedelta(hours=3))).date()
        monday = today - dt.timedelta(days=today.weekday())
        self.api(
            "unithead",
            "POST",
            "report-selections/",
            {
                "source_type": "work",
                "source_id": work["id"],
                "week_start": monday.isoformat(),
                "selected": True,
            },
            expected=(200, 201),
        )
        self.api(
            "employee",
            "POST",
            "report-selections/",
            {
                "source_type": "work",
                "source_id": team_work["id"],
                "week_start": monday.isoformat(),
                "selected": True,
            },
            expected=(200, 201),
        )
        report = self.api(
            "unithead",
            "POST",
            "reports/",
            {
                "title": self.unique("haftalık rapor"),
                "period_start": monday.isoformat(),
                "period_end": today.isoformat(),
            },
            expected=(201,),
        ).data
        source_ids = [str(source["id"]) for source in report["sources"]]
        self.assertIn(work["id"], source_ids)
        self.assertIn(
            team_work["id"],
            source_ids,
            "Ekip çalışanının yıldızı unit haftalık raporuna taşınmalı",
        )
        self.assertEqual(
            len(source_ids),
            len(set(source_ids)),
            "Yıldızlı kritik aday iki kez eklenmemeli",
        )
        for source in report["sources"]:
            self.assertIn("version", source)
            self.assertIn("type", source)
        queued = self.api(
            "unithead",
            "POST",
            f"reports/{report['id']}/generate/",
            {"version": report["version"]},
            expected=(202,),
        ).data
        self.assertEqual(queued["status"], "GENERATING")
        # Live AI may use the configured 180-second provider deadline. Allow
        # bounded worker/commit overhead instead of assuming a quick TLS fallback.
        deadline = time.monotonic() + 210
        current = queued
        while time.monotonic() < deadline:
            current = self.api("unithead", "GET", f"reports/{report['id']}/").data
            if (
                current["status"] in ("READY", "FAILED")
                or current.get("job_status") == "FAILED"
            ):
                break
            time.sleep(0.3)
        self.assertEqual(
            current["status"], "READY", "Rapor worker tarafından tamamlanmadı"
        )
        self.observations["report_50_generation_mode"] = current["generated_mode"]
        self.assertTrue(current["markdown"].strip())
        self.assertTrue(current["content_hash"])
        referenced = [
            source_id for source_id in source_ids if source_id in current["markdown"]
        ]
        self.observations["report_50_visible_source_references"] = len(referenced)
        self.observations["report_50_snapshot_sources"] = len(source_ids)
        self.assertEqual(
            set(referenced),
            set(source_ids),
            "Raporun kaynak dizini seçilmiş ve zorunlu snapshot kayıtlarını korumalı",
        )
        if current["generated_mode"] == "RULE_BASED":
            self.assertIn("kurallı", current["markdown"])
            self.assertIn("canlı AI çıktısı değildir", current["markdown"])
        self.api(
            "unithead",
            "POST",
            f"reports/{report['id']}/approve/",
            {"version": current["version"], "content_hash": "invalid-reviewed-hash"},
            expected=(409,),
        )
        approved = self.api(
            "unithead",
            "POST",
            f"reports/{report['id']}/approve/",
            {"version": current["version"], "content_hash": current["content_hash"]},
        ).data
        self.assertEqual(approved["status"], "APPROVED")
        rolled_up = self.api("director", "GET", f"reports/{report['id']}/").data
        self.assertEqual(rolled_up["id"], report["id"])
        self.assertEqual(rolled_up["status"], "APPROVED")
        self.api("iamhead", "GET", f"reports/{report['id']}/", expected=(403, 404))
        self.api(
            "employee",
            "POST",
            "reports/",
            {"period_start": monday.isoformat(), "period_end": today.isoformat()},
            expected=(403,),
        )

    def test_60_admin_boundaries_and_unconfigured_integrations(self):
        """K39: ayarlar teknik yetki ister; yapılandırılmamış bağlantı sahte başarı değildir."""
        for role in ("director", "unithead", "employee", "pm"):
            for path in ("admin/settings/", "admin/users/", "admin/ai/usage/"):
                self.api(role, "GET", path, expected=(403,))
        settings = self.api("admin", "GET", "admin/settings/").data
        self.assertIn("sections", settings)
        roles = self.api("admin", "GET", "admin/roles/").data
        self.assertIn("roles", roles)
        self.api(
            "admin",
            "PATCH",
            f"admin/users/{self.user_id('admin')}/",
            {
                "roles": [
                    {
                        "role": "DIRECTOR",
                        "org_node": self.users["admin"]["primary_org_id"],
                    }
                ]
            },
            expected=(403,),
        )
        self.api("admin", "GET", "admin/ai/usage/?from=not-a-date", expected=(400,))

    def test_61_external_jwt_is_read_only_scoped_and_revocable(self):
        """K33: dış JWT yazamaz, başka modül okuyamaz; iptal hemen etkilidir."""
        created = self.api(
            "admin",
            "POST",
            "api-clients/",
            {
                "name": self.unique("salt okunur test istemcisi"),
                "scopes": ["work:read"],
            },
            expected=(201,),
        ).data
        self.assertTrue(created.get("token"))
        bearer = ApiClient(CONFIG["base_url"])
        headers = {"Authorization": "Bearer " + created["token"]}
        read = bearer.request("GET", "work/", headers=headers)
        self.assertEqual(read.status, 200)
        self.assertEqual(
            records(read.data),
            [],
            "Teknik admin JWT'si iş verisini otomatik devralamaz",
        )
        self.assertEqual(
            bearer.request(
                "POST", "work/", {"title": "JWT yazamaz"}, headers=headers
            ).status,
            403,
        )
        self.assertEqual(bearer.request("GET", "cases/", headers=headers).status, 403)
        self.assertEqual(
            bearer.request("GET", "admin/settings/", headers=headers).status, 403
        )
        bad = {"Authorization": "Bearer " + created["token"] + "tampered"}
        self.assertEqual(bearer.request("GET", "work/", headers=bad).status, 401)
        self.api("admin", "POST", f"api-clients/{created['id']}/revoke/", {})
        self.assertEqual(bearer.request("GET", "work/", headers=headers).status, 401)

    def test_62_ldap_secret_masking_and_unconfigured_result(self):
        """K39: sır GET/audit'te görünmez; kapalı LDAP hazır görünmez veya lokale düşmez."""
        before = self.api("admin", "GET", "admin/settings/ldap/").data
        if before["config"].get("enabled") or before.get("secret_fields"):
            self.skipTest(
                "Gerçek LDAP yapılandırması veya mevcut sır sentetik test tarafından değiştirilmez"
            )
        marker = "qa-synthetic-bind-" + uuid.uuid4().hex
        try:
            changed = self.api(
                "admin",
                "PATCH",
                "admin/settings/ldap/",
                {
                    "expected_version": before["version"],
                    "config": {"enabled": False},
                    "secrets": {"bind_password": marker},
                },
            ).data
            self.assertGreater(changed["version"], before["version"])
            self.assertIn("bind_password", changed["secret_fields"])
            self.assertNotIn(marker, json.dumps(changed, ensure_ascii=False))
            reread = self.api("admin", "GET", "admin/settings/ldap/").data
            self.assertNotIn(marker, json.dumps(reread, ensure_ascii=False))
            self.api(
                "admin",
                "PATCH",
                "admin/settings/ldap/",
                {"expected_version": before["version"], "config": {"enabled": False}},
                expected=(400, 409),
            )
            tested = self.api(
                "admin", "POST", "admin/integrations/ldap/test/", {}, expected=(409,)
            ).data
            self.assertEqual(tested["status"], "unconfigured")
            after_test = self.api("admin", "GET", "admin/settings/ldap/").data
            self.assertFalse(after_test["ready"])
            audit = self.api("admin", "GET", "admin/audit/").data
            self.assertNotIn(marker, json.dumps(audit, ensure_ascii=False))
            isolated = ApiClient(CONFIG["base_url"])
            isolated.request("GET", "auth/csrf/")
            result = isolated.request(
                "POST",
                "auth/login/",
                {
                    "username": "employee",
                    "password": CONFIG["password"],
                    "method": "ldap",
                },
            )
            self.assertIn(result.status, (400, 401, 409))
            self.assertIn(isolated.request("GET", "dashboard/").status, (401, 403))
        finally:
            current = self.api("admin", "GET", "admin/settings/ldap/").data
            self.api(
                "admin",
                "PATCH",
                "admin/settings/ldap/",
                {
                    "expected_version": current["version"],
                    "config": before["config"],
                    "secrets": {"bind_password": None},
                },
            )

    def test_63_deactivated_account_loses_existing_session(self):
        """K13: pasifleşme mevcut cookie oturumunu sonraki istekte geçersiz kılar."""
        username = "qa_" + uuid.uuid4().hex[:14]
        user = self.api(
            "admin",
            "POST",
            "admin/users/",
            {
                "username": username,
                "display_name": "Sentetik QA Oturum İptali",
                "password": CONFIG["password"],
                "identity_source": "local",
                "primary_org": self.users["employee"]["primary_org_id"],
            },
            expected=(201,),
        ).data
        isolated = ApiClient(CONFIG["base_url"])
        self.assertEqual(isolated.login(username, CONFIG["password"]).status, 200)
        self.assertEqual(isolated.request("GET", "dashboard/").status, 200)
        self.api("admin", "PATCH", f"admin/users/{user['id']}/", {"is_active": False})
        self.assertIn(isolated.request("GET", "dashboard/").status, (401, 403))
        self.assertIn(isolated.request("GET", "work/").status, (401, 403))

    def test_64_test_mode_is_disabled_in_development(self):
        """K15: geliştirme varsayılanında God Mode ve kullanıcı denemesi açılmaz."""
        state = self.api("admin", "GET", "test-mode/").data
        if state.get("available"):
            self.skipTest(
                "Test/demo God Mode kasıtlı açık; bu davranış backend ortam testlerinde ayrı doğrulanır"
            )
        self.assertFalse(state["god_mode"])
        self.api("admin", "POST", "test-mode/", {"mode": "god"}, expected=(403,))
        self.api(
            "admin",
            "POST",
            "test-mode/",
            {"mode": "simulate", "user_id": self.user_id("director")},
            expected=(403,),
        )
        self.api("employee", "GET", "test-mode/", expected=(403,))

    def test_66_directory_import_and_ai_profiles_require_admin(self):
        """K39: keşif/arama/aktarım ve AI profil yönetimi sıradan rollere kapalıdır."""
        fake_batch = str(uuid.uuid4())
        for role in ("employee", "teammanager", "unithead", "pm"):
            for method, route, payload in (
                ("POST", "admin/ldap/discover/", {}),
                ("POST", "admin/ldap/search/", {"kind": "users", "query": "qa"}),
                (
                    "POST",
                    "admin/ldap/import/",
                    {"batch_id": fake_batch, "entries": []},
                ),
                ("GET", "admin/ai/profiles/", None),
                ("POST", "admin/ai/profiles/", {"name": "Yetkisiz profil"}),
            ):
                with self.subTest(role=role, route=route):
                    self.api(role, method, route, payload, expected=(403,))
        # Import consumes an already staged batch. An invented batch must fail
        # without authenticating to LDAP or creating a local identity.
        self.api(
            "admin",
            "POST",
            "admin/ldap/import/",
            {
                "batch_id": fake_batch,
                "entries": [
                    {
                        "subject": "qa-nonexistent-directory-subject",
                        "org_node": self.users["employee"]["primary_org_id"],
                        "role": "EMPLOYEE",
                    }
                ],
            },
            expected=(404,),
        )

    def test_67_disabled_ai_profiles_are_isolated_and_masked(self):
        """K39: iki profil sürümü/sırrı ayrıdır; bağlantı/default değişmeden arşivlenir."""
        shared_before = self.api("admin", "GET", "admin/settings/ai/").data
        default_before = shared_before["config"].get("default_profile_id")
        markers = ["qa-profile-key-" + uuid.uuid4().hex for _ in range(2)]
        created = []
        try:
            for index, marker in enumerate(markers):
                profile = self.api(
                    "admin",
                    "POST",
                    "admin/ai/profiles/",
                    {
                        "name": self.unique(f"kapalı AI bağlantısı {index + 1}"),
                        "config": {
                            "enabled": False,
                            "provider": "openai-compatible",
                            "base_url": "https://qa-never-called.invalid/v1",
                        },
                        "secrets": {"api_key": marker},
                    },
                    expected=(201,),
                ).data
                created.append(profile)
                self.assertFalse(profile["config"]["enabled"])
                self.assertFalse(profile["is_default"])
                self.assertFalse(profile["ready"])
                self.assertIn("api_key", profile["secret_fields"])
                self.assertNotIn(marker, json.dumps(profile, ensure_ascii=False))
            self.assertNotEqual(created[0]["id"], created[1]["id"])
            first, second = created
            revised_name = self.unique("kapalı profil düzeltmesi")
            updated = self.api(
                "admin",
                "PATCH",
                f"admin/ai/profiles/{first['id']}/",
                {"expected_version": first["version"], "name": revised_name},
            ).data
            self.assertGreater(updated["version"], first["version"])
            untouched = self.api(
                "admin", "GET", f"admin/ai/profiles/{second['id']}/"
            ).data
            self.assertEqual(untouched["version"], second["version"])
            self.assertEqual(untouched["name"], second["name"])
            self.api(
                "admin",
                "PATCH",
                f"admin/ai/profiles/{first['id']}/",
                {"expected_version": first["version"], "name": "Eski sürüm yazamaz"},
                expected=(400, 409),
            )
            current = self.api("admin", "GET", f"admin/ai/profiles/{first['id']}/").data
            self.assertEqual(current["name"], revised_name)
            self.api(
                "admin",
                "PATCH",
                f"admin/ai/profiles/{first['id']}/",
                {
                    "expected_version": current["version"],
                    "config": {"model": "profile-must-not-override-shared-model"},
                },
                expected=(400,),
            )
            for suffix in ("", "test/", "default/"):
                self.api(
                    "employee",
                    "GET" if not suffix else "POST",
                    f"admin/ai/profiles/{first['id']}/{suffix}",
                    None if not suffix else {},
                    expected=(403,),
                )
            listed = self.api("admin", "GET", "admin/ai/profiles/").data
            audit = self.api("admin", "GET", "admin/audit/?action=ai.profile").data
            for marker in markers:
                self.assertNotIn(marker, json.dumps(listed, ensure_ascii=False))
                self.assertNotIn(marker, json.dumps(audit, ensure_ascii=False))
            shared_after = self.api("admin", "GET", "admin/settings/ai/").data
            self.assertEqual(
                shared_after["config"].get("default_profile_id"), default_before
            )
        finally:
            # These are disabled profiles created by this test. No live profile,
            # saved default, model setting or external connection is changed.
            for profile in created:
                archived = self.api(
                    "admin", "DELETE", f"admin/ai/profiles/{profile['id']}/"
                ).data
                self.assertFalse(archived["active"])

    def test_65_openapi_and_swagger_require_login(self):
        """K33: API belgesi erişimlidir; anonim oturum belgeyi okuyamaz."""
        anonymous = ApiClient(CONFIG["base_url"])
        for path in ("schema/", "docs/"):
            headers = {"Accept": "text/html" if path == "docs/" else "application/json"}
            self.assertIn(
                anonymous.request("GET", path, headers=headers).status, (401, 403)
            )
            response = self.api("admin", "GET", path, headers=headers)
            self.assertIn("Atlas", response.text)
            self.assertNotIn("Traceback", response.text)


class EvidenceResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.evidence = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.evidence.append({"test": test.id(), "status": "passed"})

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.evidence.append(
            {"test": test.id(), "status": "failed", "detail": str(err[1])}
        )

    def addError(self, test, err):
        super().addError(test, err)
        self.evidence.append(
            {"test": test.id(), "status": "error", "detail": str(err[1])}
        )

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.evidence.append({"test": test.id(), "status": "skipped", "detail": reason})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--password-env", default="ATLAS_DEMO_PASSWORD")
    parser.add_argument(
        "--env-file", default=str(Path(__file__).resolve().parents[1] / ".env")
    )
    parser.add_argument("--allow-mutations", action="store_true")
    parser.add_argument("--output", default="tests/artifacts/api-acceptance.json")
    parser.add_argument(
        "--test",
        action="append",
        dest="test_names",
        help="Yalnız belirtilen test metodunu çalıştırır; birden fazla verilebilir.",
    )
    args = parser.parse_args()
    if not args.allow_mutations:
        parser.error(
            "Sentetik ortamda yazma yapıldığını belirtmek için --allow-mutations gerekli"
        )
    password = os.environ.get(args.password_env)
    # Parse data only: no shell interpolation or arbitrary dotenv command execution.
    if not password and Path(args.env_file).is_file():
        for line in Path(args.env_file).read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            if key.strip() == args.password_env:
                value = value.strip()
                if len(value) > 1 and value[0] == value[-1] and value[0] in ('"', "'"):
                    value = value[1:-1]
                password = value
                break
    if not password:
        parser.error(f"{args.password_env} tanımlı olmalı; parola rapora yazılmaz")
    parsed = urllib.parse.urlparse(args.base_url)
    if parsed.scheme not in ("http", "https") or parsed.hostname not in (
        "localhost",
        "127.0.0.1",
        "::1",
    ):
        parser.error("Bu koşucu yalnız yerel sentetik ortam için yapılandırılmıştır")
    CONFIG.update(base_url=args.base_url.rstrip("/"), password=password)
    started = time.monotonic()
    if args.test_names:
        available = set(unittest.defaultTestLoader.getTestCaseNames(AtlasApiAcceptance))
        unknown = sorted(set(args.test_names) - available)
        if unknown:
            parser.error("Bilinmeyen test metodu: " + ", ".join(unknown))
        suite = unittest.TestSuite(
            AtlasApiAcceptance(name) for name in dict.fromkeys(args.test_names)
        )
    else:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(AtlasApiAcceptance)
    result = unittest.TextTestRunner(verbosity=2, resultclass=EvidenceResult).run(suite)
    evidence = {
        "application": "Atlas",
        "run_key": AtlasApiAcceptance.run_key,
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
        "external_integrations_verified": False,
        "observations": AtlasApiAcceptance.observations,
    }
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    return 0 if result.wasSuccessful() and result.testsRun else 1


if __name__ == "__main__":
    sys.exit(main())
