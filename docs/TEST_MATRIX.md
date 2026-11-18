# onecs test matrisi

## onecs adlandırma kapsamı

Arayüz ve kaynak dokümanlarda ürün adı `onecs` olarak standartlaştırıldı. Yapılandırma anahtarları, cookie/session ve tarayıcı tercih anahtarları, API güvenlik şeması, JWT issuer/audience ve genel okuma kapsamı aynı adlandırmaya taşındı. Mevcut secret/şifreleme değerleri ve veritabanı kayıtları korunur; dolu kurulum yükseltme adımları [README](../README.md#yerel-kurulum) içindedir. Yeni kaynak ve dokümanlar için kural [geliştirme yönergesine](AGENTS.md) yazıldı.

Geçmiş kanıtların proje içindeki adlandırması normalleştirilirken açıklama eklendi; özgün dosyalar proje dışındaki arşivde korunur. Geçmiş test sayıları ve sonuçları değiştirilmedi; bu kayıtlar güncel adlandırma geçişinin yeniden test edildiği anlamına gelmez. Güncel geçiş doğrulaması aşağıdadır; sonraki bölümlerdeki önceki sürüm toplamlarıyla birleştirilmez.

| Kontrol | Güncel sonuç ve kanıt |
| --- | --- |
| PostgreSQL backend | **404 test geçti**, 36,230 sn; migration modülü son tekrarı **2 test geçti**, 0,036 sn. Tekrar toplam sayıya eklenmez. [Koşu çıktısı](../tests/artifacts/onecs-rebrand-backend-tests.txt). |
| Frontend ve derleme | **13 dosyada 73 test geçti**, `npm run build` geçti. [Kontrol kaydı](../tests/artifacts/onecs-rebrand-frontend.json). |
| Django ve API sözleşmesi | `manage.py check`, `makemigrations --check --dry-run`, `spectacular --validate` geçti. |
| Yerel yükseltme ve canlı kontrol | `core.0009_onecs_brand` uygulandı; giriş/kullanıcı/dashboard/OpenAPI 200, yeni cookie adları, önceki kullanıcıların korunması ve kayıtlı sırların çözülmesi doğrulandı. Eşzamanlı kullanıcı eklemeleri sabit toplam iddiasından ayrılır. [Canlı kanıt](../tests/artifacts/onecs-rebrand-live.json). |

## Proje içgörüleri ek kabulü

Yeni akışlar için **21/21 HTTP testi geçti**; mevcut regresyonun 45 geçen senaryosuna, kaynak dizini düzeltmesi sonrası geçen 1 hedefli gerçek AI testi eklendi. **67 farklı senaryo** ayrı koşularda doğrulandı; tek 67'lik tam koşu değildir. Kanıtlar: [yeni 21](../tests/artifacts/project-insights-acceptance.json), [46'lık koşunun korunmuş 45/46 sonucu](../tests/artifacts/api-acceptance-project-insights-regression.json), [düzeltilen testin gerçek AI tekrarı](../tests/artifacts/api-report-source-index-recheck.json). Yeni kapsamın bütün alt varyasyonları [FEATURE_ACCEPTANCE.md](testing/FEATURE_ACCEPTANCE.md) içinde geçen/bekleyen ayrımıyla izlenir.

**Ayrı feature snapshot sonucu:** 234 backend testi + 45 alt senaryo (19,598 sn), 17 frontend testi, strict TypeScript/production build, uyarısız strict OpenAPI ve migration drift kontrolü geçti. Canlı DB yerine ayrı test DB kullanılıp kaldırıldı. Eşzamanlı LDAP ilk giriş, onecs marka, ek dosya ve anons değişiklikleri bu snapshot'a dahil değildir. İki ldap3/pyasn1 deprecation uyarısı ve 543,22 kB entry bundle boyut uyarısı kaydedildi. [Snapshot kanıtı ve kaynak hash kapsamı](../tests/artifacts/project-feature-snapshot.json).

