# Atlas çalışan sürümün kapsamı

18 Kasım 2026 · Yerel geliştirme sürümü. Onaylı Revizyon 3 hedefi [uygulama planında](UYGULAMA_PLANI.md), testin gerçek kapsamı [QA raporunda](QA_REPORT.md) tutulur. Bu belge ilk çalışan sürümü ve sonraki işi ayırır; üretim kabulü vermez.

## Çalışan uçtan uca kapsam

| Alan | Mevcut davranış |
| --- | --- |
| Kimlik ve yetki | Yerel parola girişi, LDAP adaptörü ve süreli aktarım önizlemesi, cookie/CSRF, rol + organizasyon + kaynak ilişkisi; teknik adminin iş yetkisi ayrı |
| Direktör görünümü | Dört KPI, kritik/geciken gündem, yönetici seçimine bağlı sertifika uyarı eşiği ve unitlere göre filtre; 7 unit, 7 yönetici alt ekibi, 37 kişilik referans/demo rehberi |
| Projeler | Kişisel taslak, PM'ye gönderim, gerekçeli sürüm/karar, kontrollü yayın, kaynak talebi/kabulü, görev/katkı ve kapanış |
| Unit işleri | Hiyerarşik atama, kişisel işin resmîleştirilmesi, alt iş ve üst sorumluluğun korunması, bağımsız sonuç kabulü |
| Vakalar | Unit Head veya açık yetkiyle açılış, çalışan bildirimi, tek vaka altında ekip aksiyonları, ayrı kapanış doğrulaması |
| SLA | 24 saat / 7 takvim günü / 1 takvim ayı başlangıç politikaları; sürümlü değişiklik, ilk termin ve ihlal geçmişi, tekilleştirilmiş uyarı |
| Ekipler arası paylaşım | Yönetici/görev ve referans/demo ayrımlı sayfalı kişi rehberi, gönüllü uzmanlık, kaynak erişimini açmayan kart; proje içerik onayı ve hedef kitle yayın onayı ayrı |
| Anons ve etkinlik | Hedef ekipli anons/yayın; etkinlik/davetli, tek/çok seçimli isimli anket, RSVP ve gerçek katılım ayrı |
| Sertifikalar | Süreli/süresiz beyan, yönetici önem/doğrulama/uyarı eşiği, yaklaşan bitiş gündemi |
| Rapor | Erişimle süzülen ekip yıldızları + zorunlu adaylar, kaynak sürümlü snapshot, bağlantı/ortak model sürümüne sabitlenmiş AI işi veya açık kurallı fallback, Markdown ve tarayıcı PDF; onaylı raporu üst yönetim salt okunur görür |
| Ayarlar | Kullanıcılar/roller, proje yetkileri, SLA, LDAP keşif/arama/açık aktarım, SMTP, bağımsız AI bağlantı profilleri ve ortak model/bütçe ayarı; bağlantı testleri, token/maliyet dönem/profil filtresi, audit ve kalıcı kuyruk |
| Arama ve bildirimler | Yetkiyle süzülen PostgreSQL tam metin/önek araması, Türkçe harf/aksan sadeleştirme; alıcıya ve güncel kaynak erişimine bağlı okundu/okunmadı filtresi ve toplu okundu işlemi |
| Veri paylaşımı | Kapsamlı, iptal edilebilir salt okunur JWT API ve oturum korumalı Swagger/OpenAPI |
| Test ortamı | Yalnız açık test/demo bayrağında God Mode; kullanıcı simülasyonunda bypass kapanır, gerçek/etkin aktör audit'te ayrılır |
| Kesinti ve işletim | PostgreSQL job/outbox, 240 saniyelik rapor işi lease'i ve fencing, sürüm ve idempotency; yerel yedek/ayrı veritabanına geri yükleme deneyi |

Arayüz Penpard'ın görsel yaklaşımını, Türkçe metinleri ve ortalanmış işlem pencerelerini kullanır; Atlas'ın kaynağı, portları, veritabanı ve kimliği ayrıdır. Yerel başlangıç komutu ve demo rolleri [README](../README.md) içindedir.

Organizasyon, doğrulanan şemaya ait kişi/ekip adlarını `OFFICIAL_REFERENCE`, açıkça kurgusal örnekleri `DEMO` olarak gösterir. 37 kişi tam kurumsal kadro değildir; eksik kadro için dolgu isim üretilmez. Aynı kişinin iki unit yönetmesi tek hesapta iki görevdir. Bilinmeyen e-posta boş kalır; demo giriş alias'ı olmayan referans kişilerin parolası kullanılamaz. `ICT-CS-*` kodları Atlas içi eşleme anahtarlarıdır. Ayrıntılar [rehber servisindedir](services/DIRECTORY_SEARCH_NOTIFICATIONS.md).

Teknik `admin` hesabı iş rolü veremez. İş rolü yönetimini deneyebilmek için seed'de teknik ve direktör yetkileri açıkça bir arada verilen `fulladmin` hesabı bulunur; kendi erişimini değiştirme ve kendi projesini onaylama engelleri burada da sürer. Kurumsal ilk hesap sağlama bu sentetik hesapların kopyalanmasıyla yapılmaz.

