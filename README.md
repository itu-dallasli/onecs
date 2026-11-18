# Atlas

Atlas, Siber Güvenlik Direktörlüğü için ortak yönetim ve koordinasyon uygulamasıdır. Projeleri proje yöneticisi, unit işlerini organizasyon yöneticileri, vakaları yetkili vaka koordinasyonu yönetir. Aynı kayıtlardan direktör gündemi ve kaynaklı haftalık rapor üretilir.

Ürün kararları [Uygulama Planı](docs/UYGULAMA_PLANI.md), teknik tasarım [Mimari Tasarım](docs/MIMARI_TASARIM.md), doğrulama durumu [QA Raporu](docs/QA_REPORT.md) ve [Kabul Matrisi](docs/TEST_MATRIX.md) içindedir. Tasarım belgesindeki hedef kapsam, tek başına uygulanmış özellik kanıtı değildir.

Çalışan modüller, pilotta gereken bağlantılar ve sonraki fazlar [Uygulama Durumu](docs/IMPLEMENTATION_STATUS.md) belgesinde ayrılır. Bu sürüm yerel geliştirme ve yönetici demosu içindir.

18 Kasım 2026 doğrulamasında PostgreSQL üzerinde **193 backend testi ve 41 alt senaryo** ([kanıt](tests/artifacts/backend-tests.json)), ayrı rol oturumlarıyla **46 canlı HTTP kabul testi** ([kanıt](tests/artifacts/api-acceptance-ui-org-overhaul.json)) geçti. Frontend tip kontrolü, üretim derlemesi ve 9 API istemci testi de [başarılıdır](tests/artifacts/frontend-tests.json). Bu sonuçlar gerçek kurum LDAP/AI bağlantısının veya üretim yükünün doğrulandığı anlamına gelmez.

## Yerel kurulum

Gerekenler: Python 3.13, Node.js 22.12+, PostgreSQL 17. Penpard 3000 portunda kalır; Atlas 3100, API 8000 ve ayrı geliştirme veritabanı 55432 kullanır.

```bash
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt
cd frontend
npm ci
cd ..
```

`.env.example` dosyasını `.env` olarak kopyalayın. `ATLAS_SECRET_KEY`, `ATLAS_ENCRYPTION_KEY` ve yerel demo girişlerinin `ATLAS_DEMO_PASSWORD` değerini belirleyin. Anahtar üretmek için:

