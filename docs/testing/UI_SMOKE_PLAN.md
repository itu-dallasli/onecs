# onecs arayüz / organizasyon / entegrasyon kabul planı

Durum: Yeni sürüm için uygulandı; gerçekleşen sonuçlar aşağıda ve QA raporunda yer alır. Bu üst tablo senaryoları tanımlar; tek başına her varyasyonun geçtiği iddiası değildir. Önceki sürümün 41 HTTP / 142 backend kanıtı yeni özellikler için başarı kanıtı sayılmaz.

| Kimlik | Kullanıcı davranışı / kontrol | Doğrulama |
| --- | --- | --- |
| U01 | Masaüstünde iş/proje/vaka ayrıntısı ve oluşturma penceresi açılır. | Dialog viewport içinde, yatay/dikey merkezde; uzun içerik pencerede kayar; sayfa kayması kilitlenir. |
| U02 | Dialog klavyeyle kullanılır ve kapatılır. | İleri/geri Tab pencere içinde kalır; Escape en üst pencereyi kapatır; odak açan kontrole döner; dış içerik inert olur ve kapanınca geri gelir. |
| U03 | İç içe pencere açılır. | İki aria-modal aynı anda aktif kalmaz; üstteki kapanınca alttakinin odağı ve kilidi korunur. |
| U04 | Yeni kurumsal görünüm açılır. | Seçilen onecs logosu, altında “Siber Güvenlik Yönetim Uygulaması” alt başlığı; profil adı ve Türkçe roller; Wifi/Bağlı göstergesi bulunmaz. Giriş, açık/dar menü ve mobil görünümde logo oranı korunur. Sayfa verisi yüklenirken küçük onecs logosu ortada sabit kalır; yalnız çevre halkası döner ve hareket azaltma tercihinde animasyon durur. Kullanıcı adı/rol için sahte sabit metin yoktur. |
| U05 | 125% okunurluk hedefi ve 390 px görünüm denenir. | Hesaplanan metin boyutları önceki tasarımla karşılaştırılır; giriş, başlıklar, tablolar ve modal kesilmez. Mobil menü ve tablo içi yatay kaydırma çalışır; global yatay taşma yoktur. Geçici viewport sıfırlanır. |
| U06 | Global aramaya açıklamadaki iki kelime farklı sırada girilir. | Yetkili kayıt bulunur; harf bazlı sonuç yenilenir; gizli kaynak/özel katkı arama yoluyla bulunmaz. Gerçek PostgreSQL FTS kontrolü: `test_47_full_text_search_reads_body_and_preserves_scope`. |
| U07 | Bildirim paneli açılır, okunmamış filtrelenir ve kayda tıklanır. | Panel genişliği/uzun satırlar okunabilir; doğru kayda gidilir; tıklanan bildirim okundu olur; okunmuş/okunmamış listeleri ayrılır. `test_48_notification_read_is_recipient_scoped` ayrıca başkasının bildirimi üzerinde ret doğrular. |
| U08 | Resmî organizasyon açılır. | Direktör Emin İslam Tatlı; yedi resmî unit ve yöneticileri doğru; sentetik çalışanlar açıkça demo verisidir. Güncel oturum kimliklerinden kapsam doğrulanır. Eski 12 unit varsayımı yoktur. |
| U09 | Teknik admin LDAP sekmesini ve keşif/arama/önizleme/aktarım kontrollerini açar. | Parola maskeli; arama sonucu atama yapmaz; explicit org/rol seçimi olmadan içe aktarılmaz. Gerçek LDAP keşif/arama yalnız root koordinasyonuyla yapılır. |
| U10 | LDAP içe aktarma yetkisi sınanır. | Çalışan/TM/UH izin alamaz; teknik admin iş rolü veremez; sahte batch kontrollü 4xx verir. HTTP testleri dış LDAP çağrısı başlatmaz. |
| U11 | İki AI profilinin ayarları incelenir. | Profil/seçim/versiyon ayrı; sır hiçbir GET/audit sonucunda düz metin olmaz. Sentetik test profili disabled oluşturulur, düzenlenir, arşivlenir; default veya canlı bağlantı değiştirilmez. |
| U12 | Son sabit sürüm konsolu kontrol edilir. | Yeni runtime hata/uyarıları raporlanır; eski HMR kaynaklı hatalar ayrı zaman damgasıyla belirtilir. |

Her tamamlanan UI akışı için ilgili görünüm PNG olarak `tests/artifacts/` altına kaydedilir. Ekranlar veya JSON kanıtları gerçek parola/API anahtarı içermez. Gerçek bağlantı denemeleri sentetik/local testlerden ayrı raporlanır; başarısızlık veya atlama gizlenmez.

## onecs markası ve yükleme görünümü kontrolü

Ürün adı onecs olarak güncellendi; kullanıcının gönderdiği özgün PNG yeniden çizilmeden uygulamaya kopyalandı. Logo görünümü ortak `ProductLogo` bileşeninden, alt başlık `OnecsBrand` bileşeninden gelir. Ayarlar dâhil sayfa verisi yükleme durumları ortak `Loading` bileşenini kullanır. Logo masaüstünde 96 px, mobilde 88 px genişliğinde sabittir; lacivert/altın çevre halkası 7 saniyede döner; `prefers-reduced-motion: reduce` kuralı animasyonları durdurur. Yol değişiminde sayfa yeniden bağlanır; sorgu parametresiyle açılan ayrıntılar aynı yol içinde kalır. Yapay bekleme veya sahte yüzde eklenmedi.

