# Atlas entegrasyon ve yönetim servisleri

Bu belge `backend/administration` uygulamasının çalışan sözleşmesini açıklar. Ayar ekranının görünmesi bağlantının kurulduğu anlamına gelmez. Entegrasyonlar gerçek bağlantı testinin sonucunu, test edilen yapılandırma sürümünü ve zamanı ayrı saklar.

## Yönetim sınırı ve kimlikler

Yönetim endpointleri oturum açmış, etkin `SYSTEM_ADMIN` rolüne sahip kullanıcı içindir. Dış API JWT istemcileri bu endpointleri kullanamaz. Başka kullanıcı görünümünde test yapılırken yönetim erişimi engellenir; gerçek aktör ile etkin kullanıcı aynı olmalıdır.

Teknik yönetici kullanıcı oluşturabilir, sıradan çalışanın organizasyonunu belirleyebilir ve yerel hesap için parola atayabilir. Bu **güvenilen ve denetim kaydı tutulan kimlik sağlama yetkisidir**. Organizasyona atama, yayımlanmış ekip içeriklerine erişim sağlayabilir; bu işlem risksiz bir görünüm değişikliği değildir. Teknik yönetici iş yönetimi rolü kazanmaz. Kendi erişim kapsamını veya rollerini değiştiremez. Başka bir iş yöneticisinin parolasını sıfırlamak ya da hesabını değiştirmek için ayrıca direktör yetkisi gerekir.

`TEAM_MANAGER`, `UNIT_HEAD`, `PROJECT_MANAGER` veya `DIRECTOR` rolü vermek için gerçek kullanıcının ayrıca güncel `DIRECTOR` rolü ve hedef organizasyonda yönetim kapsamı bulunmalıdır. Özel proje/vaka yetki devirleri bu genel kullanıcı formundan verilmez; ilgili domain akışı kullanılır. Proje yöneticisi rolü tek başına bir `PMAppointment` veya proje yönetim hakkı oluşturmaz.

Kullanıcı API'si salt okunur `access_version` döndürür. Profil/rol PATCH isteğinde `expected_access_version` gönderildiğinde değer satır kilidi altında doğrulanır; eski editör 409 alır ve yeni kayıt ezilmez. Geçiş uyumluluğu için sürüm alanı API'de isteğe bağlıdır; Atlas arayüzü güncel değeri gönderir.

## Ayar API'si ve sürümleme

| Endpoint | Davranış |
|---|---|
| `GET /api/v1/admin/settings/` | Kullanılabilir sekmeler ve sır içermeyen etkin ayarlar |
| `GET /api/v1/admin/settings/{section}/` | Tek sekmenin etkin sürümü, `config`, `secret_fields`, `configured`, `ready`, `latest_test` |
| `PATCH /api/v1/admin/settings/{section}/` | `config`, `secrets`, `expected_version`, `activate: true` ile yeni sürüm |
| `POST /api/v1/admin/integrations/{section}/test/` | Gerçek bağlantı testi; SMTP için `recipient` gerekir |
| `GET/POST /api/v1/admin/users/` | Kullanıcı arama / güvenilen kimlik sağlama |
| `PATCH /api/v1/admin/users/{id}/` | Profil, parola veya izinli rol değişikliği |
| `GET /api/v1/admin/roles/` | Rol seçenekleri ve `business_grant_allowed` |
| `GET /api/v1/admin/ai/usage/` | Tarih/model/işlem filtresiyle token ve maliyet tahmini |
| `GET/POST /api/v1/admin/ai/profiles/` | Bağımsız şifreli AI bağlantılarını listeleme/oluşturma |
| `GET/PATCH/DELETE /api/v1/admin/ai/profiles/{id}/` | Bağlantı ayrıntısı/sürümü veya arşivleme |
| `POST /api/v1/admin/ai/profiles/{id}/test/` | Yalnız bu bağlantıya gerçek kısa model isteği |
| `POST /api/v1/admin/ai/profiles/{id}/default/` | Gelecek işler için varsayılan bağlantıyı seçme |
| `POST /api/v1/admin/ldap/discover/` | Doğrulanmış bağlantı üzerinden RootDSE/Base DN keşfi |
| `POST /api/v1/admin/ldap/search/` | Kullanıcı/grup araması ve süreli önizleme paketi |
| `POST /api/v1/admin/ldap/import/` | Önizlemeden açık kişi–organizasyon–rol onayı ile aktarım |
| `GET /api/v1/admin/audit/` | Denetim olayının metadata'sı; hassas domain payload'ı verilmez |
| `GET /api/v1/admin/jobs/` | `job`/`outbox` türü ve durum filtresiyle kalıcı işlem metadata'sı |
| `POST /api/v1/admin/jobs/{id}/retry/` | Başarısız işin veya uzlaştırılmış posta tesliminin kontrollü yeniden denemesi |