| Yeni alan | Gerçek HTTP kanıtı | Sınır |
| --- | --- | --- |
| İki seviyeli ekip/teslimat ağırlığı | `project_insights_acceptance.py` 01–07 | Ayrı PostgreSQL yarış ve worker kontrolleri backend katmanıdır. |
| Davetli anketi, yanıt değişimi ve gizlilik | 08, 09, 20 | Tekil yanıt, stale `response_version`, %50/%100 kapsam; kapanış yarışı ayrı. |
| Günlük/haftalık/kapanış raporu | 10–14, 21 | Yerel kurallı üretim, değişmez kaynak/original, insan edit/yayın; canlı AI tüm yeni türlerde denenmiş sayılmaz. |
| Kişi iş yükü ve hızlı atama | 15–19 | Org scope, JWT read-only, personel yöneticisine özel teknik kanıtın kapalı kalması. |
| Genel raporun gerçek AI kaynak dizini | Eski suite `test_50`, hedefli tekrar | 9/9 UUID görünür; modelin tüm çıkarımlarının doğruluğu ölçülmedi. |
| Proje kapanışında canlı AI | [Ayrı root UI kanıtı](../tests/artifacts/project-ai-live-check.json) | **AI başarısı doğrulanmadı**: 2048 çıkış `output_truncated`, yeni 4096 istek sağlayıcı öncesi `budget_or_request_limit`; RULE_BASED fallback READY geçti, limit artırılmadı. |
| Yeni UI | Root tarayıcı gözlemleri [QA raporunda](QA_REPORT.md) | HTTP testleri görsel/klavye/reduced-motion kabulünün yerini almaz. |
| Güncel restore | [62 tablo / 910 satır, 0,824 sn](../tests/artifacts/restore-project-insights.json) | Dump migration kapsamı core0006 + admin0004; sonradan gelen0007/0008 ve kurum RPO/RTO kapsam dışı. |

Birleşik working tree son kontrolü root tarafından **293 backend + 96 alt senaryo** (19,68 sn) ve **24 frontend**, strict build (271 ms) olarak raporlandı; bağımsız LDAP/marka değişiklikleri de bu toplamın içindedir. Ayrı staged feature snapshot sonucu ayrıca değerlendirilir. Yerel temizleme sonrası 29 korunan model satır hash'i eşit kaldı; [klon](../tests/artifacts/cleanup-clone-proof.json) ve [yerel canlı temizleme](../tests/artifacts/cleanup-live-verification.json) kanıtları üretim geri yükleme tatbikatı yerine sayılmaz.

## Önceki sürümün K01–K40 başlangıç kanıtı

18 Kasım 2026 · **193 backend testi + 41 alt senaryo, 46 gerçek HTTP testi ve 9 frontend testi geçti.** Sonuç ve sınırlar [QA raporunda](QA_REPORT.md), HTTP kanıtı [JSON artifact içinde](../tests/artifacts/api-acceptance.json) tutulur.

Bu matris Revizyon 3 kabul maddelerini doğrulama katmanına bağlar. **Geçti**, belirtilen yerel kabul akışının çalışan kanıtı olduğunu gösterir. **Kısmi**, geçen kontrollerin bulunduğunu fakat kalan davranışın ayrıca kanıtlanması gerektiğini gösterir. Testlerin tamamının geçmesi K01–K40 maddelerinin tamamının kapandığı anlamına gelmez. Haricî entegrasyon veya kullanıcı ölçümü lokal testle tamamlanmış sayılmaz.

## Çalışma sınırı

- API kabul testleri: ayrı cookie/CSRF oturumlarıyla gerçek HTTP ve PostgreSQL üzerinde sentetik veri.
- Backend domain/transaction testleri: uygulamanın `backend/core/tests/` dizini.
- UI: gerçek tarayıcıda rol ekranları, hata bildirimleri, klavye ve kritik akışlar.
- Geri yükleme: ayrı PostgreSQL veritabanında 53 tablo / 573 satır eşleşti; [artifact](../tests/artifacts/restore-check.json).
- Pilot: kurum LDAP/SMTP/Teams/model erişimi, kurum RPO/RTO hedefleri ve temsilci kullanıcı ölçümleri.

`test_NN_...` adları `tests/api_acceptance.py` içindeki gerçek HTTP testleridir. `core/tests/...` ve `administration/tests/...` yolları `backend/` altındadır. Backend toplamının kaydı [backend-tests.json](../tests/artifacts/backend-tests.json), temiz demo başlangıcının kaydı [startup-smoke.json](../tests/artifacts/startup-smoke.json) dosyasındadır. Adaptör/mock testi canlı sağlayıcı kanıtı sayılmaz.

## K01–K40 eşlemesi

