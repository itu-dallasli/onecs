import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { AIConnections } from "./Settings";

function profile(id: string, status: string, message: string) {
  return {
    id,
    name: `Test bağlantısı ${id}`,
    section: `ai_profile_${id}`,
    version: 2,
    active: true,
    is_default: false,
    config: { enabled: true, base_url: "https://model.example.test/v1" },
    ready: false,
    secret_fields: ["api_key"],
    latest_test: {
      status,
      message,
      checked_at: "2026-11-18T12:00:00Z",
      configuration_version: 2,
    },
  };
}

describe("AI connection diagnostics", () => {
  it("keeps each stored failure visible after the settings page is reopened", () => {
    const markup = renderToStaticMarkup(
      <AIConnections
        profiles={[
          profile("1", "failure", "TLS sertifikasının süresi dolmuş."),
          profile("2", "failure", "Model sağlayıcısı erişimi reddetti (403)."),
        ]}
        loading={false}
        error=""
        refresh={vi.fn()}
      />,
    );

    expect(markup).toContain("TLS sertifikasının süresi dolmuş.");
    expect(markup).toContain("Model sağlayıcısı erişimi reddetti (403).");
    expect(markup.match(/role="alert"/g)).toHaveLength(2);
    expect(markup).toContain("Test başarısız");
    expect(markup).not.toContain("Bağlantı doğrulandı");
    expect(markup).toContain(
      'disabled="" title="Önce bu bağlantıyı güncel model ayarlarıyla test edin."',
    );
  });

  it("distinguishes an unconfigured profile from a failed external request", () => {
    const markup = renderToStaticMarkup(
      <AIConnections
        profiles={[
          profile("1", "unconfigured", "Ortak model ayarı eksik."),
        ]}
        loading={false}
        error=""
        refresh={vi.fn()}
      />,
    );

    expect(markup).toContain("Yapılandırılmadı");
    expect(markup).toContain("Ortak model ayarı eksik.");
    expect(markup).toContain('role="status"');
    expect(markup).not.toContain("Başarısız / yapılandırılmadı");
    expect(markup).not.toContain('role="alert"');
  });
});
