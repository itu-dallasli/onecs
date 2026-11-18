# Atlas QA raporu

## Proje içgörüleri ve kişi iş yükü ek kabulü

18 Kasım 2026 · Yeni proje teslimat/anket/rapor akışı için **21/21 gerçek HTTP testi geçti**, 27,618 saniye; hata veya atlama yok. [Yeni koşu](../tests/artifacts/project-insights-acceptance.json), [kabul planı ve eşleme](testing/FEATURE_ACCEPTANCE.md). Testler PM/Unit Head ayrımı, iki seviyeli ağırlık, eksik veride `null`, davetli/sürümlü tek yanıt, insan rapor düzenlemesi, değişmez kaynak/hesaplanan skor, kapanış yayını, JWT organizasyon kapsamı ve kişi iş yükü gizliliğini doğruladı. Yeni raporlar açık `RULE_BASED` modunda gerçek worker ile tamamlandı; bu 21 test canlı AI başarısı sayılmaz.

**Özelliğin ayrı kaynak snapshot'ı da doğrulandı:** Başlangıç sürümü üzerine yalnız bu özellik değişiklikleri alınarak **234 backend testi + 45 alt senaryo** (19,598 saniye), **17 frontend testi**, strict TypeScript ve production build geçti. Strict OpenAPI üretimi uyarısız; migration drift kontrolü `No changes detected` verdi. Ayrı özelliğe ayrılmış geçici PostgreSQL veritabanı kullanıldı ve koşu sonunda kaldırıldı; canlı DB, seed ve servisler çalıştırılmadı. İki ldap3/pyasn1 deprecation uyarısı ve 543,22 kB entry bundle için Vite boyut uyarısı vardır (build 245 ms). Bu snapshot eşzamanlı LDAP ilk giriş, Atlas marka, dosya eki ve anons değişikliklerini içermez. [Ayrı snapshot kanıtı](../tests/artifacts/project-feature-snapshot.json) ilk 48 kaynak dosyasının `ddc2e453…` tree hash'ini kapsamıyla birlikte kaydeder; bu hash son commit'in tüm ağacı olarak sunulmaz.

Mevcut 46 senaryonun tekrarında **45 geçti, 1 gerçek AI raporu kaynak referansı kontrolü başarısız oldu**; 57,295 saniye, atlama yok. Model `AI` modunda yanıt verdi fakat seçilmiş kritik kaydın referansı metinde yoktu. [Başarısız koşu korunuyor](../tests/artifacts/api-acceptance-project-insights-regression.json). Sunucunun kaynak dizini düzeltmesinden sonra **yalnız ilgili test yeniden çalıştırıldı ve geçti**, 10,220 saniye: gerçek `AI` çıktısında snapshot'ın **9/9 kaynak referansı** korundu. [Hedefli son kontrol](../tests/artifacts/api-report-source-index-recheck.json). Böylece **67 farklı HTTP senaryosu** doğrulandı; bu ifade tek seferde yapılmış 67 testlik tam koşu anlamına gelmez.

Kaynak dizini, modelin her kaynak hakkında doğru çıkarım yaptığı iddiası değildir; modele verilen kayıtları görünür ve izlenebilir tutar. Ham AI metni ile sunucunun doğruladığı referanslar ayrılır. Kayıtlı LDAP için regresyon testi yalnız maskeli public cevap/yetkisiz okuma reddini kontrol etti; gerçek ayar, sır ve bağlantı değiştirmedi. Daha aşağıdaki 193/46/9 sonuçları önceki sürümün başlangıç kanıtıdır. Root'un **birleşik working tree** son koşusu **293 backend testi + 96 alt senaryo** (19,68 saniye) ve **24 frontend testi**, strict TypeScript/production build (271 ms) olarak geçti. Bu toplam bağımsız LDAP/marka çalışmasının henüz ayrı commit'lenmemiş değişikliklerini de içerir; bu özelliğin ayrı staged snapshot doğrulamasıyla karıştırılmaz. Farklı sürümlerin toplamları birbirine eklenmez. Entry bundle 551,28 kB için Vite uyarısı vardır; gerçek cihaz/yük gecikmesi ölçülmüş sayılmaz.

