# Atlas · Proje başvurusu ve PM yönetimi

Proje yönetimi PM kapsamındadır; personel tahsisini kabul eden Unit Head proje içeriğini yönetmiş olmaz.

- `POST /api/v1/projects/` girdi: `{title,description,expected_outcome?,appointment_id? | pm_id?,priority?,due_at?}`. Kaynak birim çalışanın üyeliğidir; kayıt `DRAFT` başlar ve kişiseldir.
- `POST /projects/{id}/submit/ {version}` değişmez `ProjectRevision` oluşturur ve `SUBMITTED` yapar. Onay atanmış PM hattındadır; çalışanın normal yöneticisine otomatik gönderilmez.
- `POST /projects/{id}/review/ {version,decision:APPROVE|REVISION|REJECT,note?}` kararı sırasıyla `PLANNED`, `REVISION`, `REJECTED` üretir. Red/düzeltme gerekçesi ve bağımsız gerçek karar verici zorunludur.
- Yönetim: atanmış PM, PM'nin bağlı Unit Head'i veya geçerli işlem kapsamındaki vekil. Direktörün görünürlüğü otomatik günlük yönetim/onay yetkisi değildir.
- Yayın hedefi kullanıcıları onaylı özet görür; PM/üyelerin ayrıntıları ve katkıları ayrıca korunur. Sonraki değişiklik taslağı özet okuyucusuna açılmaz.
- `POST /projects/{id}/members/ {version,user_id,summary}` kaynak talebi açar; hedef yönetici `/participation-requests/{id}/decide/ {version,decision:ACCEPT|REJECT,note?}` ile kararlaştırır. Kabul üyelik üretir, PM yetkisi vermez.
- `POST /projects/{id}/tasks/ {version,title,assignee_id,description?,due_at?}` yalnız yayınlı etkin projede kabul edilmiş üyeye `PROJECT_TASK` açar. Unit SLA'sı uygulanmaz.
- `POST /projects/{id}/progress/ {version,done,next_step?,blocker?,progress?}` katkı tutar ve `IN_PROGRESS` yapar. Yüzdeyi yalnız proje yöneticisi belirler; yüzde beyan niteliğindedir.
- `POST /projects/{id}/propose-change/ {version,reason,...}` ana kapsam/kitlenin yeni sürümünü karara gönderir; eski yayın ve proje durumu korunur. `/review/` bağımsız kararla yeni sürümü yayımlar; `/revisions/` yetkili geçmişidir.
- `/authorities/` GET/POST süreli ve sınırlı devir; `/authority-revoke/` iptal; `/transfer/ {version,appointment_id,reason}` kontrollü PM değişimidir. Transfer eski devirleri kapatır ve bekleyen başvuruyu güncel PM'ye yönlendirir.
- `POST /projects/{id}/close/ {version,summary}` zorunlu açık teslim yoksa PM tarafından `COMPLETED` yapar; yüzde 100 olur. Otomatik bağımsız proje kapanış onayı bu sürümde bulunmaz.
- Kritik mutasyon, audit ve gereken uygulama içi bildirim/e-posta outbox'ı aynı transaction içindedir. `X-Request-ID` tekrarları tek mantıksal işlemdir; SMTP başarısızlığı proje kaydını geri almaz.
- Hatalar: eksik/geçersiz durum 400, yetki/kendi onayı 403/404, eski sürüm veya bekleyen çakışan değişiklik 409. Pasif PM'nin başvurusu yetkili yeniden yönlendirme görünümünden devredilebilir.
- **Henüz uygulanmayan:** direktör için yapılandırılabilir doğrudan proje başlatma; küçük tarih değişimi için ayrıntılı tolerans politikası; ağırlıklı kilometre taşı, aylık snapshot ve PPTX. Yayınlı ana kapsam doğrudan PATCH ile değiştirilemez.

Kod: [API](../../backend/core/views.py), [yetki](../../backend/core/policy.py), [kalıcı servisler](../../backend/core/services.py).
Testler: [test_project_case_api.py](../../backend/core/tests/test_project_case_api.py), [test_latest_flows.py](../../backend/core/tests/test_latest_flows.py), [test_continuity.py](../../backend/core/tests/test_continuity.py), [test_session_security.py](../../backend/core/tests/test_session_security.py). Sonuç: [QA raporu](../QA_REPORT.md).
