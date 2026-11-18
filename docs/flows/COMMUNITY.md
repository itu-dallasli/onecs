# Atlas ekip paylaşımı ve keşif akışı

Mevcut ürün, ekip rehberi/uzmanlık beyanını ve kaynakla ilişkili paylaşım kartlarını kullanır. Serbest mesajlaşma veya çalışan performans puanı üretmez.

## Akış ve servis sözleşmesi

- `POST /api/v1/community/`, başlık, paylaşılacak ayrı metin, tür, hedef ekipler ve isteğe bağlı erişilebilir iş/proje/vaka kaynağıyla `DRAFT` oluşturur. Kaynak kimliği/sürümü kaydedilir.
- Türler `SUCCESS`, `HELP`, `OFFER`, `LESSON`, `KNOWLEDGE`; kart ham kaynak metninin otomatik yayını değildir.
- Kart sahibi `submit` ile `SUBMITTED` durumuna gönderir. `approve-content`, proje içeriği için PM kapsamında onay; vaka içeriği için vaka açma yetkisi ister ve `CONTENT_APPROVED` kaydeder.
- `publish`, kartın sahibi organizasyonda yönetim yetkisi ister. Proje kartı için doğrudan proje onay yetkisi veya önceden kaydedilmiş içerik onayı ayrıca gerekir.
- Tüm CS veya yayıncının organizasyon kapsamı dışındaki hedefler için Unit Head/Direktör yayın kararı gerekir. PM rolü tek başına geniş yayına yetmez.
- Kaynak sürümü yayın öncesinde yeniden doğrulanır; değişmiş/kaldırılmış kaynak 409 verir. `withdraw`, yetkili organizasyon yöneticisinin kartı `WITHDRAWN` yapmasıdır.
- `interest`, yalnız yayınlı karta ilgi ekler/kaldırır; ekleme kart sahibine tekilleştirilmiş bildirim oluşturur. Proje üyeliği, kaynak tahsisi veya iş ataması yapmaz.

## Görünürlük ve hata yolları

- Taslak sahibi/kapsam yöneticisi; gönderilmiş proje kartı ilgili PM; yayınlı kart onaylı hedef kitlesi tarafından görülür. Liste de bu politika ile süzülür.
- Kaynağı okuyamayan kart okuyucusuna kaynak kimliği/türü gösterilmez; paylaşımı görmek kaynağa erişim kazandırmaz.
- Sürüm isteyen işlemlerde eski `version` 409, eksik izin 403, geçersiz tür/durum 400 üretir. İçerik onayı ile hedef kitle yayını ayrı adımlardır.
- `Organizasyon` ekranındaki uzmanlık gönüllü kişisel beyandır; `PATCH /people/{id}/` başka kişinin uzmanlığını düzenlemeye izin vermez. Sertifika doğrulamasıyla eşdeğer değildir.
- Mevcut otomatik yayından kaldırma yerine yetkili geri çekme kullanılır; kaynak sınıfı değişikliklerine bağlı kapsamlı yeniden inceleme ve AI uzmanlık eşleştirme hedef çalışmadır.

## Kod ve doğrulama

- Kod: `CommunityViewSet`/`PeopleViewSet`, `core.policy.visible_cards`, `core.serializers.CardSerializer`; UI: `frontend/src/pages/Community.tsx` ve `Organization.tsx`.
- Mevcut testler: `backend/core/tests/test_latest_flows.py::ControlledSharingTests` ve `SelfServiceAndApiScopeTests.test_expertise_is_voluntary_self_declaration_and_cannot_edit_another_person`; HTTP kabul dosyası `tests/api_acceptance.py` içindeki `test_42` ve `test_46` paylaşım testleri.
- K28–K29 ile ilişkilidir; güncel yürütme sonucu [QA raporundadır](../QA_REPORT.md). Gerçek kurumsal bildirim/posta teslimi ayrıca doğrulanır.