**Proje kapanış raporunun canlı AI başarısı doğrulanmadı:** Root'un sentetik kapanış projesindeki ayrı UI denemesinde 2048 çıkış sınırındaki yanıt `output_truncated` oldu. Son yapılandırılmış 4096 sınırıyla açık yeni istek, sağlayıcıya gönderilmeden `budget_or_request_limit` nedeniyle durdu. İkisi de açık `RULE_BASED` fallback ile `READY`/tamamlanmış job durumuna ulaştı. Bütçe artırma, sınırı atlama veya ek otomatik deneme yapılmadı. Genel haftalık test50'nin gerçek `AI`/9 kaynak başarısı bu proje denemesinin başarısı yerine sayılmaz. [Canlı proje sonucu](../tests/artifacts/project-ai-live-check.json), [UI](../tests/artifacts/ui-project-ai-report.jpg).

Yeni gerçek UI kontrollerini root yürüttü: kişi ayrıntısından yönetici işi oluşturma ve önceden seçilmiş kişiyle atama, çalışan profilinde iş yükü, PM ekip içgörüleri, haftalık Markdown düzenleme/yayımlama, insan tarafından incelenen kapanış skorları ve davetli çalışanın cevap değiştirmesi. Kaynak hesaplanan kalite/başarı değeri 75/88,5 korunurken incelenmiş değerler 80/90 olarak saklandı. 390 px görünümde doküman genişliği 390 px, form dialog genişliği 362 px gözlendi. Görsel/odak/diğer grafik varyasyonlarının tamamı otomatik HTTP kanıtına dahil değildir.

[Root UI kontrol kaydı](../tests/artifacts/project-ui-checks.json), CDC 52 / IAM 62 / OS 77 / SAA 42 ilerlemesinin ağırlıklı 58,25 değerini PM'nin beyan ettiği 62'den ayırdığını; sidebar tercihinin reload sonrası korunduğunu da kaydeder. Bütün reduced-motion, klavye çevrimi ve tema varyasyonları eksiksiz doğrulanmış sayılmaz.

Bu akışların ekranları: [ekip ağırlıklı ilerleme](../tests/artifacts/ui-project-team-progress.jpg), [düzenlenen haftalık rapor](../tests/artifacts/ui-project-report-reviewed.jpg), [insan incelemesi ve değişmeyen kaynak skoru](../tests/artifacts/ui-project-score-reviewed.jpg), [mobil kişisel iş formu](../tests/artifacts/ui-work-personal-mobile.jpg).

**Kabul verisi temizliği tamamlandı:** Bağımsız incelemede ilk geniş reverse-FK taslağı uygulanmadan kaldırıldı; kullanıcı/rol/cache temizliği kapsam dışına alındı. Ayrı PostgreSQL klonunda apply/preserve kontrolü **2,444 saniyede geçti**; ilk self-PROTECT hata denemesi tamamen geri alındı ve gerçek yaprak sırasıyla düzeltildi. Root onayı, servis durdurma ve preview sonrası **0600 izinli PGDMP yedeği** ardından yerel canlı exact dört koşu temizliği **2,314 saniyede geçti**. 47 QA projesi, 28 iş, 14 job ve 198 bildirim/outbox silindi; **29 korunan modelin tüm satır hash'leri aynı** kaldı: 38 kullanıcı, 56 rol kaydı, 7 öneksiz proje, gerçek LDAP/AI ayar/sırları, maliyet ledger'ı ve idempotency cache korundu. Pasif test kullanıcısı silinmedi. Root API/worker'ı yeniden başlatır. İki geçici klon veritabanı ve dört geçici dump dosyası kaldırıldı; son geri dönüş yedeği ignored runtime'da korunur. [Klon kanıtı](../tests/artifacts/cleanup-clone-proof.json), [yerel temizleme kanıtı](../tests/artifacts/cleanup-live-verification.json), [sınır ve yönerge](testing/CLEANUP.md). Bu dev verisi temizliği kurum RPO/RTO tatbikatı değildir.

