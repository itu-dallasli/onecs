# Atlas API sözleşmesi

Çalışan API `/api/v1/` altındadır. Oturum açmış kullanıcı için [yerel Swagger](http://localhost:3100/api/v1/docs/) ve [OpenAPI şeması](http://localhost:3100/api/v1/schema/) sunulur. Sürüm kontrolüne alınan [OpenAPI YAML](api/openapi.yaml), `manage.py spectacular --validate --fail-on-warn` ile mevcut koddan üretilir. Şema, nesne bazlı policy kontrolünün yerine geçmez.

## Kimlik ve işlem sınırı

Tarayıcı önce `GET /auth/csrf/`, sonra `POST /auth/login/` kullanır. Login metodu `local` veya `ldap` olur; istek alanları Swagger'da tanımlıdır. Oturum `atlas_sessionid` HttpOnly cookie'sinde, CSRF değeri `atlas_csrftoken` cookie'sinde tutulur. Yazma istekleri `X-CSRFToken` taşır; parolalar veya bearer tokenlar URL'ye eklenmez. `GET /auth/me/` güncel kullanıcı ve arayüz yetki özetini, `POST /auth/logout/` çıkışı sağlar.

Dış tüketici, yetkili kullanıcıya bağlı `ApiClient` için üretilen kısa ömürlü JWT bearer kullanır. Tokenın scope'u, istemcinin organizasyon sınırı ve kullanıcının güncel kayıt yetkisi birlikte uygulanır. Dış API salt okunurdur; yönetim ve kimlik uçlarına erişemez. İstemciyi iptal etmek veya kullanıcısını pasifleştirmek mevcut tokenın kullanımını da keser. Tokenı oluşturmak kurumun bütün verisini açmaz.

Organizasyon sınırı ana kayıtların yanında dashboard sayaçlarına, sertifika/katılım bildirimlerine, duyuru/paylaşım kartlarına, kişi aramasına ve faaliyet geçmişine de uygulanır. Bilinmeyen kaynak türündeki dış API bildirimi kapalı kabul edilir. Kapsam, kaydın organizasyonuna göre belirlenir; izinli çok ekipli projenin katılımcı alanları ayrı kişi bazlı maskeleme iddiası taşımaz.

Domain değişiklikleri nesnenin `version` değerini ister. Eski sürüm `409` döndürür; istemci güncel kaydı yükleyip kullanıcıya yeniden karar verdirir. `X-Request-ID` ile aynı mantıksal isteğin tekrarı gövde/kimlik kontrolüyle tekilleştirilir; replay öncesinde de kimlik, CSRF ve güncel yetki doğrulanır. Aynı kimliği farklı gövdeyle kullanmak reddedilir. Audit ve bildirim niyeti domain işlemiyle aynı transaction içinde yazılır.

## Kaynak grupları

| Kaynak | Kullanım |
| --- | --- |
| `organization`, `people`, `project-managers` | Organizasyon ve gönüllü uzmanlık rehberi; yönetim kapsamı ve PM görevi ayrı |
| `projects`, `participation-requests` | Taslak/gönderim/PM kararı; personel talebi ve kaynak yöneticisinin ayrı kabulü |
| `work` | Unit işi, kişisel iş, alt işler, atama, sonuç kabulü ve SLA değişikliği |
| `cases`, `case-notices` | Yetkili vaka, çalışan bildirimi, ekip aksiyonları ve bağımsız kapanış doğrulaması |
| `contributions`, `activity` | Sürümlü katkı ve yetkiyle süzülen geçmiş |
| `community`, `announcements` | İçerik ve hedef kitle onayları; kontrollü paylaşım |
| `events` | Davetli, anket, RSVP ve gerçekleşmiş katılımın ayrı kaydı |
| `credentials` | Sertifika beyanı, yönetici değerlendirmesi ve yenileme eşikleri |
| `report-selections`, `reports` | Yıldız seçkisi, kaynak snapshot'ı, kalıcı üretim işi ve içerik onayı |
| `dashboard`, `search`, `notifications` | Yetkili özet, PostgreSQL araması ve uygulama içi bildirimler |
| `sla-policies`, `api-clients` | Sürümlü SLA politikası ve kontrollü veri tüketicileri |
| `admin/*` | Kullanıcı/rol, LDAP/SMTP/AI ayarı ve bağlantı testi, kullanım, audit ve kuyruk |

İş/proje/vaka için aynı aksiyon adının bulunması aynı yetki anlamına gelmez. Proje kaynak tahsisinin kabulü, Unit Head'e projeyi yönetme yetkisi vermez. Her grubun ayrıntılı akışı [akış belgelerinde](flows/AUTHORIZATION.md) açıklanır. OpenAPI uçları ve temel istek şemalarını gösterir; özel aksiyonların bütün durum/yetki koşulları şemada ifade edilmez. Gerçek payload ve yanıt örnekleri bağımsız HTTP kabul testlerinde de bulunur.

## Rehber, tam metin arama ve bildirimler

`GET /people/?org_id={id}&search={metin}&limit=48&offset=0` seçilen dalın çalışanlarını ve yönetici görevlilerini sayfalar. Alt dallar varsayılan olarak kapsanır; `include_descendants=false` tek düğüm, `role` ise görev filtresidir. Yanıt `{results, count, limit, offset, next_offset}` taşır. Aynı kişinin ikinci unit görevi primary organizasyonuyla sınırlanmaz. Dış JWT'nin ek organizasyon sınırı korunur.

Kişi yanıtında `profile_kind`, `identity_source`, `role_label` ve etkin `roles[{role,org_id,org_name,includes_descendants,expires_at}]`; organizasyon yanıtında `manager_id`, `manager_ids`, `managers`, `manager_name`, `member_count`, `is_demo` bulunur. `OFFICIAL_REFERENCE` şema referansı, `DEMO` açıkça kurgusal hesap, `LOCAL` yerel hesap, `LDAP` sabit dizin kimliğiyle eşlenmiş hesaptır. Referans adı gerçek LDAP doğrulaması değildir. Başlangıç verisi 7 unit, 7 yönetici alt ekibi ve 37 kişilik kısmi rehberdir.

`GET /search/?q={metin}` PostgreSQL tam metin, sözcük öneki, Türkçe harf/aksan sadeleştirme ve sınırlı trigram eşleşmesiyle en fazla 25 sonuç verir. Erişim filtresi eşleşmeden önce uygulanır. İş/vaka açıklamaları ve izinli rehber/paylaşım/anons/etkinlik/sertifika alanları aranır; yalnız proje özeti okuyabilen kullanıcı yayımlanmış başlıkla sınırlıdır. Onaylanmamış revizyon açıklamasından sonuç varlığı sızdırılmaz. Sonuç kaynağı `resource_type` ve `id` ile belirtilir.

| Endpoint | Davranış |
| --- | --- |
| `GET /notifications/?status=all\|unread\|read` | Yalnız mevcut alıcının ve güncel kaynak erişiminin izin verdiği kayıtlar; `read_at`, `is_read` |
| `POST /notifications/{id}/read/` | Varsayılan okundu; `{read:false}` yeniden okunmadı; alan gerçek boolean olmalı |
| `POST /notifications/mark-all-read/` | Yalnız o anda görünür okunmamış bildirimleri değiştirir; `{updated:n}` |

Başka alıcının veya erişimi kaldırılmış kaydın bildirimi 404; geçersiz durum/boolean 400 döndürür. Okundu işareti e-posta teslimi veya işin tamamlandığı anlamına gelmez. Dış JWT bu yazma uçlarını kullanamaz. Ayrıntılı davranış ve test referansları [rehber servisindedir](services/DIRECTORY_SEARCH_NOTIFICATIONS.md).

## LDAP önizlemesi ve bağımsız AI bağlantıları

Bu uçlar etkin teknik yönetici içindir; simülasyon ve dış JWT oturumlarında kullanılamaz. Teknik adminin LDAP kişisine iş yönetimi rolü vermesi ayrıca direktörün hedef organizasyon kapsamını gerektirir.

| Endpoint | Davranış |
| --- | --- |
| `POST /admin/ldap/discover/` | Gerçek TLS/servis bağlantısıyla RootDSE ve Base DN keşfi |
| `POST /admin/ldap/search/` | Kullanıcı/grup önizlemesi; aktöre ve ayar sürümüne bağlı 15 dakikalık `batch_id` |
| `POST /admin/ldap/import/` | `{batch_id, entries:[{subject,org_node,role}], expected_config_version}` ile açık kişi/kapsam aktarımı |
| `GET/POST /admin/ai/profiles/` | Bağımsız bağlantı profillerini listeleme/oluşturma |
| `GET/PATCH/DELETE /admin/ai/profiles/{id}/` | Profilin sürümlü ayarı veya arşivlenmesi |
| `POST /admin/ai/profiles/{id}/test/` | O profile gerçek kısa model isteği; sır geri okunmaz |
| `POST /admin/ai/profiles/{id}/default/` | Sonraki işler için varsayılan bağlantı seçimi |
| `GET/PATCH /admin/settings/ai/` | Ortak model, giriş/çıkış sınırı, süre, sıcaklık, bütçe ve fiyat ayarı |
| `GET /admin/ai/usage/?from=YYYY-MM-DD&to=YYYY-MM-DD&profile_id={id}` | Tarih/profil kullanım ve tahmini maliyet; `model`, `operation` filtreleri de desteklenir |

LDAP önizlemesi hesap açmaz. Aktarım sabit `entryUUID/objectGUID` ister; aynı ad/e-postadan referans veya yerel hesabı otomatik birleştirmez. Grup araması, otomatik grup–iş rolü senkronizasyonu değildir. Geçmiş/süresi dolmuş paket ve yetkisiz kapsam atomik olarak reddedilir.

En fazla 8 etkin AI profili ayrı bağlantı/anahtar sürümüne sahiptir; model ve bütçe ortak ayarlardan gelir. `configured` kayıtlı ayarı, `ready` aynı bağlantı ve ortak model ayarıyla başarılı testi belirtir. Kullanımı bilinmeyen dış çağrı null kalır; sıfır token/maliyet gösterilmez. Tam alanlar, sürüm ve ağ sınırları [entegrasyon sözleşmesinde](services/INTEGRATIONS.md) açıklanır. Bu uçların uygulanması, gerçek kurum LDAP/model bağlantısının doğrulandığı anlamına gelmez; bu kabul hâlâ beklemektedir.

## Hata ve arka plan işleri

Geçersiz alan veya durum `400`, geçersiz kimlik `401`, yetki reddi `403`, görünmeyen/bulunmayan kayıt `404`, sürüm veya içerik çakışması `409` üretir. Kayıt mahremiyeti için bazı yetki redleri `404` olarak görünür. İstemci HTML traceback'i başarılı cevap gibi yorumlamaz.

Rapor üretiminde `BackgroundJob`, posta/bildirimde `OutboxEvent` kalıcı kaynaktır. Rapor kuyruğa alınırken `ai_profile_id`, `ai_configuration_version`, `ai_settings_version` payload'a kaydedilir; sonradan seçilen profil veya model bekleyen işi sessizce değiştirmez. Rapor işi lease'i 240 saniyedir; AI süre sınırı en fazla 180 saniyedir. Yeniden sahiplenilen işte eski worker sonucu yayımlayamaz. `WAITING_CONFIGURATION` teslim edilmiş anlamına gelmez; `UNKNOWN` dış sistemde sonucu belirsiz işlemdir. Worker lease, checkpoint ve tekillik kontrolleriyle yeniden başlatılır; belirsiz e-posta teslimi körlemesine tekrarlanmaz. Gerçek entegrasyon sınırları [servis belgesinde](services/INTEGRATIONS.md) açıklanır.

## Şemayı yenileme

```bash
.venv/bin/python backend/manage.py spectacular --file docs/api/openapi.yaml --validate --fail-on-warn
```

HTTP sözleşmesi bağımsız rol oturumlarıyla [kabul testlerinde](../tests/README.md) doğrulanır. 18 Kasım 2026 koşusunda [46 HTTP testi](../tests/artifacts/api-acceptance-ui-org-overhaul.json) ve PostgreSQL üzerinde [191 backend testi ile 41 alt senaryo](../tests/artifacts/backend-tests.json) geçti. Kurum LDAP/SMTP/model bağlantısı için bu yerel kanıt yeterli değildir.