```bash
.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(48))"
.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Homebrew PostgreSQL 17 araçları mevcutsa yerel başlatıcı `.runtime/postgres` altında yalnız loopback dinleyen ayrı bir geliştirme kümesi oluşturur. Mevcut kurum/başka uygulama veritabanını değiştirmez. Bu kümenin yerel trust erişimi geliştirme içindir; üretim PostgreSQL’i kullanıcı/parola, ağ sınırı ve yedek politikasıyla ayrıca kurulmalıdır.

```bash
.venv/bin/python scripts/dev.py --seed
```

Uygulama: **http://localhost:3100**. Başlatıcı migration, referans organizasyon/demo seed'i ve Django kontrolünü çalıştırır; ardından API, worker ve frontend süreçlerini birlikte yönetir. Ctrl+C uygulama süreçlerini durdurur; veritabanı ve işler diskte kalır. Sonraki başlatmada aynı kayıtlar kullanılır. Veritabanını gerektiğinde `pg_ctl -D .runtime/postgres stop` ile durdurabilirsiniz.

Başlangıç rehberi, doğrulanan organizasyon şemasını **7 unit, 7 yönetici alt ekibi ve 37 kişi** ile temsil eder. Bu, bütün kurumsal kadro değildir. Gerçek kişi/ekip adları `OFFICIAL_REFERENCE`, kurgusal örnek çalışanlar `DEMO` olarak ayrılır; dolgu personel üretilmez. Hakan Tokay'ın iki unit görevi tek kişi ve iki yetki kaydıdır. Organizasyon kodları Atlas içi eşleme anahtarlarıdır; resmî LDAP kodu olduğu iddia edilmez. Ayrıntılar [rehber ve arama servisinde](docs/services/DIRECTORY_SEARCH_NOTIFICATIONS.md) bulunur.

## Demo hesapları

| Kullanıcı | Görev |
| --- | --- |
| `director` | Direktör ve tüm unitlerin yönetim özeti |
| `unithead` | Offensive Security unit yöneticisi |
| `teammanager` | Application Security Testing ekip yöneticisi |
| `employee` | AST çalışanı ve kişisel işler |
| `pm` | Security Management altında açıkça demo proje yöneticisi |
| `admin` | Teknik sistem yönetimi |
| `fulladmin` | Demo için açıkça tanımlı teknik + direktör yetkisi; başka kullanıcıların iş rollerini yönetir |
| `iamhead` | Ayrı unit yöneticisi; kapsam testleri |
| `iamemployee` | Açıkça demo IAM çalışanı; kaynak tahsisi ve kapsam testleri |

Tablodaki alias'lar yalnız yerel demo girişi sunar; parola `.env` içindeki `ATLAS_DEMO_PASSWORD` değeridir. Gerçek şema kişisinin adını gösteren alias, o kişinin kurumsal kimliğini veya parolasını doğrulamaz. Giriş alias'ı tanımlanmayan referans kişilerin yerel parolası kullanılamaz. Bu hesapları ve parolayı gerçek ortama taşımayın. System Admin iş verisini otomatik yönetmez; farklı roller ayrı oturumlarla denenir. Kurumsal giriş, yapılandırılıp test edilmiş LDAP bağlantısı ve sabit dizin kimliğiyle açık aktarım gerektirir.

Seed bu parolayı yalnız hesabı ilk oluştururken kullanır; sonraki çalıştırmalarda mevcut parolaları ve iş kayıtlarını sıfırlamaz. Eski dolgu rehberini tespit ederse otomatik silmek yerine işlemi reddeder; yedek ve yalnız yerel verinin temizlenmesi ayrı işletim kararıdır.

İş rolü düzenlemesi hem teknik kullanıcı yönetimi hem direktör kapsamı gerektirir. Bu ayrım `admin` hesabının kendisine veya bir başkasına sessizce iş yöneticiliği vermesini engeller. Demo `fulladmin` hesabında iki yetki başlangıçta açıkça tanımlıdır; bu kullanıcı da kendi rolünü değiştiremez veya kendi proje başvurusunu onaylayamaz. Gerçek ortamda ilk yetkili hesap kurumun onaylı sağlama sürecinde kurulur.

## Geliştirme ve kontroller

```bash
.venv/bin/python scripts/dev.py --check
.venv/bin/python -m pytest
cd frontend
npm run build
npm test
npm audit --omit=dev
```

Canlı HTTP kabul testleri ayrı rol oturumlarını ve CSRF davranışını kullanır; sentetik uygulama açıkken [test yönergelerine](tests/README.md) göre çalıştırılır. Testler demo verisine yeni kayıtlar ekleyebilir. Test kanıtları ve pilotta gereken ek doğrulamalar QA raporunda belirtilir.

## Yapı ve işletim

```text
backend/config/          Django ortamı ve yönlendirme
backend/core/            Organizasyon, policy ve domain akışları
backend/administration/  Ayarlar, LDAP, SMTP, AI ve kullanım kaydı
frontend/src/            React sayfaları, tasarım sistemi ve API istemcisi
scripts/                 Yerel başlatma ve işletim yardımcıları
tests/                   Bağımsız HTTP kabul senaryoları
docs/                    Plan, mimari, akışlar ve doğrulama kanıtı
.agents/skills/           Atlas'a özel tekrar kullanılabilir geliştirme akışı
```

Tarayıcı aynı origin üzerinden session cookie ve CSRF kullanır. Dış entegrasyon API’si JWT bearer ile salt okunur kapsam sunar. Uzun işlemler session yerine PostgreSQL job/outbox kayıtlarında tutulur. Worker’ın yeniden başlaması kaydı ortadan kaldırmaz; dış servisin yanıtı belirsizse bu durum ayrıca saklanır.

Entegrasyonlar başlangıçta yapılandırılmamıştır. Ayarlar ekranında sırlar maskelenir; bağlantı testi gerçek sonuç döndürür. Hedef sunucular deployment izin listesinde olmalıdır. LDAP/SMTP/AI ayarının kaydedilmesi testin geçtiği anlamına gelmez. LDAP keşif, önizleme ve açık kişi/rol aktarımı; AI için bağımsız bağlantı profilleri, ortak model/bütçe ayarları ve profil bazlı testler bulunur. Kuyruğa alınan rapor bağlantı ve ayar sürümlerine sabitlenir; worker lease'i 240 saniyedir. AI kullanılamıyorsa kaynaklı kurallı rapor hazırlanır ve canlı AI çıktısı olmadığı açık belirtilir. Yerel bağlantı ayarları şifreli kaydedildi. 18 Kasım gerçek testinde LDAP StartTLS ve iki AI profilinde süresi dolmuş TLS sertifikası hatası alındı; doğrulama devre dışı bırakılmadı. Bu nedenle kurum girişi, dizin aktarımı ve model erişimi henüz doğrulanamadı. [Canlı test kanıtı](tests/artifacts/live-integrations.json).

Penpard’ın görsel yaklaşımı referans alındı: açık gri zemin, beyaz kartlar, ince sınırlar, koyu gri ana aksiyonlar ve altın vurgu. Türkçe arayüz, ortalanmış işlem pencereleri, kapsamlı PostgreSQL araması ve okundu/okunmadı bildirim filtresi kullanılır. Atlas ayrı kaynak kodu, kimlik sistemi ve veritabanıyla çalışır.

Yerel yedekten ayrı veritabanına dönüş deneyi `scripts/verify_restore.py` ile çalıştırılır; [sonuç artifact'i](tests/artifacts/restore-check.json) tutarlı snapshot ve tablo sayımlarını içerir. Kurum yedek hedefi ve dış secret deposu ayrıca doğrulanır.

## Akış ve servis belgeleri

- [Organizasyon](docs/flows/ORGANIZATION.md), [Yetkilendirme](docs/flows/AUTHORIZATION.md), [Projeler](docs/flows/PROJECTS.md), [İşler](docs/flows/WORK.md), [Vakalar](docs/flows/CASES.md)
- [Rapor ve AI](docs/flows/REPORTS_AI.md), [Ekip paylaşımı](docs/flows/COMMUNITY.md), [Etkinlik/anket](docs/flows/EVENTS.md), [Sertifikalar](docs/flows/CREDENTIALS.md)
- [Entegrasyon servisleri](docs/services/INTEGRATIONS.md), [Rehber, arama ve bildirimler](docs/services/DIRECTORY_SEARCH_NOTIFICATIONS.md), [API sözleşmesi](docs/API.md), [OpenAPI YAML](docs/api/openapi.yaml)
- [Geliştirme ve agent katkıları](docs/DEVELOPMENT.md), [Güvenlik](SECURITY.md), [Atlas geliştirme skill'i](.agents/skills/atlas-domain-change/SKILL.md)

Gerçek kurum entegrasyonu, yük ölçümü ve kurumsal işletim kabulü tamamlanmadan üretim kabulü verilmez. Bilinen geliştirme bağımlılığı uyarısı [Uygulama Durumu](docs/IMPLEMENTATION_STATUS.md) içinde kayıtlıdır.