**Güncel geri yükleme:** Kaynakta read-only consistent snapshot alınıp yeni disposable PostgreSQL veritabanına restore edildi; **62 tablo / 910 satır sayısı ve foreign key kontrolü geçti**, 0,824 saniye. Geçici restore DB silindi; dump 0600 izinle ignored runtime'dadır. [Yeni restore kanıtı](../tests/artifacts/restore-project-insights.json) dump'ın kendi migration kaydını taşır: core `0006_project_insights`, administration `0004_ldapmanagedgrant` dahil; daha sonra canlıda görülen `0007_record_extras` / `0008_attachment_purge` bu kanıtın kapsamı dışındadır. Önceki `restore-check.json` içeriği aynen korundu; aşağıdaki 53 tablo / 573 satır sonucu eski sürüme aittir.


18 Kasım 2026 · Resmî 7 unit organizasyonu + yeni arayüz/LDAP/AI profil sürümü · Yerel kabul

## Son doğrulama

Gerçek HTTP kabul koşusu **46/46 geçti; hata, başarısızlık ve atlanan test yok**. Koşu **21,621 saniye** sürdü ve **18 Kasım 2026 12:23:03 UTC** zamanında tamamlandı. API `http://127.0.0.1:8000`, arayüz `http://127.0.0.1:3100`, veri katmanı PostgreSQL'dir. Dokuz ayrı kullanıcı/cookie/CSRF oturumu kullanıldı; testler God Mode veya doğrudan veritabanı değişikliği kullanmadı. [Makine tarafından üretilen HTTP kanıtı](../tests/artifacts/api-acceptance.json).

| Katman | Sonuç | Kanıt ve sınır |
| --- | --- | --- |
| Backend | **193 test + 41 alt senaryo geçti**, 13,88 saniye | [backend-tests.json](../tests/artifacts/backend-tests.json), `.runtime/pytest-final.log`; PostgreSQL üzerinde gerçek transaction/kısıt testleri ve iki bağlantıyla worker yarışı. Haricî sağlayıcı çağrılarının bir bölümü adaptör testidir. |
| Gerçek HTTP | **46 geçti**, 21,621 saniye | [api-acceptance.json](../tests/artifacts/api-acceptance.json); çalışan, TM, UH, PM, PM'nin UH'si, direktör, teknik admin ve IAM kullanıcıları. |
| Frontend | **9 Vitest testi**, strict TypeScript ve production build geçti | [frontend-tests.json](../tests/artifacts/frontend-tests.json), 12:37:48 UTC; API istemci testleridir. Deep-link, görsel, klavye ve responsive davranışlar ayrıca tarayıcıdan doğrulanır. |
| PostgreSQL geri yükleme | **53 tablo / 573 satır eşleşti**, 0,839 saniye | [restore-check.json](../tests/artifacts/restore-check.json); tutarlı snapshot, custom dump, ayrı veritabanına restore, tüm tablo sayıları ve foreign key kontrolü. |
| API şeması | Strict şema üretimi uyarısız; migration kontrolü temiz | Entegrasyon liderinin son kontrolü; anonim ve oturumlu Swagger HTML erişimi ayrıca gerçek HTTP testinde geçti. |
| Yeni canonical veri | **37 referans/demo kişi, 7 unit, 7 alt ekip** başlangıcı | Seed/migration sonrası API + frontend + worker açıldı. 46 HTTP testinde yedi unit, yönetici isimleri ve referans aktör kimlikleri doğrulandı; root IAB oturumunda OS → AST → çalışan ayrıntısına kadar yeni ağaç doğrulandı. [Temiz başlangıç](../tests/artifacts/startup-smoke.json); iki AI profilinin restart sonrası şifreli saklanması da kontrol edildi. |
| Production npm bağımlılıkları | **0 audit bulgusu** | [Production audit çıktısı](../tests/artifacts/dependency-audit-production.json). Geliştirme bağımlılıklarındaki açık kayıt aşağıda belirtilmiştir. |

Bu sayılar farklı doğrulama katmanlarıdır; tek bir “bütün akışlar tamamlandı” yüzdesi üretmek için birleştirilmez. [Test matrisi](TEST_MATRIX.md) 20 yerel kabul akışını geçmiş, 20 maddeyi kalan varyasyon veya pilot nedeniyle kısmi olarak gösterir. Önceki sürümün 200 kişi/12 unit performans ve ekran kanıtı bu sürümün son görünümü sayılmaz. Yeni sürümün tarayıcı ve canlı bağlantı durumu aşağıda ayrı izlenir.

## Yeniden çalıştırma