IAB'de gerçek masaüstü ve 390 px mobil giriş ekranı doğrulandı. Açık/koyu/dar menü ve yükleme bileşeni, gerçek uygulama bileşenlerini ve stillerini kullanan geçici bir önizlemede kontrol edildi; geçici dosya kaldırıldı. İki ölçümde logo dönüş matrisi değişti; durum bölgesi `role=status`, `aria-live=polite` değerlerini taşıdı. Mobil giriş ve yükleme önizlemesinde sayfa genişliği 390 px oldu; yatay taşma yoktu. Hareket azaltma kuralı kaynak kodundan kontrol edildi; işletim sistemi tercihi değiştirilmedi. Bu çalışma yeni bir kimlik/rol veya bütün sayfaların canlı HTTP kabul koşusu değildir.

`npm run build` ve 24 frontend testi geçti. Eski uygulama adı ayarları, sabit ad doğrulaması, API belgesi, worker ve proje raporları için ilgili 66 PostgreSQL testi geçti. Kontrol kaydı [onecs marka kontrolü](../../tests/artifacts/onecs-brand-checks.json); ekranlar `tests/artifacts/ui-onecs-*.jpg` altındadır. Önceki logo denemelerinin kanıtları tarihsel kayıt olarak tutulur.

## Sabit ve ortalanmış yükleme logosu

Son düzeltmede logo dönüşü kaldırıldı. Masaüstü çemberi 120 px / logo 96 px, mobil çemberi 112 px / logo 88 px oldu. Yalnız yükleme bileşeni bulunan ana içerik alanı grid ile ortalanır; başlık veya başka içeriği olan sayfalara bu kural uygulanmaz. Kart/tablo yüklemeleri kendi kutularında ortalı kalır. `role=status`, `aria-live=polite` ve hareket azaltma desteği korundu.

Gerçek bileşenleri kullanan geçici IAB önizlemesinde iki farklı anda logo `animation:none`, `transform:none` kaldı; yalnız halka dönüş matrisi değişti. Masaüstünde yatay merkez farkı 0 px, dikey fark 1,5 px; 390 px mobilde iki merkez farkı da 0 px oldu, sayfa genişliği 390 px kaldı. Kart önizlemesinde ana içerik `display:block` kalarak başlık yerleşimi korundu; koyu görünüm kontrol edildi. Üretim derlemesi geçti. Geçici dosya kaldırıldı, viewport sıfırlandı. [Güncel kontrol kaydı](../../tests/artifacts/onecs-loading-stationary-checks.json); görseller `ui-onecs-loading-stationary*.jpg` adlarıyla kayıtlıdır. Önceki dönen logo kayıtları tarihsel durumdur.

## 18 Kasım 2026 yürütme durumu

Yeni tam HTTP koşusu 12:23:03 UTC'de **46/46 PASS, 0 skip**, 21,621 saniye tamamlandı. U06'nın backend FTS/gizlilik, U07'nin API alıcı/read-unread ve U08'in yedi unit/referans aktör karşılıkları geçti. U10 yetki reddi/sahte batch, U11 kapalı iki sentetik profil izolasyonu/maskeleme/arşivlemesi geçti. Canlı LDAP/AI çağrısı yapılmadı.

QA alt ajanının IAB bağlantısı kullanılamadığından native Chrome'da yeni sekme denendi; kullanıcı kontrolü değiştiğinde işlem durduruldu. Mevcut kullanıcı sekmeleri değiştirilmedi. **Root IAB yeni kişi/ayar penceresi merkez, inert/body kilidi, Escape/odak dönüşü, 390 px ölçümü, arama, Türkçe profil ve bildirim read/unread akışlarını doğruladı.** Sertifika bildirimi → sertifika ayrıntısı ve arama sonucu → iş ayrıntısı açılışı, Escape sonrası URL kimliğinin temizliğiyle geçti; iç içe modal ve tam Tab/Shift-Tab çevrimi ayrıca denenmiş sayılmaz. Bu teknik sınırlama UI kontrolünü geçmiş saymak için kullanılmaz. Sonuçların tek kaynağı güncel [QA raporudur](../QA_REPORT.md).

Gerçek LDAP StartTLS ve iki AI bağlantı testini root sonradan çalıştırdı: üçü de süresi dolmuş TLS sertifika doğrulaması nedeniyle başarısız. TLS korundu; [canlı sonuç](../../tests/artifacts/live-integrations.json). Bu, U09/U11 canlı bağlantı başarısı değildir.

Son birleşik doğrulama: **193 backend + 41 alt senaryo**, **46 HTTP**, **9 frontend**, güncel **53 tablo/573 satır restore**. İç içe modal stack testi ve tam Tab/Shift-Tab çevrimi için ek kanıt yok; Alt İş aynı dialog içinde form açmaktadır.