| Kabul | Beklenen davranış | Otomasyon / yöntem | Kalan geniş kapsam | Son durum |
| --- | --- | --- | --- | --- |
| K01 | Doğru dallar, doğrudan unit çalışanı ve ICT-CS-OS/AST ayrımı; kod değişimi yetkiyi değiştirmez. | `test_01_role_sessions`; `test_49_official_units_and_reference_people`; `core/tests/test_policy.py`; `core/tests/test_canonical_seed.py` | Yeni resmî veride 7 unit/7 alt ekip ve 37 referans/demo kişi başlangıcı; bilinen kimlikler ve ilişki kapsamı geçti. Önceki 200/12 görünümü tarihsel kanıttır; yeni UI ağaç ve OS → AST → çalışan modalı root IAB oturumunda doğrulandı. | Geçti |
| K02 | Taslak kişisel; gönderim atanmış PM’ye gider, normal yöneticisi otomatik onaylayıcı olmaz. | `test_10_private_draft_and_pm_routing` | Özel taslak → PM yönlendirmesi API ve UI geçti. | Geçti |
| K03 | Gerekçeli sürümler korunur; tek onaylı proje yayınlanır. | `test_11_project_revision_approval_and_stale_version` | Düzeltme/yeniden gönderme/yayın, gerekçe ve stale sürüm reddi geçti. | Geçti |
| K04 | Gerçek kimliğe göre kendi onayı reddedilir; rol değişimi aşamaz; tanımlı doğrudan başlatma ayrı audit ve PM atamasıyla çalışır. | `test_12_project_self_and_implicit_director_approval_denied`; `core/tests/test_policy.py` | Kendi onayı ve örtük direktör onayı reddi geçti; direktörün doğrudan charter akışı ayrıca doğrulanmalı. | Kısmi |
| K05 | Yalnız proje yönetim kapsamındaki izinler çalışır; diğer UH’nin okuması yazma hakkı vermez. | `test_13_project_resource_acceptance_does_not_grant_management`; `test_15_project_delegation_scope_and_revocation`; `core/tests/test_policy.py`; `core/tests/test_project_case_api.py` | PM/PM UH, başka UH reddi, süreli grant/scope/iptal ve tekrar devir reddi geçti. | Geçti |
| K06 | Gerçek yazar, o tarihteki ekip ve eski sürüm korunur; yalnız yetkili içerik görünür. | `test_27_contribution_authorship_is_server_owned`; `test_29_contribution_revision_preserves_original_author`; `core/tests/test_latest_flows.py` | Sunucu yazarı, ekip snapshot, append-only düzeltme ve yetkisiz düzenleme reddi geçti. | Geçti |
| K07 | Tek kayıt; ayrı policy; Bana Atananlar birleşimi yönetim hakkını genişletmez. | `test_13_project_resource_acceptance_does_not_grant_management`; `core/tests/test_persistence.py` | Üç context için DB kısıtları ve ayrı yetkiler geçti; PM görevi unit SLA başlatmadı. | Geçti |
| K08 | Bildirim resmî vaka sayılmaz; açılış yetkili; zorunlu aksiyon/doğrulama olmadan kapanmaz. | `test_30_case_roles_notice_and_independent_verification`; `core/tests/test_project_case_api.py`; `core/tests/test_latest_flows.py` | UH/TM/çalışan ayrımı, yetki devri, ihbar dönüşüm replay, zorunlu aksiyon ve bağımsız doğrulama geçti. | Geçti |
| K09 | Yalnız hedef kitle; bağlı kaynak erişimi genişlemez; süresi dolan yayın arşivlenir. | `test_40_announcement_targeting` | Hedef unit erişimi geçti; süre sonunda arşiv ve bağlı kaynak varyasyonunun ayrı regresyonu gerekli. | Kısmi |
| K10 | Tek etkin yanıt; kapalı ankette değişiklik yok; doğru payda. | `test_41_poll_rsvp_and_attendance_are_distinct`; `test_44_closed_poll_rejects_late_response` | Tek etkin oy, değişim, payda ve kapanıştan sonra ret geçti; eşzamanlı son oy/kapanış yarışı ayrıca gerekli. | Kısmi |
| K11 | Üçü ayrı; yanıtsız/kararsız/katılmayacak ayrılır. | `test_41_poll_rsvp_and_attendance_are_distinct` | API ve UI: anket, RSVP ve gerçek katılım birbirini değiştirmedi; yanıtsız paydası korundu. | Geçti |
| K12 | Direktör toplamı tekil; yöneten portföy ve katkı veren unit ayrılır. | `test_17_project_totals_distinguish_managed_and_contributing_units` | İki katkı uniti/tek proje; yönetim portföyü PM biriminde, direktör toplamı tekil geçti. | Geçti |
| K13 | Eski erişim kesilir; katkı geçmişi kalır; PM yönetim birimi/grant devirleri kontrollü yapılır. | `test_63_deactivated_account_loses_existing_session`; `core/tests/test_policy.py`; `core/tests/test_continuity.py` | Pasifleştirme, grant iptali, PM devri ve katkı ekip snapshot geçti; organizasyon transferi sonrası bütün eski erişim yüzeyleri ayrıca denenmeli. | Kısmi |
| K14 | İçerik, başlık ve gizli varlık bilgisi sızmaz. | `test_02_unauthenticated_surfaces_rejected`; `test_14_project_audience_cannot_read_full_contributions`; `test_45_search_filters_hidden_resources`; `core/tests/test_api_scope_secondary.py`; `test_47_full_text_search_reads_body_and_preserves_scope`; `test_48_notification_read_is_recipient_scoped` | Gizli proje/iş, üst kayıt, katkı, arama ve dış JWT ikincil koleksiyonlarında fail-closed kontrolleri geçti. | Geçti |
| K15 | Üretimde God Mode yok; rol görünümünde bypass kapalı; gerçek/etkin aktör ayrı. | `test_64_test_mode_is_disabled_in_development`; backend ortam/policy testleri; `core/tests/test_test_mode.py` | Backend test/demo akışı, gerçek/etkin aktör ayrımı, üretimde bypass reddi ve gerçek HTTP development kapalı hali geçti. | Geçti |
| K16 | Tek mantıksal işlem; kalıcı iş/outbox devam eder. | `test_25_rejected_creation_is_atomic`; `test_26_idempotency_deduplicates_and_does_not_skip_csrf`; `core/tests/test_worker.py` | Tek kayıt/replay, CSRF/rol, rollback ve lease kurtarma geçti; gerçek process kesintisinin commit aralığında enjeksiyonu ayrıca gerekli. | Kısmi |
| K17 | Eski yetkiyle karar veremez; uygun PM/yetkiliye kayıtlı yeniden yönlendirme. | `test_15_project_delegation_scope_and_revocation`; `core/tests/test_project_case_api.py`; `core/tests/test_continuity.py` | Süresi biten yetki reddi ve pasif PM için kapsamlı, kayıtlı yeniden yönlendirme geçti. | Geçti |
| K18 | Yetkili dal ve yol bilgisi doğru; bütün kurum verisi browser’a yüklenmez. | Tarayıcı organizasyon/klavye kontrolü; `test_45_search_filters_hidden_resources`; `test_47_full_text_search_reads_body_and_preserves_scope`; `core/tests/test_directory_search_notifications.py` | UI klavye/dal/çalışan ve mahrem arama geçti; lazy veri yükleme miktarına bütçe kontrolü ayrıca gerekli. | Kısmi |
| K19 | Üst sorumlu korunur; alt işler ayrı; gerekli atama bildirimleri oluşur. | `test_23_unit_scope_and_private_parent`; `test_26_idempotency_deduplicates_and_does_not_skip_csrf`; `test_48_notification_read_is_recipient_scoped` | Direktör → UH → TM → çalışan; üst sahip, alt iş ve iki kanal bildirim niyeti geçti. Haricî mail teslimi K21 pilotu. | Geçti |
| K20 | Kaynak kabulü ayrı; normal UH proje içeriğini yönetemez; kabul edilmemiş kişi atanamaz. | `test_13_project_resource_acceptance_does_not_grant_management` | Kabul öncesi kişi atanamaz, kaynak kabulü proje yönetimi vermez; API ve UI geçti. | Geçti |
| K21 | İş korunur; belirsizlik görünür; eski bekleyen mail iptal; test kutusunda teslim doğrulanır. | `core/tests/test_worker.py`; `administration/tests/test_integrations.py` | WAITING_CONFIGURATION/BLOCKED/RETRY/UNKNOWN/CANCELLED/SENT davranışları geçti; kurum test kutusunda gerçek teslim gerekli. | Kısmi |
| K22 | Yalnız kendi işi ve bilinçli paylaşılan hedef özeti görünür. | `test_23_unit_scope_and_private_parent` | Kendi alt işi okunurken özel üst kaydın kimliği/metni açılmadı. | Geçti |
| K23 | Açık birimler; ay sonu doğru kırpılır; hafta sonu ve saat dilimi doğru; 1 ay 30 gün sayılmaz. | `core/tests/test_sla.py` | 24 saat/7 takvim günü/1 takvim ayı, artık yıl, İstanbul tarih sınırı ve hafta sonu geçti. | Geçti |
| K24 | Önce kişisel hedef; SLA yönetici işleminde başlar; eski katkı/tarih korunur. | `test_20_personal_work_and_formal_adoption` | Kişisel tarihler korunarak yönetici benimsemesi anında resmî SLA başladı. | Geçti |
| K25 | Açık iş sessiz değişmez; ilk tarih/ihlal korunur; saat sıfırlanmaz. | `test_24_cross_unit_reassignment_denied_and_sla_not_reset`; `test_28_sla_reassignment_adjustment_and_self_extension`; `core/tests/test_sla.py` | Politika snapshot, yeniden atama/uzatma, ilk tarih ve tarihsel ihlal korunması geçti. | Geçti |
| K26 | İhlal doğru hesaplanır; güncel durum tekilleştirilmiş uyarı; geçmiş eşik mail yağmuru yok. | `core/tests/test_sla.py::test_two_restarted_workers_emit_one_logical_breach`; `core/tests/test_worker.py` | Kesinti sonrası uyarıları birleştirme ve iki gerçek PostgreSQL bağlantısında tek ihlal geçti. | Geçti |
| K27 | Kabul öncesi saat devam eder; yetkili kabulünde durur; kişisel iş doğrudan tamamlanabilir; eski SLA/ihlal silinmez. | `test_21_formal_completion_requires_independent_acceptance`; `test_22_personal_work_completes_without_manager_acceptance` | Bekleme/doğrulamada sayaç, bağımsız kabul, kişisel tamamlanma ve yeniden açma geçti. | Geçti |
| K28 | İçerik ve hedef kitle yetkileri ayrı doğrulanır; PM rolü tek başına geniş yayına yetmez; kapalı kaynak ayrıntısı açılmaz; geri çekme işler. | `test_42_community_public_card_keeps_source_private`; `test_46_project_card_separates_content_and_audience_approval` | Temiz kart, PM içerik/UH hedef onayı ve gizli kaynağa erişmeme geçti; geri çekme ayrıca gerekli. | Kısmi |
| K29 | Gönüllü beyan; bildirim oluşur, otomatik atama/üyelik/performans puanı oluşmaz. | `test_42_community_public_card_keeps_source_private`; `core/tests/test_latest_flows.py` | Gönüllü uzmanlık ve ilgiyle otomatik atama oluşmaması geçti; yardım talebi/buluşma bildirimleri ayrıca gerekli. | Kısmi |
| K30 | Yetkili doğru dönem; kaynaklı maddeler; çıkarma gerekçesi; sayı/tarih kanonik. | `test_50_report_star_sources_and_generation`; `core/tests/test_report_rollup.py` | Ekip yıldızının UH raporuna taşınması, kritik aday, kaynak hash, kurallı çıktı ve üst yönetim okuması geçti; çıkarma gerekçesi/dönem sınırı ayrıca gerekli. | Kısmi |
| K31 | İçerik taslağa/cache’e geri yazılmaz; indirme güncel yetkiyle korunur. | `core/tests/test_worker.py::test_late_ai_result_is_discarded_when_database_actor_is_disabled`; `test_attachments.py`; `test_record_extras_api.py` | Geç AI yanıtı aktör/lease iptalinde yazılmadı; özel dosya indirmede başka unit, proje özeti, iptal edilmiş rol/üyelik, pasif hesap ve karantina reddi geçti. Diğer cache/çıktı yolları ayrıca gerekli. | Kısmi |
| K32 | Sınırlı çağrı; tahmini/doğrulanamayan ayrımı; AI’sız rapor devamı. | `test_50_report_star_sources_and_generation`; `administration/tests/test_integrations.py` | Bütçe limiti, retry dedup, citation reddi ve AI kapalı kurallı çıktı geçti; gerçek sağlayıcı timeout/usage/maliyet pilotu gerekli. | Kısmi |
| K33 | Salt okunur tüketici yazamaz; kayıt kapsamı korunur; dokümana erişim kontrollü. | `test_61_external_jwt_is_read_only_scoped_and_revocable`; `test_65_openapi_and_swagger_require_login`; `core/tests/test_api_scope_secondary.py` | JWT yazma/modül/org scope/imza bozulması/iptal ve Swagger geçti; süre sonu ve farklı audience negatifleri ayrıca gerekli. | Kısmi |
| K34 | Doğru bitiş; beyan/doğrulama ayrımı; tekilleştirilmiş uyarı. | `test_43_credential_claim_verification_and_scope` | Süreli/süresiz, beyan/doğrulama, employee/UH manage ayrımı geçti; tekrar sertifika uyarısı taraması ayrıca gerekli. | Kısmi |
| K35 | Dört kart; ilgili görevde üç etkileşim hedefi ve 30 saniyede bulma kullanıcıyla ölçülür. | Tarayıcı dört kart/rol/üç etkileşim; temsilci kullanıcı süre ölçümü | Direktör kartları/gündem, mobil giriş/menü/liste görüldü; kullanıcıyla üç etkileşim/30 saniye ölçümü yapılmadı. | Kısmi |
| K36 | Rutin işlem hızlı; tolerans dışı/taahhüt etkili değişiklik uygun onay rotasına gider. | `test_16_significant_project_change_keeps_published_revision`; `core/tests/test_project_case_api.py` | Önemli değişiklikte bağımsız karar ve eski yayın korundu; küçük termin/tolerans sınırı uç değer testi ayrıca gerekli. | Kısmi |
| K37 | Yetkisiz/kendi lehine uzatma engeli; tek geçerli sürüm; ihlal kaydı korunur. | `test_28_sla_reassignment_adjustment_and_self_extension`; `core/tests/test_work_api.py` | Kendi lehine uzatma, yetkisiz karar, stale sürüm ve ihlal koruma geçti; eşzamanlı kapanış/uzatma yarışı ayrıca gerekli. | Kısmi |
| K38 | İncelenen hash/sürüm dışında onay yok; yeniden inceleme gerekir. | `test_11_project_revision_approval_and_stale_version`; `test_16_significant_project_change_keeps_published_revision`; `test_50_report_star_sources_and_generation`; `core/tests/test_latest_flows.py` | Proje stale sürüm, rapor hash ve kaynak değişiminde kart onayı iptali geçti; hedef kitle değişimiyle onay yarışı ayrıca gerekli. | Kısmi |
| K39 | Sürümlü test/etkinleştirme, sır maskeleme; aktif iş sessiz yeni endpoint’e taşınmaz; TLS ve iptal doğrulanır. | `test_60_admin_boundaries_and_unconfigured_integrations`; `test_62_ldap_secret_masking_and_unconfigured_result`; `administration/tests/test_integrations.py`; `administration/tests/test_directory_profiles.py`; `test_66_directory_import_and_ai_profiles_require_admin`; `test_67_disabled_ai_profiles_are_isolated_and_masked` | Sürümlü ayar, sır şifreleme/maskeleme, kapalı bağlantı ve yetki reddi geçti; önceki LDAP/AI TLS hatası doğrulanmış yerel CA zinciriyle aşıldı. Yeni TLS el sıkışmaları geçti; bind/model erişimi ve SMTP/Teams doğrulaması gerekli. | Kısmi |
| K40 | Veri/job/SLA tutarlı; akış ve servis belgeleri gerçek davranışla eşleşir; kanıtlar gerçek çıktıdır. | [Restore](../tests/artifacts/restore-check.json); [başlangıç](../tests/artifacts/startup-smoke.json); `core/tests/test_worker.py` | 53 tablo/573 satır restore, job/lease, temiz başlangıç ve gereksinim bağlantıları mevcut; kurum RPO/RTO ve tüm akış belgelerinin pilot walkthrough kontrolü gerekli. | Kısmi |