Sentetik uygulama, PostgreSQL ve worker açıkken proje kökünden:

```bash
python3 tests/api_acceptance.py --base-url http://127.0.0.1:8000 --allow-mutations
```

Backend regresyonları:

```bash
.venv/bin/python -m pytest -q
```

Koşucu parolayı `ATLAS_DEMO_PASSWORD` ortam değerinden veya yerel `.env` dosyasından veri olarak okur. Parola, session cookie ve JWT token rapora yazılmaz. Yalnız loopback hedeflerine izin verir; benzersiz `QA-` başlıklarıyla sentetik kayıt oluşturur. Gerçek kurumsal veri üzerinde çalıştırılmaz. Worker kapalıysa raporun tamamlanma kontrolü başarısız olur; sahte başarıyla geçilmez. Ayrıntı [test yönergelerinde](testing/README.md).

## Yeni sürümün ek kabul kanıtı

- **Tam metin arama:** İş açıklamasında bulunan iki kelime ters sırayla sorgulandı; kayıt bulundu. Başlıkta bu kelimeler yoktu. Başka unit ve teknik admin aynı özel kaydı bulamadı. Kısmi başlık ve boş sorgu da kontrol edildi.
- **Bildirimler:** Yalnız alıcı bildirim ayrıntısını okuyup okundu/okunmadı yapabildi. İlgili kayıt read/unread filtreleri arasında doğru taşındı; başka kullanıcının GET/POST girişimleri reddedildi.
- **Resmî organizasyon:** Yedi unit ve yönetici isimleri; Emin İslam Tatlı, Emre Uzun ve Muhammed Eren Uygun referans kimlikleri ve AST ilişkisi gerçek API oturumlarıyla doğrulandı.
- **LDAP önizleme/aktarım sınırı:** Çalışan, TM, UH ve PM keşif/arama/import yapamadı. Uydurma batch aktarımı 404 verdi. Bu testler LDAP'a bağlantı başlatmadı; gerçek dizin sonucu içe aktarma backend adaptör testlerinde sınandı.
- **İki AI profili:** İki kapalı sentetik profil oluşturuldu; birinin sürüm değişimi diğerini etkilemedi. Eski sürüm reddedildi, profile özel model alanı ortak ayar sınırı nedeniyle reddedildi. Anahtar GET/audit'te görünmedi, çalışan profil/test/default uçlarına erişemedi. Sonunda yalnız bu kapalı test profilleri arşivlendi; default ve canlı bağlantı değiştirilmedi.

[Bu sürümün 46 HTTP testi](../tests/artifacts/api-acceptance-ui-org-overhaul.json), [önceki 41 testin korunmuş çıktısı](../tests/artifacts/api-acceptance-before-ui-org-overhaul.json). [UI kabul planı](testing/UI_SMOKE_PLAN.md) U01–U12 olarak hazırlanmıştır.

**Yeni tarayıcı kontrolünün yürütülmesi:** QA alt ajanında IAB kullanılamadı; native Chrome denemesi kullanıcı kontrolü değiştiğinde durduruldu, mevcut sekmeler değiştirilmedi. Aşağıdaki yeni UI kontrollerini root ajanı kendi IAB oturumunda gerçekleştirdi; QA bu ekran artifact'lerini ayrıca görsel olarak inceledi.

