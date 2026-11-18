---
name: onecs-domain-change
description: onecs'ta proje, unit işi, vaka, SLA veya paylaşım akışını değiştirirken bağlama göre yetkiyi ve kalıcı işlem sınırlarını korur. Genel arayüz metni veya bağımsız projeler için kullanılmaz.
---

# onecs domain değişikliği

Değişikliğin amacını onaylı `docs/UYGULAMA_PLANI.md` ve teknik sınırlarını `docs/MIMARI_TASARIM.md` üzerinden belirle. Çalışan sürümün doğrulama durumunu `docs/TEST_MATRIX.md` ve `docs/QA_REPORT.md` ile karşılaştır; planlanan özellikleri çalışıyor kabul etme.

- Kaydın bağlamını önce seç: `UNIT_WORK` organizasyon yöneticisi, `PROJECT_TASK` PM yönetimi, `CASE_ACTION` vaka koordinasyonu tarafından yönetilir. Birleşik liste bu hakları birleştirmez.
- Proje isteyen unit ile PM’nin bağlı yönetim uniti farklıdır. Personel tahsisini kabul eden yönetici proje içeriğini yönetmiş olmaz. Kendi onayı gerçek kullanıcı kimliğiyle engellenir.
- İşlemi bağlamın servisinde uygula. Güncel policy, nesne sürümü ve durum geçişini aynı transaction’da kontrol et; değişiklik, audit ve outbox’ı birlikte yaz. İstek tekrarı yeni atama veya SLA üretmemeli.
- SLA başlangıcı resmî açılış/ilk atama veya kişisel işi benimseme anıdır. Yeniden atama/açma saati sıfırlamaz; ilk termin ve ihlal geçmişi korunur. Resmî unit işinde sonuç kabulü, vakada bağımsız kapanış doğrulaması gerekir.
- Paylaşım metni ve okuyucu kapsamı ayrı onaylanır. PM’nin içerik onayı geniş kitleye yayın hakkı değildir. Kart kaynak erişimini vermez; arama, rapor, bildirim ve cache aynı sınırı korumalıdır.
- Testi kullanıcı davranışından yaz: ilgili olumlu akışa ek olarak başka unit, sıradan Unit Head, eski sürüm veya iptal edilmiş rol ile reddi doğrula. Transaction/eşzamanlılık testi gerçek PostgreSQL üzerinde çalışır.

Sonuçta ilgili akış/servis belgesini ve kabul eşlemesini güncelle. Gerçek LDAP/SMTP/model/restore kanıtı olmayan özellik için yerel testin kapsamını açık yaz. Bu skill kendi başına dış servise mesaj veya üretime dağıtım izni vermez.