## Sonuç okuma kuralları

API testinin reddedilmesini beklediği istekte `403` ile `404` güvenlik politikasına göre kabul edilebilir; `500`, HTML traceback veya kapsam dışı içeriğin görünmesi başarısızlıktır. Yetki reddi ayrıca kaydın değişmediği kontrolüyle tamamlanır. Tekrarlanan istekte yalnız yanıt kodu değil kayıt sayısı ve olay/bildirim niyeti değerlendirilir.

Üretim God Mode engeli, gerçek LDAP TLS/eşleme ve dış sistem teslimi lokal sahte adaptörle kanıtlanmaz. Test koşusunun ortamı, zamanı, komutu, atlanan test sayısı ve bilinen eksikleri raporda açıkça tutulur.

## Yeni arayüz ve entegrasyon ek kabulü

LDAP otomatik ilk giriş ek kabulü: `administration/tests/test_ldap_auto_login.py` ile ilk hesap, sabit kimlik, tam grup kapsamı, gerçek direktör yetkisi, yanlış parola/yerel kimlik çakışması/grup kaybı/audit rollback ve iki PostgreSQL bağlantısında tek hesap senaryoları geçti. İlgili yönetim/policy/kalıcılık/oturum seti **146 test**, LDAP/ayar istemci seti **16 test** geçti. [Backend](../tests/artifacts/ldap-auto-login-tests.json), [frontend](../tests/artifacts/ldap-auto-login-frontend.json). Gerçek dizin politika eşleşmesi salt okunur doğrulandı; kişisel parola ile login ve sürekli LDAP oturum iptali kurum kabulünde ayrıca doğrulanmalıdır. K39 Kısmi kalır.

