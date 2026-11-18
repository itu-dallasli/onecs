# onecs · Vaka koordinasyonu ve kapanış doğrulaması

Tek resmî vaka farklı ekiplerin kabul edilmiş aksiyonlarını toplar; ham teknik kanıtın yerine paylaşılabilir koordinasyon özeti tutulur.

- `POST /api/v1/cases/` girdi: `{title,description?,owner_org_id?,coordinator_id?,priority?,kind?}`. Türler `SECURITY_INCIDENT`, `VULNERABILITY`, `OPERATIONAL` olur.
- Unit Head/direktör kendi kapsamına resmî vaka açar; Team Manager ancak kapsamlı `case.create` devriyle açabilir. Koordinatör etkin ve atayanın yönetim kapsamında olmalıdır.
- Çalışan `POST /case-notices/ {title,description}` ile ihbar açar; durum `PENDING`dir, resmî SLA başlamaz. Acil müdahale mevcut kurum kanalında sürdürülür.
- Yetkili yönetici `/case-notices/{id}/convert/ {version,priority?,kind?,coordinator_id?}` ile `CONVERTED` ve bağlantılı vaka/SLA oluşturur; `/dismiss/ {version,reason}` gerekçeli `DISMISSED` yapar.
- Resmî vaka `NEW` başlar. `/status/ {version,status:ASSESSING|IN_PROGRESS|CANCELLED,reason?}` kontrollü durum değiştirir; `/progress/ {version,done,next_step?,blocker?}` katkı kaydeder ve ilk aşamaları `IN_PROGRESS` yapar.
- `/members/ {version,user_id,summary}` kaynak talebi açar. `/participation-requests/{id}/decide/` hedef unitin kabulüyle üyelik verir; bekleyen talep doğrudan atama değildir.
- `/actions/ {version,title,assignee_id,description?,expected_outcome?,priority?,due_at?,mandatory?}` yalnız kabul edilmiş üyeye/koordinatöre `CASE_ACTION` açar. Alt aksiyona ayrı varsayılan unit SLA'sı kopyalanmaz.
- Vaka açılışı, koordinatör/üyelik, SLA, audit ve atama bildirim outbox'ı aynı transaction'dır. Yeniden deneme `X-Request-ID` ile tek vaka/posta üretir.
- İç hedefler kritik 24 saat, yüksek 7 takvim günü, normal 1 takvim ayıdır; resmî oluşturma commit'inde başlar. Bunlar ilk müdahaleyi bekletmek için kullanılan endüstri/yasal süre iddiası değildir.
- `/request-close/ {version,summary,evidence}` bütün zorunlu aksiyonlar kapalıysa `VERIFYING` yapar. Doğrulama beklerken SLA çalışır.
- `/verify-close/ {version,evidence}` kapsamlı Unit Head/direktör veya açık doğrulama yetkilisiyle `CLOSED` yapar ve SLA'yı durdurur. Kapanış isteyen gerçek kişi kendini doğrulayamaz; sıradan TM rolü yeterli değildir.
- `CLOSED`/`CANCELLED` vaka yetkili ve gerekçeli `/status/` işlemiyle yeniden açılabilir. Aynı SLA başlangıcı/hedefi, eski kapanış audit'i ve gerçekleşmiş ihlal korunur.
- `/sla-adjust/ {version,due_at,reason}` bağımsız yetkili karar ister; mevcut ihlal önce kaydedilir. Worker eski sürüm, kapanmış hedef ve artık geçerli olmayan uyarıları iptal eder.
- Hatalar: geçersiz tür/durum/eksik kanıt/açık zorunlu aksiyon 400; kapsam veya kendi doğrulaması 403/404; eski sürüm/istek çakışması 409. E-posta hatası vaka kaydını geri almaz; belirsiz teslim kontrollü uzlaştırılır.
- **Henüz uygulanmayan:** SIEM/SOAR veri adaptörü, otomatik ilk yanıt/containment hedefleri, teknik risk kabul süreci ve aksiyonu başka kayda devretme ekranı. Açık zorunlu aksiyon bu eksikler nedeniyle sessizce kapatılmaz.

Kod: [Case/Notice API](../../backend/core/views.py), [vaka policy](../../backend/core/policy.py), [SLA/katkı servisi](../../backend/core/services.py), [outbox worker](../../backend/core/worker.py).
Testler: [test_project_case_api.py](../../backend/core/tests/test_project_case_api.py), [test_latest_flows.py](../../backend/core/tests/test_latest_flows.py), [test_sla.py](../../backend/core/tests/test_sla.py), [test_worker.py](../../backend/core/tests/test_worker.py). Koşu kapsamı: [QA raporu](../QA_REPORT.md).
