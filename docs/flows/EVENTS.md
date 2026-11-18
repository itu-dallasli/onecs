# Atlas etkinlik, anket ve katılım akışı

Tercih anketi, katılım niyeti ve gerçekleşmiş katılım üç ayrı kayıttır. Mevcut ekran `frontend/src/pages/Community.tsx` içindeki etkinlik görünümüdür.

## Akış ve servis sözleşmesi

- `POST /api/v1/events/`, yetkili organizasyon yöneticisi tarafından oluşturulur. Başlangıç/bitiş verilmişse bitiş daha sonra olmalıdır.
- Davetliler etkin sahip organizasyonun alt ağacındaki aktif kişilerden seçilir; açık liste verilmezse bu kapsamdaki kişiler alınır. Kapsam dışı davetli reddedilir.
- `POST /events/{id}/poll/`, yöneticiye açıktır: 2–20 benzersiz/dolu seçenek, geçerli seçim sınırı ve gelecekte kapanış zamanı gerekir. Davetli kimlikleri seçmen snapshot'ı olur.
- `POST /events/{id}/poll-response/`, seçmenin 1–`max_choices` geçerli/benzersiz seçeneğini kaydeder. Kapanışa kadar aynı kişinin mevcut yanıtı güncellenir; yeni oy satırı çoğaltılmaz.
- Sunucu zamanı ve anket satır kilidi kapanış kontrolünü belirler. UI radyo/çoklu seçim, sınır ve kapalı anket görünümü sağlar; son karar sunucudadır.
- `POST /events/{id}/rsvp/`, yalnız davetlinin `YES`, `NO`, `MAYBE` yanıtını tutar. Yanıtsız kişi ayrı sayılır; anket oyu RSVP oluşturmaz.
- `POST /events/{id}/attendance/`, yöneticinin davetli için boolean `present` kaydını tutar. Henüz kaydedilmemiş ile katılmadı ayrı durumlardır.
- `GET /events/{id}/participants/`, yalnız kapsam yöneticisine isim, RSVP ve gerçekleşmiş katılımı döndürür. Genel görünüm toplu sayıları ve kişinin kendi oyunu/yanıtını içerir.

## İzinler, başarısızlık ve mevcut sınır

- Liste/ayrıntı davetliler ve sahip organizasyonun yöneticileriyle sınırlıdır. Anket açma/katılım kaydetme organizasyon yönetim yetkisi; oy/RSVP davetli veya seçmen ilişkisi ister.
- Yanlış seçenek, seçim sayısı, kapalı anket veya geçersiz tarih 400; kapsam/davetli yetkisi eksikliği 403/404; sürümlü yönetici işleminde eski kayıt 409 verir.
- Anket isimlidir; anonimlik vaadi yoktur. Anket sonucu etkinliği otomatik kesinleştirmez.
- Mevcut API'de davetli değiştirme/etkinliği yeniden planlama akışı yoktur. Ayrı unit kabulüyle ortak etkinlik, takvim/Teams senkronizasyonu, galeri ve anonim geri bildirim pilot/genişleme hedefidir.

## Kod ve doğrulama

- Kod: `backend/core/views.py::EventViewSet`, `core.models` içindeki `Event`, `Poll`, `PollResponse`, `EventRSVP`, `EventAttendance`; `core.serializers.EventSerializer/PollSerializer`.
- Mevcut HTTP kabul testleri: `tests/api_acceptance.py::test_41_poll_rsvp_and_attendance_are_distinct` ve `test_44_closed_poll_rejects_late_response`; ortak oturum korumaları `backend/core/tests/test_session_security.py` içindedir.
- Testler oy tekrarı/değişimi, seçim sınırı, davetli dışı yanıt, RSVP/katılım ayrımı ve kapanış sınırını kapsar. K10–K11 [test matrisiyle](../TEST_MATRIX.md) eşlenir; güncel yürütme sonucu [QA raporunda](../QA_REPORT.md) tutulur.