18 Kasım ek bağlantı tanısı: `administration/tests/test_connection_diagnostics.py` güvenli TLS/HTTP hata nedenleri, CA dosyası doğrulaması, TLS başarısızken bind yapılmaması, kalıcı sonuç/readiness geçişleri ve yönetici olmayan kullanıcının test reddini kapsar. İlgili yönetim/kalıcılık/oturum testleriyle **75 PostgreSQL testi geçti** ([çıktı](../tests/artifacts/connection-diagnostics-tests.json)). Yerel doğrulanmış CA zinciriyle LDAP ve iki AI TLS el sıkışması geçti ([canlı kanıt](../tests/artifacts/integration-tls-diagnosis.json)); yeni koşuda LDAP bind/model isteği denenmediği için K39 **Kısmi** kalır. Önceki başarısız testler tarihsel kayıttır; yönetici tekrar test etmelidir.

[U01–U12 planı](testing/UI_SMOKE_PLAN.md), yeni merkezlenen pencere, yazı ölçeği, kalkan/pusula logo, Türkçe profil, bildirim ve LDAP/AI profil akışlarını açıklar. Ek HTTP testleri 46 testlik tam koşuda geçti. Root IAB yeni kişi modalı merkez/odak/klavye ve bildirim tıklaması/read-unread akışını doğruladı; 390 px taşma/merkez ölçümü, arama Down/Enter, Türkçe profil ve ortak ayar modalı da geçti; sertifika bildirimi → sertifika ayrıntısı ve arama sonucu → iş ayrıntısı deep-link akışları, Escape sonrası URL kimliği temizliğiyle geçti. İç içe modal/tam Tab çevrimi ayrıca denenmiş sayılmaz. QA alt ajanının Chrome kontrolü kullanıcı aktif olduğunda durduruldu. Gerçek LDAP ve iki AI testi TLS sertifika süre dolumu nedeniyle başarısız; TLS korundu. [Canlı sonuç](../tests/artifacts/live-integrations.json). Önceki 200 kişi/12 unit ekran ve 41 test çıktıları önceki sürüm olarak korunur.