Sekmeler `general`, `ldap`, `smtp`, `ai`, `teams` olur. PATCH mevcut ayarlarla birleştirilir; bilinmeyen alanlar reddedilir. `expected_version` eskiyse değişiklik uygulanmaz. Ayar sürümü ve denetim kaydı aynı transaction içinde yazılır. Mevcut uygulama doğrulanan ayarı etkin sürüm olarak kaydeder; ayrı taslak/sonradan etkinleştirme akışı bulunmaz ve `activate: false` reddedilir. Bağlantı testi kaydetme işleminden ayrıdır. `configured`, ayarların kayıtlı ve etkin olduğunu; `ready`, **aynı sürümün** gerçek bağlantı testinin başarıyla geçtiğini belirtir. Yeni ayar sürümü eski test başarısını devralmaz.

Test sonucu `success`, `failure` veya `unconfigured` döner. HTTP yanıtı sırasıyla 200, 400 veya 409'dur. Bir testin başarısı diğer test türlerini kapsamaz; LDAP servis bağlantısı başarılı olması her kullanıcı/grup eşlemesinin doğrulandığı anlamına gelmez.

## Sırlar ve ağ güven sınırı

`ATLAS_ENCRYPTION_KEY`, deployment sırasında oluşturulmuş Fernet anahtarıdır. Anahtar yokken sır kaydetme başarısız olur; uygulama sessizce bir anahtar üretmez. Anahtar veritabanında tutulmaz. Anahtarın değişmesi eski ayarların otomatik açılmasını sağlamaz; kontrollü yeniden şifreleme/yeniden yapılandırma gerekir. Veritabanı yedeğinin yanında uygun anahtar kurtarma süreci de planlanmalıdır.

Sırlar `ConfigurationVersion.encrypted_secrets` içinde şifrelenir. API yalnız mevcut sır alanlarının adlarını döndürür. Boş metin mevcut sırrı korur; `null` sırrı kaldırır. Parola, API anahtarı veya tam yapılandırma sırları denetim payload'ına yazılmaz. Eski sürümler eski şifreli sırları da içerir; saklama politikası bunları kapsamalıdır.

Yönetim UI'sı deployment güven sınırını genişletemez:

- `ATLAS_ALLOWED_INTEGRATION_HOSTS`: bağlantıya izin verilen tam sunucu adları.
- `ATLAS_ALLOW_PRIVATE_INTEGRATION_HOSTS`: aynı izinli adlardan özel ağ adreslerine çözümlenmesine ayrıca izin verilenler.
- `ATLAS_LDAP_CA_FILE`: LDAP için deployment tarafından yönetilen özel CA dosyası.
- `ATLAS_TEST_EMAIL_RECIPIENTS`: üretim dışı ortamda izinli test alıcıları.

Ağ hedefi ad ve DNS çözüm sonucu ile doğrulanır. HTTPS/LDAPS sertifika doğrulaması kapatılamaz. Düz HTTP AI hedefi yalnız ayrıca izinli yerel/özel hedefte kullanılabilir. AI HTTP istemcisi yönlendirme ve ortam proxy'si kullanmaz. Bu kontroller ağ seviyesinde egress politikası yerine geçmez; DNS ve izinli sunucular deployment güven sınırının parçasıdır.

## LDAP/AD

Ayarlar: `enabled`, `url`, `bind_dn`, `base_dn`, `start_tls`, `user_dn_template`, `user_search_base`, `group_search_base`, `user_filter`, `group_filter`, `timeout_seconds`; ayrıca `username_attribute`, `display_name_attribute`, `email_attribute`, `department_attribute`, `title_attribute`, `manager_attribute`, `membership_attribute`. Servis parolası `secrets.bind_password` alanındadır. `ldaps://` doğrudan TLS; `ldap://` ise **TLS sertifikası doğrulanan StartTLS** kullanır. 389 bağlantısında `start_tls=false` reddedilir; servis parolası TLS'den önce gönderilmez. Referral takibi kapalıdır. Dizin özniteliklerinde parola/sır alanları, wildcard veya keyfî şema sorgusu kabul edilmez.

