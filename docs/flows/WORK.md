# onecs · Unit işleri, alt işler ve taahhütler

Unit işleri organizasyon kapsamıyla; proje görevleri PM, vaka aksiyonları vaka yetkisiyle yönetilir. Birleşik görev listesi bu hakları birleştirmez.

- `GET /api/v1/work/` varsayılan `UNIT_WORK` listesidir; `?mine=true&all_contexts=true` kişinin yetkili bütün bağlamlarını toplar.
- `POST /work/` girdi: `{title,assignee_id?,description?,expected_outcome?,priority?,personal?,due_at?,parent_id?,mandatory?,shared_parent_summary?,kind:TASK|COMMITMENT?}`. Taahhütte beklenen çıktı gerekir.
- Direktör kendi alt kapsamına, Unit Head unitine, Team Manager ekibine atar; çalışan kendisine kişisel iş açabilir. PM rolü tek başına unit atama hakkı değildir.
- Yönetici resmî atamasında SLA ilk commit anında başlar. Kişisel işte yalnız isteğe bağlı hedef tarih vardır; `/adopt/ {version,priority?}` yönetici teyidiyle yeni SLA başlatır, geçmişe ihlal yazmaz.
- Alt iş aynı bağlamda kalır; üst sorumluyu değiştirmez. Üst kayda erişmeyen alt iş sahibi yalnız bilinçli paylaşılan `shared_parent_summary` alanını görür.
- `/assign/ {version,assignee_id}` yeniden atama yapar ve atama sürümünü artırır; eski bekleyen posta iptal edilir. SLA başlangıcı/orijinal hedef değişmez.
- `/status/ {version,status,result?,blocker?,reason?}` durumları `OPEN`, `IN_PROGRESS`, `WAITING`, `VERIFYING`, `COMPLETED`, `CANCELLED` olur. Beklemede engel, sonuçta çıktı, iptal/yeniden açmada gerekçe gerekir.
- Resmî işte tamamlanma isteği `VERIFYING` olur; süre işlemeye devam eder. `/accept/ {version}` bağımsız yetkili yöneticinin kabulüyle `COMPLETED` yapar ve saati durdurur. Kişisel iş doğrudan tamamlanabilir.
- Açık zorunlu çocuk üst tamamlanmasını engeller; çocuklar bitince üst kayıt kendiliğinden kapanmaz. Yeniden açma aynı SLA geçmişini kullanır; eski ihlal korunur.
- Varsayılan iç hedefler `CRITICAL=24 geçen saat`, `HIGH=7 İstanbul takvim günü`, `NORMAL=1 takvim ayı`dır; ay sonunda geçerli son güne kırpılır. Bekleme saati durdurmaz.
- `/sla-adjust/ {version,due_at,reason}` atayan/yetkili üst yönetici tarafından yapılır; sorumlu kendi lehine uzatmayı onaylayamaz. Önce mevcut ihlal kaydedilir; ilk ve güncel hedef ayrı kalır.
- `/progress/ {version,done,next_step?,blocker?}` gerçek aktörün katkısını kaydeder. `/contributions/{id}/` PATCH yalnız yazarın yeni sürüm oluşturmasını sağlar; önceki metin silinmez.
- İş/atama/SLA/audit/uygulama içi bildirim/outbox tek transaction'dır. Worker güncel atama, erişim ve SLA sürümünü tekrar doğrular; geçersiz eski uyarıyı göndermez. Belirsiz posta `UNKNOWN` kalır.
- Hatalar: geçersiz girdi/durum 400, kapsam/kendi kabulü 403/404, eski sürüm ve aynı istek anahtarıyla farklı içerik 409. `X-Request-ID` tekrarında yeni iş/atama/posta oluşmaz.
- **Henüz uygulanmayan:** iş günü takvimi, SLA duraklatma, grafik bağımlılık yönetimi ve kapsam dışı unit işinin ayrı kaynak kabul ekranı. İlk sürüm kapsam dışına doğrudan atamayı reddeder.

Kod: [WorkViewSet](../../backend/core/views.py), [SLA/atama servisi](../../backend/core/services.py), [worker](../../backend/core/worker.py).
Testler: [test_work_api.py](../../backend/core/tests/test_work_api.py), [test_sla.py](../../backend/core/tests/test_sla.py), [test_worker.py](../../backend/core/tests/test_worker.py), [test_persistence.py](../../backend/core/tests/test_persistence.py). Güncel kanıt: [QA raporu](../QA_REPORT.md).