| Yeni UI kontrolü | Gerçek sonuç | Kanıt |
| --- | --- | --- |
| Merkezlenen kişi penceresi | 1052 × 1133 px viewport'ta dialog 900 × 961 px, x=76, y=85,85. Merkez sapması 1 px altında; arka plan inert ve body overflow hidden. Tab kapatma düğmesinde kaldı; Escape kapanışı sonrası odak kişi düğmesine döndü. Root font 20 px, body 16 px ölçüldü. | [Merkezlenen kişi](../tests/artifacts/ui-centered-person-modal.jpg) |
| Bildirim tıklaması ve filtreleri | 4 okunmamıştan ilk sertifikaya tıklanınca 3 okunmamış kaldı. Tümü görünümünde okundu/okunmadı satırları ayrıldı; Okunmuş filtresi yalnız 1 satır gösterdi. | [Önce](../tests/artifacts/ui-notifications-unread.jpg), [sonra](../tests/artifacts/ui-notifications-read-unread.jpg) |
| Yeni resmî organizasyon | 7 unit, 7 alt ekip, 37 referans/demo kişi; OS → AST → Muhammed Eren Uygun kişi ayrıntısına geçiş. Referans kimlik ile kurumsal dizin doğrulamasının ayrı olduğu modalda açıklandı. | [Kişi ayrıntısı](../tests/artifacts/ui-centered-person-modal.jpg) |
| Mobil merkez/taşma | 390 × 844 px viewport'ta body/document 383 px; global yatay taşma yok. Dialog x=14, y=14, 362 × 816 px; içerik kendi içinde kayıyor. Geçici viewport sıfırlandı. | [Mobil organizasyon](../tests/artifacts/ui-mobile-organization.jpg), [mobil modal](../tests/artifacts/ui-mobile-centered-modal.jpg) |
| Arama ve klavye | Aksansız `kaniti birlikte` başlıkta olmayan gövde kelimeleriyle 7 iş buldu. `sakar` sorgusu Abdurrahman Şakar sonucunu getirdi; Down/Enter kişi modalını ve Türkçe Birim yöneticisi rolünü açtı. | [Tam metin arama](../tests/artifacts/ui-global-fulltext-search.jpg) |
| Kurumsal tema/profil | Kalkan/pusula logo, Türkçe ürün alt başlığı, gerçek profil adı ve Çalışan/Direktör etiketleri göründü; Wifi/Bağlı göstergesi kaldırıldı. | Yeni arama/ayar ekranları |
| LDAP formu | StartTLS, Base DN, kullanıcı/grup filtreleri ve profil alanları; kayıtlı sır için boş parola alanı ve başarısız test rozeti görüldü. Dizin araması doğrulanmış bağlantı bekliyor. | [LDAP ayarları](../tests/artifacts/ui-ldap-settings.jpg) |
| İki AI bağlantısı | Her iki kartta anahtar kayıtlı / test başarısız durumu; ortak ayarlarda çıkış 4096, timeout 180, sıcaklık 0,7; token/maliyet bilinmiyor olarak gösterildi. | [AI bağlantıları](../tests/artifacts/ui-ai-connections.jpg) |
| Ayar penceresi | Profil Düzenle merkez penceresi ortak portalda açıldı. Parola input değeri boş; arka plan inert, body kilitli. Escape sonrası odak Düzenle düğmesine döndü. | [Profil penceresi](../tests/artifacts/ui-ai-profile-modal.jpg) |

**Deep-link son kontrolü de geçti:** Direktör cold login sonrası okunmamış sertifikaya tıklayınca ISO 27001 Lead Auditor örnek kaydı merkezde açıldı (`/credentials?id=...`); okunmamış sayı 3'ten 2'ye düştü. Escape modalı kapattı ve URL `/credentials` oldu. Gövde araması sonucuna Down/Enter ile gidince Denetim kanıt paketinin son kontrolü iş ayrıntısı `/work?id=...` adresinde açıldı; Escape sonrası URL `/work` oldu. [Sertifika hedefi](../tests/artifacts/ui-notification-credential-detail.jpg), [arama iş hedefi](../tests/artifacts/ui-search-work-detail.jpg).

Alt İş düğmesi ayrı pencere yerine aynı dialog içinde form açtı; tek dialog gözlendi. Bu adım iç içe modal stack testinin geçtiği anlamına gelmez. Tam ileri/geri Tab çevrimi ayrıca denenmiş sayılmıyor. Geçici 390 px viewport sıfırlandı. Temiz yerel demoda üç ardışık dashboard okuması 0,107 / 0,108 / 0,112 saniyedir; eşzamanlı yük testi değildir. Eski UI ekranları bu yeni kontroller yerine sayılmaz.

**Gerçek bağlantı denemeleri:** Root, yerel kabul koşusundan sonra LDAP StartTLS ve iki AI profiline gerçek bağlantı testi yaptı. **Üçü de TLS sertifika doğrulamasında `certificate has expired` nedeniyle başarısız oldu.** TLS doğrulaması korunmuştur; LDAP servis hesabı bind'i ve AI bearer kimlik bilgisi iletimi gerçekleşmedi. Yapılandırma yerel PostgreSQL'de şifreli tutuldu, sırlar kod/kanıta eklenmedi. URUK kişi bulucu SSO girişi istedi; oradan dizin kaydı içeri aktarılmadı. Bu bağlantılar çalışıyor veya production hazır sayılmaz. [Canlı bağlantı kanıtı](../tests/artifacts/live-integrations.json).