Varsayılan kullanıcı önizleme filtresi `(&(objectClass=user)(sAMAccountName=*{query}*))`, grup filtresi `(&(objectClass=group)(cn=*{query}*))` olur. Arama metni escape edilir. Login sorgusu önizleme wildcard'ından bağımsız, seçilmiş kullanıcı özniteliği üzerinde **tam eşleşmedir**. Kullanıcı bind'i için `user_dn_template` verilmişse `{username}` yerleştirilir; aksi halde dizindeki DN kullanılır. AD için kurumun gerçek şeması ve servis yetkileri doğrulanmalıdır.

Base DN boşken RootDSE `defaultNamingContext`/`namingContexts` okunur. Tek/default kapsam varsa kullanılabilir; birden fazla kapsamda varsayılan yoksa açık seçim gerekir. Seçilen arama tabanı yapılandırılmış/keşfedilmiş kapsamın altından gelmelidir. Kullanıcı ve grup arama tabanları ayrı tanımlanabilir.

`authenticate_ldap(username, password)` boş parolayı reddeder. Servis bind'i ile tekil kullanıcı kaydı bulunur; kullanıcı DN'i ve girilen parola ile yeniden bind yapılır. TLS/bind/arama hatasında yerel parola yöntemine düşülmez. LDAP giriş yöntemi önceden sağlanmış, etkin `identity_source='ldap'` hesabı gerektirir. Yerel ve LDAP giriş seçimi ayrıdır.

LDAP kullanıcı oluşturma, dizine gerçek servis bağlantısı kurup `entryUUID` veya `objectGUID` değerini `LDAPIdentity` ile eşler. Kullanıcı adı/e-posta değişikliği başka bir dizin kimliğine otomatik bağlanmaz. Sabit dizin kimliği yoksa hesap sağlama reddedilir. Mevcut yerel hesap, resmî referans kişi veya aynı adlı çalışan otomatik birleştirilmez. Gerçek dizin aktarımı `identity_source='ldap'`, kullanılamaz yerel parola ve `profile_kind='LDAP'` ile hesap oluşturur.

Arama önizlemesi en fazla 100 kaydı; ad, kullanıcı adı, e-posta, bölüm, unvan, yönetici DN'i, grup bilgisi ve **yalnız metadata olan** rol ipucunu gösterir. Önizleme hiç kullanıcı veya rol oluşturmaz. Paket arayan gerçek yöneticiye, yapılandırma sürümüne ve 15 dakikalık süreye bağlıdır. Aktarım her kişi için `subject`, `org_node`, `role` ister. Teknik yönetici sıradan `EMPLOYEE` sağlayabilir; iş yönetimi rolleri gerçek direktörün hedef organizasyon kapsamını gerektirir. Değişmiş ayar, süresi geçmiş paket, yerel kullanıcı adı çakışması, kapalı dizin hesabı, başka aktörün paketi veya eksik onay atomik olarak reddedilir. Mevcut eşlenmiş hesabın rol/kapsam değişikliği normal kullanıcı yönetimi akışına gider. Bölüm/unvan/grup bilgisi `ldap_metadata` olarak saklanır ve kendiliğinden yetkiye dönüşmez.

Grup arama önizlemesi kullanılabilir; grubun bütün üyelerini otomatik sağlama veya grup–iş rolü senkronizasyonu bulunmaz. Grup filtresi bir otomatik yetki politikası değildir.

LDAP bağlantı testi gerçek servis bind'ini, TLS doğrulamasını ve Base DN okumasını sınar. Bu test kullanıcı parolalarını toplamaz ve herhangi bir kişiye rol vermez.

TLS/bind başarısızlığından sonra LDAP soketini kapatma hatası asıl sonucu maskelemez. Kapatma en iyi çaba ile yapılır; sertifika doğrulama hatası kullanıcıya kontrollü 400 yanıtı olarak ulaşır. Süresi geçmiş sertifika için doğrulama kapatılmaz ve kimlik bilgileri TLS'den önce gönderilmez.

## SMTP ve kalıcı posta akışı

Ayarlar: `enabled`, `host`, `port`, `username`, `from_email`, `use_tls`, `use_ssl`, `timeout_seconds`; sır `secrets.password` olur. STARTTLS ile TLS seçeneklerinden tam biri etkin olmalıdır. Sertifika doğrulamasını devre dışı bırakma seçeneği bulunmaz.