## Dashboard anons/bildirim ek doğrulaması — 18.11.2026

| Senaryo | Kanıt | Sonuç |
| --- | --- | --- |
| Yayında/bekleyen anons ayrımı, ilk beş/toplam, hedef kitle/zaman sınırı | `DashboardAnnouncementTests`; dashboard HTTP kontrolü | PostgreSQL geçti |
| Kendi önerisini okuma yayın yetkisi vermez; süresi dolan öneri yayımlanamaz | Negatif rol/JWT ve durum testleri | PostgreSQL geçti |
| Öneri/yayın bildirimi tekilleştirme, rol iptali, zaman/geri çekme, transaction rollback | `AnnouncementNotificationTests` | PostgreSQL geçti |
| Global okunmamış sayısı, filtre/sayfa, read/unread, tümünü okundu kalıcılığı | `NotificationStateRegressionTests`; controller/render testleri | PostgreSQL + frontend geçti |
| Personel tahsisi/vaka bildirimi doğru detay hedefi; ana kaynağa ek erişim yok | Yeni backend + Records.notifications testleri | PostgreSQL + frontend geçti |
| Geç polling yanıtı, kullanıcı değişimi, çok sayfa yenilemede tekrarsız satırlar | notifications controller testleri | Frontend geçti |

Gerçek koşu: 324 PostgreSQL, 61 frontend; ilgili 29 backend testini içerir. Ayrıntılı kapsam ve bağımsız attachment doğrulama sınırı [QA raporunda](QA_REPORT.md#dashboard-anonsları-ve-bildirim-düzeltmesi--18112026), makine kanıtları `tests/artifacts/dashboard-announcements-notifications-{tests,frontend,live}.json` dosyalarındadır.


## 18 Kasım kayıt ekleri ve e-posta alıcıları

Oluşturma formları ve özel upload/claim/download akışı tamamlandı. Kaynak işlemi, dosya bağı, audit ve e-posta niyeti aynı transaction'da; taslak başvuru/yayın tercihleri kalıcıdır. Ortak çalışma alanında PostgreSQL üzerinde **381 test + 173 alt senaryo**, frontendde **61 test** geçti. Son şema/UUID/ilk vaka claim kontrollerinden sonra hedefli **58 test + 41 alt senaryo** tekrar geçti; tip kontrolü/üretim derlemesi, Ruff, migration drift ve fail-on-warn OpenAPI doğrulaması temiz. [Backend kanıtı](../tests/artifacts/record-extras-backend.json), [frontend kanıtı](../tests/artifacts/record-extras-frontend.json).

Gerçek yerel tarayıcıda ayrı sentetik kullanıcıyla çoklu dosya ve fotoğraf önizleme/kaldırma, alıcı seçimi, dosya ekli kayıt oluşturma ve yenileme sonrası kalıcılık doğrulandı; son konsol hata listesi boştu. Ek ayrıntıda tarama bekliyor olarak kaldı. Test kullanıcısında e-posta adresi boş olduğundan tek mail niyeti BLOCKED kaldı, dışarı posta gönderilmedi. Yeni oluşturulan sentetik kullanıcı/birim/kayıt/dosya temizlendi. [UI kanıtı](../tests/artifacts/record-extras-ui.json), [form](../tests/artifacts/ui-record-extras-form.jpg), [kayıt eki](../tests/artifacts/ui-record-extras-detail.jpg).

Gerçek kurumsal SMTP ve antivirüs entegrasyonu bu koşuda test edilmedi. Varsayılan yapılandırmada scanner olmayan dosya indirilemez; bu durum arayüzde açıkça gösterilir. İşletim sınırları [servis sözleşmesinde](services/RECORD_EXTRAS.md) tutulur.

## Dashboard yerleşimi — 18.11.2026

“Bu hafta ne değişti?” kutusunun kaldırılması, gündem kartının son bağlantı altında bitmesi, haftalık rapor bağlantısının korunması ve anonsların tablet/mobilde tam genişlikte görünmesi 1440, 1000 ve 390 px tarayıcı görünümlerinde doğrulandı; yatay taşma yok. TypeScript ve üretim derlemesi başarılı; mevcut 61 frontend testi geçti. Bu değişiklik yalnız yerleşimdir; yeni yetki, durum geçişi veya kalıcılık akışı eklenmedi. [Yerleşim ölçümleri](../tests/artifacts/dashboard-layout-checks.json), [frontend test sonucu](../tests/artifacts/dashboard-layout-frontend.json).

## Rapor ekip pivotu ek doğrulaması — 18.11.2026

| Davranış | Kanıt | Sonuç |
| --- | --- | --- |
| Kaynak/rapor/JWT yetkisi, rol iptali, bozuk kaynak | `test_report_pivot.py` | PostgreSQL geçti |
| Snapshot ekip etiketi, salt okunur GET, tekil toplam, sabit dönem sonu | `test_report_pivot.py`; mevcut worker/rollup regresyonu | PostgreSQL geçti |
| Genel Rapor ilk; ekip seçimi yalnız ekip bölümleri; aktör/sürüm/hash ayrımı | Pivot/Reports frontend testleri; sentetik tarayıcı | Geçti |
| Sekme Home/End, tablo ve bölüm görünümü | `report-pivot-ui.json` | Masaüstü tarayıcı geçti; mobil/print ayrıca denenmedi |

376 PostgreSQL ve 76 frontend testi son push isteğinden önce tamamlandı. İstekten sonra yeni test koşulmadı. [Rapor sözleşmesi](services/REPORTING.md), [QA ve gerçek çıktılar](QA_REPORT.md).