## Önceki sürümde tarayıcıdan doğrulanan akışlar

Aşağıdaki ekranlar ilk sürümün geçmiş kanıtıdır; yeni kalkan/pusula logo, merkezlenen pencereler, yazı ölçeği veya resmî 7 unit görünümünün geçtiği anlamına gelmez. Root önizlemesinden ayrı `127.0.0.1` oturumunda gerçek arayüz işlemleri yapılmıştı.

| Akış | Gözlenen sonuç | Görüntü |
| --- | --- | --- |
| Çalışan → PM proje başvurusu | Çalışan taslağı kaydetti, onaya gönderdi; farklı PM oturumu **Onayla ve yayınla** işlemiyle **Planlandı / v3** oluşturdu. Yeniden yükleme kaydı korudu. | [Onaylı proje](../tests/artifacts/ui-project-approved.png) |
| PM → Unit Head kaynak talebi | PM personel istedi; UH ayrı talep panelinden gerekçeli kabul verdi. UI, kaynak kabulünün proje yönetim yetkisi vermediğini açıkladı. | [Kaynak tahsisi kabulü](../tests/artifacts/ui-resource-accepted.png) |
| Organizasyon | Klavyeyle kök ve alt dallar açıldı; 200 kişi, 12 unit, yönetici isimleri ve OVSec → AST alt takım ayrımı görüldü. | [Organizasyon](../tests/artifacts/ui-organization.png) |
| Etkinlik, süreli anket, RSVP | UH etkinlik ve tek seçimli anket açtı. Çalışan oy verdi ve **Katılamıyorum** yanıtını seçti; anket 1 yanıt / 19 seçmen / 18 yanıtsız gösterdi. | [Çalışan yanıtı](../tests/artifacts/ui-event-response.png) |
| Gerçek katılım | UH aynı çalışanın gerçek katılımını **Katıldı** kaydetti. **Planlanan yanıt: Katılamıyorum** korundu; gerçek katılım 1 kişi oldu. | [Ayrı katılım kaydı](../tests/artifacts/ui-event-attendance.png) |
| Teknik admin ayarları | Kullanıcı arama, LDAP kapalı/maskeli alanlar, AI limitleri ve tarih filtreli boş kullanım, SLA hedefleri, iş kuyruğu, audit olayları ve kapalı development test modu açıldı. | [Kullanıcılar](../tests/artifacts/ui-settings-users.png), [test ortamı sınırı](../tests/artifacts/ui-settings-test-mode.png) |
| Mobil 390 × 844 | Login ve hamburger menüden iş listesine giriş çalıştı. Düzeltme sonrası login body/document/viewport **390/390/390 px**; iş tablosu kendi 349 px alanında 815 px yatay içerik tuttu, sayfada yatay taşma oluşmadı. Geçici viewport sonunda sıfırlandı. | [Mobil giriş](../tests/artifacts/ui-mobile-login.png), [mobil liste](../tests/artifacts/ui-mobile-work.png) |

Son sabit frontend sürümünde 11:53:31 UTC sonrası bu QA sekmesinde kaydedilen console error/warn listesi boştu. Aktif geliştirmede hook sayısı değişirken oluşan eski HMR hataları bu son kontrolün dışında tutuldu. QA sekmesi kapatıldı; root'un önizleme sekmesine dokunulmadı.

## Bulgu ve düzeltme kanıtları