`deliver_email(recipient, subject, body, message_id=None)` ve `send_email(...)` gerçek SMTP adaptörüdür. Entegrasyon kapalıysa yapılandırma hatası verir; konsola yazıp teslim edilmiş gibi davranmaz. Üretim dışı ortamda alıcı deployment test listesinde bulunmalıdır. Konfigürasyon testi, belirtilen test kutusuna gerçek kısa bir test iletisi gönderir.

Domain ataması, uygulama içi bildirim ve outbox kaydı `core` uygulamasında kalıcı tutulur. Worker bu adaptörü çağırır. SMTP kabulü alıcı tarafından okunma ya da son teslim garantisi değildir. Sağlayıcı kabulünden sonra yanıt kaybı belirsiz sonuç yaratabilir; bu durumlarda kontrolsüz yeniden gönderim yapılmamalıdır. Aynı `Message-ID` tek başına alıcıda tam bir kez teslim garantisi sağlamaz.

Yönetici kalıcı işlem listesinden `FAILED` bir işi; posta için ayrıca `WAITING_CONFIGURATION`/`BLOCKED` kaydını tekrar başlatabilir. `UNKNOWN` posta kaydında olası önceki teslim ve mükerrer ileti riski açıkça gösterilir; API `acknowledge_unknown: true` ister. Yeniden başlatma satır kilidi altında durum doğrulaması, eski lease'i geçersiz kılma, sınırlı deneme sayacını yeniden açma ve audit olayı ile yapılır. Çalışan veya tamamlanmış iş tekrar başlatılamaz. Teknik liste rapor payload'ı, kaynak başlığı veya e-posta gövdesi döndürmez.

## AI sağlayıcı adaptörü, bütçe ve rapor sürekliliği

AI ayarları OpenAI uyumlu `chat/completions` protokolü içindir. **Ortak model ayarı** `/settings/ai` içinde `model`, `temperature`, `timeout_seconds`, `max_input_tokens`, `max_output_tokens`, `daily_token_limit`, `daily_user_token_limit`, `input_price_per_million`, `output_price_per_million` taşır. Başlangıç çıkış sınırı 4096 token, süre sınırı 180 saniye, sıcaklık 0.3'tür; sıcaklık 0–2 aralığında ve AI süresi en fazla 180 saniye olabilir.

**Bağımsız bağlantı profili** ad, `config.enabled`, `config.provider='openai-compatible'`, `config.base_url` ve `secrets.api_key` taşır. Her profil ayrı şifreli yapılandırma sürümüne ve bağlantı testine sahiptir. Model/bütçe ayarı profil içine tekrar yazılmaz; ortak sekmede yönetilir. İki farklı anahtarı olan aynı endpoint ayrı profiller olabilir. Profil bir sır havuzu değildir; anahtarlar API'den geri okunmaz ve bir profildeki anahtar değişimi diğerini etkilemez. En fazla 8 etkin profil desteklenir. Silme arşivlemedir; varsayılan profil önce başka bir bağlantı seçilmeden arşivlenmez. Bağlantı testleri profile özeldir; ortak model ayarı değişirse eski test başarı rozeti geçersiz olur. Yalnız varsayılan seçimi değiştirmek diğer bağlantıların model testini geçersiz kılmaz.

Yerel izinli modelde anahtar gerekmeyebilir. Adaptör `max_tokens` destekleyen bu protokolü kullanır; farklı sağlayıcı protokolü ayrı adaptör gerektirir. Base URL hem kök API yolu hem tam `/chat/completions` endpoint'i olabilir; son parça iki kez eklenmez.

`selected_ai_snapshot()` seçili `profile_id`, bağlantının `configuration_version` değeri ve ortak `settings_version` değerini döndürür. Rapor işi bu üç değeri kalıcı payload'ında saklar. `generate_ai_report(..., profile_id=..., configuration_version=..., settings_version=...)` tam bu sürümleri kullanır. Sonradan varsayılan bağlantının, anahtarın, endpoint'in veya modelin değişmesi kuyruktaki işi yeni sağlayıcıya taşımaz. Hiç bağlantı yokken alınan `{profile_id:null, configuration_version:0, settings_version:0}` daha sonra bağlantı açılsa bile kurallı rapor üretir. Arşivlenmiş bir bağlantıya ait iş sessizce başka profile yönlendirilmez.

