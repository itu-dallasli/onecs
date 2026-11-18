# Atlas kişisel sertifika akışı

Mevcut modül kişisel sertifika metaverisini ve yönetici tarafından önemli seçilen kayıtların süre uyarılarını tutar. Denetim kanıt dosyası veya kurumsal sertifika deposu tamamlanmış özellik değildir.

## Akış ve servis sözleşmesi

- `GET /api/v1/credentials/`, kişinin kendi kayıtlarını ve yöneticinin alt organizasyonundaki kişilerin kayıtlarını döndürür; dış API'nin organizasyon kapsamı ayrıca daraltılır.
- `POST /credentials/`, kişinin kendisi veya kapsam yöneticisi tarafından açılır: kişi, sertifika adı, veren kurum, alınma/bitiş tarihi ve isteğe bağlı referans.
- Süreli kayıtta bitiş zorunludur; `no_expiry=true` ile bitiş birlikte gönderilemez. Bitiş edinme tarihinden önce olamaz. Yeni kayıt varsayılan `DECLARED` durumundadır.
- `important=true` işareti organizasyon yöneticisi yetkisi ister. Kişinin kendi beyanı yönetici önceliği veya doğrulanmış kanıt sayılmaz.
- `PATCH /credentials/{id}/`, yalnız kapsam yöneticisinin `important`, `verification_status` ve `alert_days` alanlarını günceller; `version` zorunludur. Doğrulama durumları `DECLARED`, `VERIFIED`, `REJECTED`; uyarı aralığı 1–365 gündür.
- `core.worker.scan_credentials`, önemli/süreli kayıtları yerel güne göre tarar. Bitiş `bugün + alert_days` sınırına girmişse sertifika sahibi ve ilgili yöneticiler için bildirim/outbox oluşturur.
- Tekillik sertifika kimliği + bitiş tarihi + alıcıya dayanır; her worker turunda aynı süre uyarısı tekrar oluşturulmaz. Süresi geçmiş önemli kayıt da taramaya dahildir.

## Arayüz ve başarısızlık davranışı

- Geçersiz tarih/süre veya doğrulama durumu 400; başka kişiye yetkisiz erişim/düzenleme 403/404; eski sürüm 409 verir. Bildirim kuyruğu SMTP başarısından bağımsız kalıcıdır.
- UI `frontend/src/pages/Community.tsx` üzerinde liste/ayrıntı, doğrulama etiketi ve süreli/süresiz sertifika oluşturma sunar. “Geçerlilik süresi yok” seçildiğinde bitiş alanı devre dışı kalır ve istek `no_expiry=true`, `expires_on=null` gönderir. Süreli kayıtta bitiş zorunludur; süresiz kayıt listede “Süresiz” görünür.
- Kapsam yöneticisi ayrıntıdaki değerlendirme formunda önem, doğrulama durumu ve uyarı gününü kaydeder. Form yalnız sunucunun kayıt için döndürdüğü `permissions.manage=true` halinde görünür; sıradan sertifika sahibi veya kapsam dışı yönetici düzenleme formunu görmez. Sunucu her PATCH işleminde kapsamı yeniden doğrular.
- Yönetim formu düzenlemeye başladığı kayıt sürümünü korur. Başarılı kayıtta sürüm yenilenir; eşzamanlı değişiklikte 409 hatası gösterilir ve yeni sürüm sessizce üzerine yazılmaz. Süresiz kayıtta uyarı günü alanı pasiftir; bitiş uyarısı üretilmez.
- Belge yükleme, kanıtın dış kaynaktan doğrulanması, sertifika yenileme/silme düzenleme akışı ve denetim paket çıktısı genişleme işidir. Posta adaptörü [entegrasyon belgesindedir](../services/INTEGRATIONS.md).

## Kod ve doğrulama

- Kod: `backend/core/views.py::CredentialViewSet`, `backend/core/models.py::Credential`, `backend/core/worker.py::scan_credentials` ve `CredentialSerializer`.
- Mevcut HTTP kabul testi `tests/api_acceptance.py::test_43_credential_claim_verification_and_scope`, süresiz beyanı, yönetici önem/doğrulama yetkisini, kapsam dışı erişimi ve ters tarih reddini kapsar; K34 [test matrisiyle](../TEST_MATRIX.md) izlenir.
- Uyarı eşiği ve tekrarlanan taramanın tek bildirim üretmesi, API metaveri testinden ayrı worker doğrulamasıdır. Bu belge yeni test sonucu üretmez; sonuçlar [QA raporunda](../QA_REPORT.md) tutulur.
