# Atlas · Organizasyon ve ekip rehberi

Bu belge çalışan ilk sürümü ve [kurumsal şema referansı/arama/bildirim sözleşmesini](../services/DIRECTORY_SEARCH_NOTIFICATIONS.md) açıklar; [Revizyon 3 planı](../UYGULAMA_PLANI.md) hedef kapsamı ayrıca tanımlar.

- Kanonik ilişki `OrgNode.parent` ve kişinin tek `User.primary_org` üyeliğidir. Kurum kodu bir yetki kuralı değildir.
- `DIRECTOR`, `UNIT_HEAD` ve `TEAM_MANAGER` rolleri, etkin/süreli `RoleGrant` kapsamı ve `includes_descendants` ile yönetim alanı oluşturur. Team Manager bulunmayan dallar desteklenir.
- `GET /api/v1/organization/` düğümleri, yönetici adını, üye sayısını ve ekip profilini; `GET /api/v1/people/?search=` kişi rehberini verir. İş ayrıntıları ayrı kayıt yetkisi ister.
- `PATCH /organization/{id}/` yalnız yetkili yönetici veya teknik admin için `{version,description?,expertise?,contact?}` kabul eder; bu işlem ağaç yapısını değiştirmez.
- `PATCH /people/{id}/` kişinin yalnız kendi gönüllü `expertise` listesini değiştirmesini sağlar; bu beyan sertifika veya performans puanı değildir.
- `GET /people/{id}/contributions/` kişi veya yetkili yöneticisine, yalnız halen erişebildiği katkıları gösterir. Eski ekip/yazar snapshot'ı korunur.
- PM görevi ayrı `PMAppointment` kaydıdır. `GET/POST /project-managers/` listeler/atar; yeni atama için `{user_id,governing_org_id,name?,reason}` ve ilgili Unit Head/direktör yetkisi gerekir.
- PM'nin bağlı uniti, isteği yapan/katkı veren unitten ayrıdır. Normal organizasyon yöneticiliği proje yönetimi vermez.
- Yerel/LDAP kullanıcı sağlama ve rol değişikliği [yönetim servisi](../services/INTEGRATIONS.md) üzerinden gerçekleşir; teknik adminin kendine iş yetkisi verme hakkı yoktur.
- Profil/PM ataması audit ile transaction içinde yazılır; bunlar SLA başlatmaz ve tek başına atama e-postası üretmez. İş atamasının bildirim sınırı [İşler](WORK.md) belgesindedir.
- Oturum zorunludur; geçersiz girdi 400, yetkisiz işlem 403/404, eski `version` 409 döndürür. JWT tüketicisinin ek organizasyon kapsamı ayrıca daraltılır.
- **Henüz uygulanmayan:** UI üzerinden düğüm oluşturma/taşıma, tam organizasyon devir kuyruğu ve LDAP grup–iş rolü otomatik senkronizasyonu. İlk sürümde organizasyon doğrulanan şema referansı ve açıkça işaretli demo hesaplarıyla kurulur; yerel referans hesabı gerçek LDAP doğrulaması değildir.

Kod: [modeller](../../backend/core/models.py), [policy](../../backend/core/policy.py), [API](../../backend/core/views.py), [serializer](../../backend/core/serializers.py).
Testler: [test_policy.py](../../backend/core/tests/test_policy.py), [test_latest_flows.py](../../backend/core/tests/test_latest_flows.py), [test_continuity.py](../../backend/core/tests/test_continuity.py), [test_test_mode.py](../../backend/core/tests/test_test_mode.py). Güncel koşu sonucu [QA raporundadır](../QA_REPORT.md).