`generate_ai_report(actor, sources, report_kind='weekly', request_id='', ...)` yalnız çağıranın güncel erişim kontrolünden geçirdiği kaynak snapshot'larını kabul eder. Kaynaklar ilk/son erişim kontrolünü yapan `core` rapor servisi tarafından sağlanır. Adaptör yeni yetki, atama veya yayın kararı vermez. Kaynak açıklamaları güvenilmeyen içerik olarak işaretlenir. JSON çıktı şeması ve kaynak kimlikleri doğrulanır; var olmayan kaynağa atıf yapan çıktı yayımlanmaz. Bununla birlikte anlamsal doğruluk insan önizlemesi gerektirir.

Gönderilen seçki en fazla 50 kaynak, kısa başlık/açıklama ve durum alanlarıyla sınırlanır. Giriş için UTF-8 baytlarından hesaplanan muhafazakâr token tavanı kullanılır; bu sayı sağlayıcı ölçümü gibi sunulmaz. En fazla bir dış çağrı yapılır; sonsuz yeniden deneme bulunmaz. Çıkış ve süre sınırları uygulanır.

`PROJECT_*` yönetici özetlerinde başlık/açıklama başlangıçta 100/180 karakterle kısaltılır; mevcut giriş bütçesine sığması için sırasıyla 80/120, 60/80 veya 40/40 sınırı uygulanabilir. Kaynak kimlikleri/durumları korunur, `project_metrics` JSON'u kesilmez. Tam kaynaklar rapor kaydında kalır; sonuca `context_abridged` ve kullanılan `ai_context` sınırları eklenir. Proje çıktısı, haftalık raporla aynı şekilde yapılandırılmış `max_output_tokens` değerini en çok **4096 token** tavanıyla kullanır; modelden en çok 150 Türkçe kelime ve üç kaynak atfı istenir. Tam kaynak dizinini sistem ayrıca ekler. Gerçek yeni proje raporu 2048 sınırında `output_truncated` döndürdüğü için projeye özel alt tavan kaldırılmıştır; 4096 ile açılan son yeni UI raporu sağlayıcı çağrısından önce `budget_or_request_limit` nedeniyle kurallı taslağa geçti; bütçe artırılmadı veya atlatılmadı. Proje kapanışının canlı AI başarısı bu koşuda doğrulanamadı. [Gerçek sonuç](../../tests/artifacts/project-ai-live-check.json). Normal haftalık raporun mevcut giriş/çıkış sınırı değişmez. İlk kısaltma sürümünde 20 kayıtlı örnek kaynak üzerinde dış istek ve ledger yazımı yapmadan ölçülen giriş tavanı **5847/6000** oldu; bu sağlayıcı token ölçümü değildir.

Bütçe rezervasyonu PostgreSQL satır kilidi ile bütün worker'lar arasında atomik yapılır; günlük toplam ve kullanıcı bütçesi aşılırsa sağlayıcı çağrılmaz. Kullanım `AIUsage` ile kalıcı tutulur. Aynı aktör, işlem türü ve dolu `request_id` tekildir. Kaynakların/sürümlerinin ve yapılandırmanın hash'i değişirse aynı iş kimliği ile yeni çağrı yapılmaz. İş tekrarında kayıtlı sonuç kullanılabilir; kullanmadan önce ve rapora yazmadan önce domain servisi güncel erişimi tekrar doğrular. Devam eden/belirsiz çağrı körlemesine tekrarlanmaz. Dahili sonuç JSON'u denetim veya kullanım listeleme API'sine verilmez.

Sağlayıcı `prompt_tokens` ve `completion_tokens` döndürürse ölçüm `provider` olarak saklanır. Usage yoksa değerler **null/bilinmiyor** kalır; sıfır tüketim iddia edilmez. Fiyatlar tanımlıysa maliyet, çağrıdaki fiyat snapshot'ıyla hesaplanan USD tahminidir; sağlayıcı faturası değildir. Bilinmeyen fiyat null kalır. Belirsiz dış çağrıda ihtiyatlı bütçe rezervasyonu tutulur.

Adaptör sonucu `status`, `markdown`/`text`, `mode`, `citations`, `usage` taşır. Başarılı AI çıktısı `mode='AI'` olur. Kapalı sağlayıcı, bütçe/uzunluk sınırı, boş kaynak veya başarısız çağrıda boş Markdown ve `mode='RULE_BASED'` döner. Core servis kaynaklı kurallı rapor oluşturur ve AI kullanılmadığını belirtir. Böylece AI sağlayıcısının yokluğu iş yönetimini ve rapor kaydını durdurmaz.

