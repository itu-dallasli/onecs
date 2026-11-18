# Kayıt ekleri ve seçili e-posta alıcıları

Proje talebi, unit işi/taahhüt/alt iş, proje görevi, vaka/aksiyon/ihbar, anons, paylaşım, etkinlik ve sertifika oluşturma formları ortak dosya/fotoğraf ve isteğe bağlı e-posta alanını kullanır. Dosya seçimi, sürükleme, yerel fotoğraf önizlemesi ve seçimden kaldırma desteklenir. Seçili alıcı kayda üyelik veya okuma yetkisi kazanmaz.

## API ve işlem sınırı

1. `POST /api/v1/attachments/`, multipart `file` ile tek dosyayı yükler. Yanıt: `id`, `name`, `size`, doğrulanan `content_type`, `status`, `scan_status`, `created_at`. Fiziksel yol verilmez. Aynı `X-Request-ID` ve aynı dosya tek yüklemedir; farklı dosya 409 üretir.
2. Desteklenen mevcut oluşturma POST'una `attachment_ids: UUID[]`, `send_email: boolean`, `notification_recipient_ids: UUID[]` eklenir. En fazla 5 dosya ve 20 tekil alıcı kabul edilir. E-posta açıkken en az bir alıcı gerekir. Liste/UUID/aktiflik ve kaynak yetkisi sunucuda doğrulanır.
3. Kaynak oluşturma, yalnız yükleyene ait ilişkisiz dosyaların bağlanması, mail tercihi, audit, outbox ve domain idempotency aynı transaction'dadır. Hatalı ek/alıcı bütün mutasyonu geri alır. Başarısız form, yüklenmiş ilişkisiz dosyaları silmeye çalışır; yarıda kalanlar süreli temizliğe kalır. Ağ hatasında istemci aynı işlem kimliğiyle bir kez yeniden dener.

`GET /attachments/?resource_type=work&resource_id={id}` kaydın eklerini listeler. Türler `project`, `work`, `case`, `case_notice`, `announcement`, `community`, `event`, `credential` olur. Parametresiz liste yalnız kişinin kendi ilişkisiz yüklemelerini verir. `GET /attachments/{id}/download/` her istekte güncel yetki ve tarama durumunu doğrular; özel, önbelleksiz, attachment yanıtıdır. `DELETE /attachments/{id}/` yalnız yükleyenin ilişkisiz dosyasını tombstone yapar; bağlı dosya bu uçla silinmez.

Proje ekleri tam proje ayrıntısı gerektirir; yayımlanmış özet izni yeterli değildir. Proje görevi ekleri de tam proje ayrıntısına bağlıdır. Vaka/iş/ihbar kendi politikalarını kullanır. Dar kapsamlı vaka açma delegasyonu ile ilk ek bağlanabilir; bu, oluşturucuya sonradan vaka okuma hakkı vermez. Kaynak ihbar vakaya dönüşünce veya kaynaktan paylaşım açılınca dosyalar yeni kitleye otomatik taşınmaz. Dış JWT salt okunur sınırı korunur.

## Bildirim zamanı ve teslim

İş, vaka, ihbar, etkinlik ve sertifika seçili alıcıları oluşturma sırasında kuyruğa alınır. Proje tercihi taslakta saklanır ve `submit` sırasında; anons/paylaşım tercihi `publish` sırasında uygulanır. İleri tarihli anons postası başlangıca ertelenir. Arada yetkisi kaldırılan kişi atlanır; worker teslimden önce aktif hesap, güncel erişim ve yayın durumunu tekrar kontrol eder. Geri çekilmiş/süresi dolmuş anons postası iptal edilir.

Mevcut zorunlu atama/PM inceleme postaları isteğe bağlı kutu kapalıyken de korunur. Aynı kaynak/alıcı için mevcut teslim niyeti ikinci kez oluşturulmaz. E-posta kayıt içeriği veya dosya eki taşımaz; uygulamadaki bildirimlere yönlendiren kısa metindir. SMTP hazır değilse `WAITING_CONFIGURATION`, alıcı adresi yoksa `BLOCKED`; bu durumlar teslim edilmiş sayılmaz. Gerçek kurumsal SMTP teslimi yerel mock testlerinden ayrı kabul gerektirir.

## Dosya doğrulama ve işletim

Tek dosya 10 MB, bir kayıtta 5 ek, kullanıcı başına 30 ilişkisiz yükleme sınırı vardır. PNG/JPEG/WebP, PDF, UTF-8 TXT/CSV ve makrosuz DOCX/XLSX/PPTX kabul edilir. Uzantı, bildirilen MIME ve içerik imzası kontrol edilir; HTML/SVG/çalıştırılabilir dosya, Office makrosu, arşiv yolu geçişi ve aşırı açılmış arşiv reddedilir. Bu kontroller antivirüs taraması değildir.

Depo varsayılan `.runtime/private-uploads` olup static/public altında sunulmaz. `ONECS_UPLOAD_ROOT` ile kalıcı özel volume seçilmeli; uygulama kullanıcısına özel dosya/dizin izinleri ve veritabanıyla eşleşen yedek kurulmalıdır.

`ONECS_UPLOAD_SCANNER_COMMAND` güvenilir deployment komutudur; shell çalıştırılmaz, dosyanın özel yolu son argüman olarak eklenir. Çıkış 0 temiz, 1 bulaşık, diğer sonuç/timeout hata kabul edilir. Tarayıcıdan komut seçilemez. Scanner yapılandırılmamış veya hata vermişse dosya `PENDING_SCAN` olur ve indirilemez. Bulaşık dosya `REJECTED` olur ve kayda bağlanamaz. Tarama düzeltildikten sonra en fazla 100 dosyalık kontrollü tekrar:

```bash
.venv/bin/python backend/manage.py scan_attachments --limit 20
.venv/bin/python backend/manage.py cleanup_attachments
.venv/bin/python backend/manage.py cleanup_attachments --apply --hours 24
```

Temizlik varsayılan önizlemedir; bağlı etkin dosyalar korunur. Fiziksel silme başarısızsa tombstone erişimi engeller ve sonraki temizlik yeniden dener. `ONECS_UPLOAD_ALLOW_UNSCANNED=true` yalnız development/debug veya test/demo ortamında açıkça taranmamış yerel dosya kullanımına izin verir; `scan_status=unscanned` arayüzde görünür. Üretimde bu bayrak indirmeyi açmaz. Güvenli varsayılan false'tur.

## Doğrulama

`core/tests/test_attachments.py`, `test_record_notifications.py` ve `test_record_extras_api.py`: özel depo, yanlış yükleyici, başka unit, özet proje izni, yetki/üyelik iptali, karantina, MIME/Office/boyut, stale sürüm, create rollback, aynı istekle tek kayıt/tek posta, taslak/yayın ve worker erteleme/iptal kontrolleri. `frontend/src/lib/recordExtras.test.ts` ve `api.test.ts`: multipart, limitler, staging temizliği ve aynı kimlikle ağ tekrarı. Gerçek scanner/SMTP kurumu bu testlerle doğrulanmış sayılmaz.