## Kurumsal pilotta tamamlanacaklar

- Referans rehberini yetkili kurum verisiyle tamamlama ve gerçek kimlikleri sağlama; organizasyon düğümlerini oluşturma/taşıma ve toplu devir için yönetim akışı. Profil düzenleme ağaç taşıma değildir. LDAP aktarımı referans kişiyi aynı ad/e-posta üzerinden otomatik birleştirmez.
- Kurum LDAP/AD sertifika zinciri, servis bind'i, arama kapsamı, sabit dizin kimliği ve gerçek kullanıcıyla giriş. RootDSE keşfi, kullanıcı/grup önizlemesi ve seçili kişileri açık rol/kapsamla aktarma uygulanmıştır; 18 Kasım canlı testinde StartTLS sertifikası süresi dolduğu için bağlantı doğrulanamadı; TLS doğrulaması korundu. Grup üyeliğinden otomatik iş rolü sağlama ve sürekli pasifleştirme senkronizasyonu uygulanmış değildir.
- Onaylı SMTP test kutusunda gerçek teslim; bağlantı testi tek başına alıcıya teslim kanıtı değildir. Yapılandırılmamış bildirimler kalıcı kuyrukta bekler.
- Onaylı model endpoint'i, erişim anahtarı, kurum veri sınıfı ve canlı usage/maliyet kanıtı. Bağımsız profiller, test, bütçe ve sürüm sabitleme uygulanmıştır; 18 Kasım canlı testinde iki profil de süresi dolmuş TLS sertifikası nedeniyle doğrulanamadı; TLS doğrulaması korundu. Mevcut demo AI bağlantısızken açıkça kurallı rapor üretir. Gerçek AI kullanıldı iddiası yoktur.
- Kurum yedek/saklama hedefi, TLS/production sunucusu, izleme ve eşzamanlı kullanıcı yük ölçümü. Yerel restore deneyi kurumun RPO/RTO kabulü değildir.
- Yöneticiyle 30 saniyede konu bulma ve rapor hazırlama süresini ölçme. Üç etkileşim bir ürün hedefidir; her formun tamamının üç tık sürdüğü iddia edilmez.

## Sonraki ürün fazları

Teams ve kurumsal takvim, MCP adaptörü, güvenli belge/görsel yükleme ve galeri, mahremiyet tasarımlı anonim geri bildirim, bütçe ve ürün/lisans yenileme, ağırlıklı kilometre taşı, aylık tarihsel snapshot ve PPTX/sunucu PDF çıktısı henüz uygulanmadı. Direktörün doğrudan proje başlatmasına özel ayrı charter politikası kapalıdır; sıradan direktör rolü otomatik PM onayı vermez. Mesai/tatil/duraklama takvimi mevcut 7/24 SLA hesabına eklenmiş değildir.

Rapor dönem filtresi yıldız seçkisini belirler; kayıtların güncel snapshot'ı kullanılır. Bütün işlerin geçmiş günlük durumunu dönem içinde yeniden kuran tarihsel analitik değildir. İsimli ankette sonuçlar yetkiyle görünür; anonimlik vaat edilmez.

## Doğrulama kaydı

18 Kasım 2026 tam PostgreSQL koşusunda **193 test ve 41 alt senaryo, 13,88 saniyede** geçti; hata veya atlanan test yoktur. `ldap3/pyasn1` kaynaklı iki deprecation uyarısı [backend artifact'inde](../tests/artifacts/backend-tests.json) kayıtlıdır. Ayrı canlı rol oturumlarıyla **46 HTTP kabul testi, 21,621 saniyede** geçti ([kanıt](../tests/artifacts/api-acceptance-ui-org-overhaul.json)). Frontend tip kontrolü, üretim derlemesi ve **9 istemci testi** de [geçti](../tests/artifacts/frontend-tests.json). Bunlar tanımlı yerel senaryoların kanıtıdır; kurumsal LDAP/AI teslimi, bütün olası akışlar veya üretim yükü için garanti değildir. Ayrıntılı kapsam ve kalan kabul [QA raporundadır](QA_REPORT.md).

## Bilinen bağımlılık sınırı

18 Kasım 2026 taramasında `npm audit --omit=dev` **0 bulgu** verdi. Tam taramada geliştirme araç zincirindeki `picomatch <=4.0.7` için [GHSA-fc5q-39xc-vjpf](https://github.com/advisories/GHSA-fc5q-39xc-vjpf) ve onu kullanan paketlerle birlikte **6 high** kaydı kaldı. Kurulu güncel registry sürümü için yamalı sürüm bulunmadığından otomatik eski Vite/Vitest sürümüne dönüş uygulanmadı. Bu paketler production frontend bundle'ının sunucu runtime'ı değildir; geliştirme sunucusu loopback'te tutulur ve güvenilmeyen glob girdisi kabul edilmez. Araç zinciri güncellemesinde yeniden taranmalıdır. Bu sonuç bütün bağımlılıkların veya uygulamanın zafiyetsiz olduğu anlamına gelmez.