| Bulgu | Son doğrulama |
| --- | --- |
| Direktör rolünün otomatik PM onayı vermesi | Normal onay reddi ayrı gerçek direktör oturumunda geçti; açık proje yetkisi ayrıca değerlendirildi. |
| DRF 4xx cevabında transaction'ın kısmi kayıt bırakabilmesi | Geçersiz iş türü sonrası aramada hiçbir kayıt bulunmadı. |
| Idempotency replay'in CSRF/güncel yetkiyi atlama riski | CSRF'siz replay reddi, tek iş/tek bildirim ve iptal edilmiş rol kontrolü geçti. |
| Proje audience kullanıcısına tam teknik katkıların açılması | Özet okuyucusunda katkı metni bulunmadı; JWT ikincil koleksiyon kapsamları da backend regresyonlarına eklendi. |
| PostgreSQL nullable join üzerinde FOR UPDATE hatası | Kilit kapsamı düzeltildi; iki gerçek bağlantıyla worker testi geçti. |
| Geç worker/AI yanıtının iptal edilmiş aktörle yazması | Veritabanından yeniden yetki ve lease kontrolü testleri geçti; eski yanıt yayınlanmadı. |
| SLA uzatıldıktan sonra cevabın eski iç içe tarih göstermesi | Work/case relation cache eşitlendi; gerçek HTTP tarih karşılaştırması ve backend regresyonu geçti. |
| Anonim Swagger HTML isteğinin 500 üretmesi | Django template ayarı tamamlandı; anonim istek kontrollü reddedildi, oturumlu HTML 200 döndü. |
| Tek rapor kaynağı için bütün koleksiyonun taranması | Tek PK sorgusuyla kaynak kontrolü eklendi. Önceki üç 20 saniye timeout'u sonrası aynı 41 test 35,648 saniyede hatasız tamamlandı. Bu, yük testi sonucu değildir. |
| Mobil login'in 390 px ekranda 420 px taşması | Flex minimum genişliği düzeltildi; gerçek 390 px cold reload ve screenshot ile yeniden doğrulandı. |
| LDAP/AI/SMTP bağlantısının hazır görünmesi riski | Yapılandırılmamış sonuç açıkça ayrıldı; canlı haricî bağlantı doğrulanmış sayılmadı. |

Önceki başarısız HTTP çıktıları da korundu: [SLA/Swagger öncesi](../tests/artifacts/api-acceptance-before-final-fixes.json), [performans düzeltmesi öncesi](../tests/artifacts/api-acceptance-before-performance-fix.json). Son geçerli sonuç `api-acceptance.json` dosyasıdır.

## Kalan doğrulamalar ve bilinen sınırlar

- **Kurumsal entegrasyonlar:** Gerçek LDAP ve iki AI bağlantısı denendi; sertifika doğrulamasında süre dolumu hatası nedeniyle başarısız oldu. Sertifika zinciri/kurum güven deposu düzeltildikten sonra LDAP bind/arama/import/iptal ve AI yanıt/token/maliyet tekrar doğrulanmalı. SMTP kurum test kutusu ve Teams hedefi de pilot bekler. Adaptör testleri ve kurallı rapor bu sonuçların yerine sayılmaz.
- **Kabul varyasyonları:** Direktörün doğrudan proje başlatması, anonsun süre sonunda arşivlenmesi, oy kapanışıyla eşzamanlı yarış, kart geri çekme, sertifika uyarılarının tekrar taramada tekilleşmesi ve rapordan çıkarma gerekçesi gibi matrisin kısmi satırları için ek kanıt gerekir.
- **Kullanım ve kapasite:** Temsilci yöneticiyle 30 saniyede gündem bulma / üç etkileşim hedefi, haftalık rapor emeğindeki azalma ve 50 eşzamanlı kullanıcıyla gecikme/kapasite ölçülmedi. Bu koşu yerel doğruluk ve erişim sınırı kanıtıdır.
- **Geri yükleme:** Sentetik snapshot ayrı veritabanına döndürüldü; kurumun RPO/RTO, operasyonel tatbikatı ve dış secret deposu kapsam dışındadır.
- **Geliştirme bağımlılıkları:** Tam npm audit, `picomatch <=4.0.7` ve onu kullanan araçlarla toplam 6 high kaydı gösteriyor; production audit 0. Güncel yamalı sürüm bulunmaması ve uygulanacak takip [uygulama durumunda](IMPLEMENTATION_STATUS.md) belgelenmiştir. [Tam audit çıktısı](../tests/artifacts/dependency-audit-development.json).
- **Uyarılar:** Son backend koşusunda ldap3/pyasn1 kaynaklı iki deprecation uyarısı var; test hatası veya atlama yok.

Bu sonuçlar bütün olası akışların veya üretim koşullarının hatasız olduğu iddiası değildir. Yerel kabul kanıtı, kurum pilotu ve kullanıcı ölçümü birbirinden ayrılmıştır.
