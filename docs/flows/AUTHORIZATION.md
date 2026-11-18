# Atlas kimlik ve yetkilendirme sözleşmesi

Yetki, etkin hesap + organizasyon kapsamı + kayıt ilişkisi + işlem izniyle belirlenir. UI düğmesi yetki kanıtı değildir; karar `backend/core/policy.py` ve sunucu akışlarında uygulanır.

## Kimlik ve kapsam

- Tarayıcı `/api/v1/auth/csrf/` ile CSRF alır; `auth/login/` yerel veya LDAP yöntemiyle oturum açar. Yanlış/pasif hesap 401; LDAP başarısızlığı yerel girişe sessizce dönmez. `auth/logout/` oturumu kapatır.
- Yerel/LDAP kimlik sağlama ve gerçek dizin bağlantısının sınırları [entegrasyon sözleşmesindedir](../services/INTEGRATIONS.md); kurumsal LDAP doğrulanmış varsayılmaz.
- `RoleGrant`, etkinlik/süre ve organizasyon düğümünü taşır. `includes_descendants=false` yalnız o düğümü kapsar; kurum kodu öneki yetki sağlamaz.
- Unit işleri organizasyon kapsamından; proje işleri PM/proje yetkisinden; vaka aksiyonları vaka koordinasyonundan yönetilir. Birden fazla rol, izinli kapsamları birleştirir; her işleme ait kısıtlar korunur.
- Proje yönetimi atanmış PM, `PMAppointment.governing_org` Unit Head'i veya süreli proje yetkilisindedir. Çalışan veren Unit Head proje yönetimi kazanmaz.
- Proje onayı gerçek başvuru/değişiklik yazarından farklı kullanıcı ister. Direktörün okuma rolü kendiliğinden yayın onayı değildir; PM pasifleşirse yetkili üst yönetim ayrı devir akışını kullanır.
- Proje özeti, tam ayrıntı ve kaynak yöneticisinin kendi çalışanı katkısı ayrı süzülür. Gönderilmemiş taslak kişiseldir; paylaşım kartını görmek kaynak kaydını açmaz.

## İşlem, worker ve dış API

- `DomainViewSet` yazmayı transaction içinde yürütür; `locked()` güncel `version` ister. Eski sürüm 409; erişilemeyen kayıt 404/403 döner.
- `X-Request-ID` tekrarında aynı içerik ve güncel erişim kontrol edilir; farklı içerik 409, sonradan değişen yetki 403 verir. Tekrar CSRF veya kayıt yetkisini atlatmaz.
- Rapor worker'ı aktörü DB'den yeniler; kaynak/özet kapsamı, erişim parmak izi ve lease'i sonuç yazmadan tekrar doğrular. Pasif hesap eski kuyruğu kullanarak rapor yayımlayamaz.
- `ScopedJWTAuthentication`, imza, issuer/audience, süre, istemci etkinliği/token sürümü ve kullanıcı etkinliğini kontrol eder. Dış token yalnız GET/HEAD/OPTIONS, izinli okuma scope'u ve daraltılmış organizasyon kapsamıyla çalışır; admin/auth/token yönetimi kapalıdır.
- System Admin teknik yetkisi otomatik iş içeriği yetkisi değildir. İş rolü sağlama ve teknik kimlik yönetimi sınırı entegrasyon belgesinde açıklanır.
- God Mode yalnız `test/demo` ve deployment bayrağıyla çalışır. Başka kullanıcı görünümünde bypass kapanır; gerçek ve etkin aktör ayrı audit edilir. Üretimde test bayrağı erişim açmaz.

## Kod ve doğrulama

- Kod: `backend/core/policy.py`, `authentication.py`, `middleware.py`, `views.py`, `services.py`; UI `frontend/src/lib/auth.tsx` ve kaydın sunucudan gelen `permissions` alanını kullanır.
- Testler: `backend/core/tests/` altındaki `test_policy.py`, `test_session_security.py`, `test_test_mode.py`, `test_continuity.py`, `test_worker.py`, `test_latest_flows.py::SelfServiceAndApiScopeTests`; ayrıca `tests/api_acceptance.py` rol, kapsam, JWT ve oturum testleri.
- K01–K05, K13–K18, K20, K28, K31 ve K33 ile ilişkilidir. Sonuçlar [QA raporunda](../QA_REPORT.md) tutulur; bu sözleşme tek başına üretim/pilot güvenlik kabulü değildir.