Başarısız çağrının bilinen nedeni sabit `failure_code` ile döner: `output_truncated`, `invalid_json`, `invalid_citations`, `invalid_response` veya `provider_error`. `provider_diagnostics` yalnız izinli `finish_reason`, içerik karakter sayısı ve JSON geçerliliği içerir; sağlayıcının metni, düşünme içeriği veya hata gövdesi açıklanmaz. `ai_context.output_token_limit` uygulanan tavanı gösterir. Başarısız sonuç da kullanım kaydına yazılır; aynı belirsiz iş tekrar çağrılmaz, yeni deneme için açıkça yeni rapor istenir. Token tüketimi belirsizse rezervasyon korunur.

Başarılı AI metninin sonuna uygulama iki ayrı dizin ekler: **Dahil edilen kaynaklar (sistem kaydı)** yetkili seçkideki tüm kaynak kimliklerini/başlıklarını; **AI tarafından atıf yapılanlar** yalnız modelin döndürdüğü ve seçkiyle doğrulanmış atıfları gösterir. Sistem dizini modelin bütün kaynakları gerekçelendirdiği iddiası değildir. Modelin değiştirilmemiş metni `ai_original_text`, atıfları `citations` ve sistem seçkisi `included_sources` alanlarında ayrıdır. Kalıcı iş tekrarı kayıtlı sonucu kullanır; dizin ikinci kez eklenmez.

Gerçek bağlantı testi modele kısa bir istek gönderir; bunun tokenları da ledger'a yazılır. Sahte başarı sonucu üretilmez. Kullanım kaydı profil, bağlantı sürümü ve ortak ayar sürümünü içerir. Bütçe bütün bağlantılar arasında ortak satır kilidiyle korunur. Kullanım API'si `from`/`to` için `YYYY-MM-DD`, ayrıca `model`, `operation` ve `profile_id` filtrelerini destekler. Ölçümü bilinmeyen çağrı sayısı toplamlarda ayrıca yer alır.

## Teams ve gözlemleme

Teams sekmesi sırları güvenli biçimde saklayabilir; ilk adaptör gerçek Teams gönderimi yapmaz. Etkinleştirildiğinde bağlantı testi açık başarısız/henüz hazır değil sonucu verir. Kurumsal pilot adaptörü, onaylı hedef ve gerçek gönderim doğrulanmadan hazır kabul edilmez.

Yönetim ayarı, bağlantı testi ve kullanıcı işlemleri core `AuditEvent` ile izlenir. Teknik adminin genel denetim listesindeki payload metadata ile sınırlıdır; hassas vaka/proje açıklamaları dönmez. Bu liste bir uygulama debug/error log toplayıcısı değildir. Dağıtımın teknik log işletimi ayrıca yönetilir.

## Doğrulama

`python backend/manage.py test administration.tests --noinput --verbosity 1` komutu bu katmanı PostgreSQL üzerinde sınar. Testler şifreleme/sır geri okumama, eski ayar ve kullanıcı sürümü, eksik bootstrap anahtarı, kapalı entegrasyon, LDAP/TLS ve izinli ağ sınırı, AI kullanım/maliyet/atıf, bütçe, kalıcı iş tekrarında ikinci ücret doğmaması, yetki reddi, kullanıcı sağlama, sır içermeyen audit, iş metadata'sının güvenliği, sekmesiz ayar güncellemesinin güvenli reddi ve belirsiz postada açık yeniden gönderim onayını kapsar. Güncel yürütme sonucu QA raporuyla birlikte değerlendirilir.

Otomatik testlerde dış sağlayıcı adaptörü kontrollü taklitlerle sınanır. **18 Kasım 2026 tarihinde gerçek LDAP ve AI bağlantıları ayrıca denendi; her ikisi de `CERTIFICATE_VERIFY_FAILED: certificate has expired` nedeniyle doğrulanamadı.** Sertifika doğrulaması kapatılmadı ve bağlantılar hazır kabul edilmedi. Kurumsal sertifika zinciri düzeltilip aynı doğrulanan bağlantı testleri başarıyla tamamlanmalıdır. Gerçek SMTP teslimi ayrıca sınanmalıdır. Test sonuçlarında parola veya API anahtarı yayımlanmaz.
