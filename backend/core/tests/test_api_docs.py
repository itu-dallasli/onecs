"""Both browser HTML and machine schema stay authenticated and renderable."""

from core.tests.base import AtlasTestCase


class APIDocumentationTests(AtlasTestCase):
    def test_anonymous_html_docs_are_denied_without_template_failure(self):
        response = self.client.get("/api/v1/docs/", HTTP_ACCEPT="text/html")
        self.assertIn(response.status_code, (401, 403))

    def test_authenticated_swagger_html_is_rendered(self):
        response = self.as_user(self.admin).get(
            "/api/v1/docs/", HTTP_ACCEPT="text/html"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertContains(response, "SwaggerUIBundle")
        self.assertContains(response, "/api/v1/schema/")
