# onecs rapor ve AI akışı

Bu belge mevcut uygulamayı açıklar; [Revizyon 3](../UYGULAMA_PLANI.md) hedefinin ve kurumsal pilot kabulünün tamamlandığı anlamına gelmez.

## Akış ve servis sözleşmesi

- `POST /api/v1/report-selections/`, kullanıcının erişebildiği iş/proje/vakayı hafta ve kaynak kimliğiyle seçer veya seçkiden çıkarır.
- `POST /api/v1/reports/`, organizasyon yöneticisi veya etkin PM görevi ister; geçerli dönem en fazla 366 gündür. Etkin kullanıcıların dönem seçkileri, raporu oluşturan kişinin kaynak erişimiyle tek tek süzülür. Böylece çalışanın yıldızladığı normal öncelikli iş de yetkili yöneticisinin raporuna taşınır. Açık kritik, SLA ihlalli, onay veya doğrulama bekleyen kayıtlar da adaylara eklenip tekilleştirilir; sürümlü kaynak snapshot'ı oluşturulur.
- Dönem seçkileri belirler; snapshot güncel kayıt durumudur. Bütün ilerleme geçmişini yalnız bu tarihler arasında yeniden hesaplayan tarihsel rapor uygulanmış sayılmaz.
- `POST /reports/{id}/generate/`, kayıt sürümünü kontrol eder ve `BackgroundJob` oluşturur: `DRAFT → GENERATING → READY → APPROVED`. Kuyruk payload'ı `ai_profile_id`, `ai_configuration_version`, `ai_settings_version` taşır; snapshot `administration.profiles.selected_ai_snapshot()` ile iş oluşturulurken alınır. Worker başarısız olursa hata/job durumu görünürdür.
- `core.services.generate_report`, etkin hesabı, erişim parmak izini, kaynak sürümünü ve özet/ayrıntı görünürlüğünü çağrı öncesinde ve sonuç kaydında doğrular; güncel job/lease sahibi olmayan worker sonucu yazamaz.
- AI adaptörü kaynaklı metin üretir; kapalı/başarısız sağlayıcıda açıkça etiketlenen kurallı rapor kullanılır. Bütçe, kullanım ve sağlayıcı sınırları [Entegrasyon servislerinde](../services/INTEGRATIONS.md) açıklanır.
- `POST /reports/{id}/approve/`, `READY`, güncel `version`, aynı `content_hash` ve aynı kaynak sürümlerini ister; onay başka içeriğe taşınmaz.

## Bağlantı, model ve kalıcı iş

AI bağlantıları ad, endpoint ve şifreli anahtarı birbirinden ayıran en fazla 8 etkin profille yönetilir. Model, sıcaklık, süre, giriş/çıkış ve günlük bütçe ayarı ortaktır. Her profil ayrı test edilir; ortak model ayarı değiştiğinde önceki başarı rozeti yeni ayarı doğrulamaz. Ayarı kaydetmek gerçek bağlantı testi yerine geçmez.

Kuyruğa alınmış iş sabitlenen bağlantı ve ortak ayar sürümlerini kullanır. Sonradan varsayılan profil, anahtar veya model değiştirilmesi bekleyen işi yeni sağlayıcıya taşımaz. Arşivlenen profile ait iş başka profile sessizce yönlendirilmez. Sürüm alanı bulunmayan eski işler `profile_id=null`, bağlantı/ayar sürümü `0/0` ile açık kurallı fallback kullanır; güncel varsayılanı kendiliğinden seçmez.

Worker rapor işi lease'i **240 saniye**, AI çağrısının üst süre sınırı **180 saniye**dir; aradaki pay doğrulama ve commit içindir. Aynı iş kimliği kullanım ledger'ını tekilleştirir; süresi dolup başka worker'a geçen işin geç yanıtı yayımlanmaz. Kaynak erişimi sağlayıcı çağrısından önce ve sonucu kaydederken yeniden kontrol edilir. Bütçe rezervasyonu bağlantılar arasında ortaktır. Sağlayıcının ölçmediği kullanım ve tanımlanmamış fiyat null/bilinmiyor kalır.

AI yokken/kapalıyken, boş kaynakta veya bütçe/sağlayıcı hatasında `RULE_BASED` rapor üretilir; `AI` modu yalnız doğrulanan sağlayıcı yanıtıdır. Gerçek kurumsal model bağlantısı ve canlı token/maliyet doğrulaması henüz beklemektedir. LDAP keşif/aktarımın uygulanmış olması da gerçek kurum LDAP girişinin doğrulandığı anlamına gelmez. Ağ izinleri, sır yönetimi ve adaptör sınırları [entegrasyon servisinde](../services/INTEGRATIONS.md) tutulur.

## Yetki, çıktı ve hata yolları

- Taslak raporu yalnız oluşturan kişi görür ve yönetir. `APPROVED` rapor, hazırlayan kişinin üst organizasyon yöneticilerine salt okunur görünür; alıcının bütün kaynaklara ve snapshot'taki ayrıntı seviyesine güncel erişimi de doğrulanır. Kardeş unit raporları açılmaz. Üst yönetim görünümü raporu yeniden üretme veya onaylama hakkı vermez.
- Proje özetine erişen kişinin rapor girdisi de özet alanlarıyla sınırlandırılır; tam proje katkıları bu yoldan açılmaz.
- Eski sürüm/hash veya değişmiş kaynak 409; kaldırılan erişim 403/404; geçersiz dönem ve uygunsuz durum 400 üretir. Yeni seçki/snapshot için yeni rapor hazırlanır.
- `frontend/src/pages/Reports.tsx` üretimi izler, Markdown indirir ve tarayıcının yazdır/PDF işlevini açar. Taslak çıktı alınabilir; indirme raporu kendiliğinden onaylamaz. Sunucuda PDF üretimi ve PPTX yoktur.

## Kod ve doğrulama

- Kod: [API akışları](../../backend/core/views.py) içindeki `ReportSelectionViewSet`/`ReportViewSet`, [rapor servisi](../../backend/core/services.py), [worker](../../backend/core/worker.py), [profil çözümleme](../../backend/administration/profiles.py) ve [rapor arayüzü](../../frontend/src/pages/Reports.tsx).
- Mevcut test referansları: [rapor seçkisi](../../backend/core/tests/test_report_rollup.py), [worker ve sürüm sabitleme](../../backend/core/tests/test_worker.py) içindeki `ReportJobRecoveryTests`, [proje mahremiyeti](../../backend/core/tests/test_policy.py) içindeki `PublishedProjectPrivacyTests`, [entegrasyon testleri](../../backend/administration/tests/test_integrations.py) içindeki `IntegrationServiceTests`; [HTTP kabulü](../../tests/api_acceptance.py) içindeki `test_50_report_star_sources_and_generation`.
- Worker testleri kuyruk oluştururken profil snapshot'ının saklanmasını, adaptöre aynı üç sürümün iletilmesini ve eski işte 0/0 fallback'i ayrı doğrular. Tüm backend koşusu [191 test + 41 alt senaryo](../../tests/artifacts/backend-tests.json); canlı HTTP koşusu [46 test](../../tests/artifacts/api-acceptance-ui-org-overhaul.json) ile geçmiştir. Bunlar taklit sağlayıcı sınamalarını gerçek kurumsal bağlantı kanıtına dönüştürmez.
- İlgili kabul hedefleri K30–K32 ve K38; son çalıştırma sonuçları [QA raporunda](../QA_REPORT.md) değerlendirilir.
