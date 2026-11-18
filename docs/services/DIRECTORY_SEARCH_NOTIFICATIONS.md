# onecs · Organizasyon referansı, arama ve bildirimler

Bu belge çalışan `core` API sözleşmesini açıklar. Kurumsal organizasyon sayfasında doğrulanan kişi/ekip adları bir **şema referansıdır**; yerel referans hesabı gerçek LDAP kimliği veya kurumsal parola doğrulaması sayılmaz. İş, vaka, katkı, sertifika ve etkinlik kayıtları açıkça belirtilmiş demo senaryolarıdır.

## Organizasyon referansı ve seed

`seed_demo` direktör Emin İslam Tatlı altında yedi unit kurar: Infrastructure Security, Security Assurance & Architecture, Cyber Defence Center, Identity Access Management, Offensive Security, Security Management, Managed Security Services. Hakan Tokay IS ve MSS için aynı `User` ve iki `UNIT_HEAD` grant'iyle temsil edilir. Kodlar `ICT-CS-*` biçiminde **onecs içi sabit eşleme anahtarlarıdır**; doğrulanmış HR/dizin kodu olarak sunulmaz.

Doğrulanan alt ekipler ve yöneticiler ayrıca eklenir; referans dizinin tam kurumsal kadro olduğu iddia edilmez; yönetici bulunmayan çalışan grupları için sahte yönetim düğümü yaratılmaz. AST'nin 13 doğrulanmış çalışan referansı bulunur. `profile_kind=OFFICIAL_REFERENCE` kaynak türünü, `DEMO` açıkça kurgusal hesabı, `LOCAL` yerel kullanıcıyı, `LDAP` gerçek dizin eşlemesini ayırır. Referans kişilerin bilinmeyen e-postaları boş kalır. Açık demo giriş alias'ları dışındaki referans hesapların parolaları kullanılamaz durumdadır.

Her unit için bir açıkça “Demo” işaretli örnek çalışan vardır; `cs001` benzeri dolgu personel üretilmez. PM görevi Security Management kapsamındadır. İsteğe bağlı `--with-demo-team` resmî olduğu iddia edilmeyen `is_demo=true` alt ekip oluşturur; doğrulanmış AST bu opsiyona bağlı değildir. Komut mevcut iş durumunu, katkıları veya parolaları tekrar çalıştırıldığında sıfırlamaz. Eski 12-unit seed/dolgu hesap tespitinde işlemi reddeder; otomatik veri silmez. Yedek ve yalnız yerel demo veritabanı temizliği ayrı işletim adımıdır.

`OrgSerializer` yönetici `manager_id`, `manager_ids`, `managers`, `manager_name`, `member_count`, `is_demo` alanlarını verir. Şema referansı yönetici varsa, teknik demo yetki hesabı resmî yönetici adına eklenmez. `PersonSerializer` `profile_kind`, `identity_source`, `role_label` ve etkin/süreli `roles[{role,org_id,org_name,includes_descendants,expires_at}]` döndürür.

`GET /api/v1/people/?org_id=...&search=...&limit=48&offset=0` seçilen dalın üyelerini ve yönetici görevlilerini getirir. Alt dallar varsayılan kapsanır; `include_descendants=false` tek düğüme indirger. `role` filtresi isteğe bağlıdır. Yanıt `results`, `count`, `limit`, `offset`, `next_offset` taşır. Dış JWT'nin organizasyon sınırı ayrıca uygulanır.

## PostgreSQL arama

`0005_search_extensions` migration'ı `unaccent` ve `pg_trgm` kurar. `/api/v1/search/?q=` PostgreSQL `SearchVector/SearchQuery/SearchRank`, sözcük öneki, aksan sadeleştirme ve sınırlı trigram benzerliği kullanır. Türkçe `I/İ/ı/i` arama karşılaştırmasında sadeleştirilir. Kelimelerin sırası değişse de sözcüksel eşleşme çalışır; kullanıcı sorgusu SQL'e metin birleştirmeyle yazılmaz.

İş/vaka başlık ve açıklamaları, kişinin dizin alanları, ekip profilleri, yetkili paylaşım/anons/etkinlik ve sertifika metaverisi aranabilir. Projelerde ayrıntı yetkilisi izinli ana alanları arar; yalnız özet okuyucusu başlıkla sınırlıdır. Onaylanmamış yeni proje sürümünün açıklaması aramaya katılmaz. Sonuçta `id`, `title`, `resource_type` ve uygun durum/kaynak alanları bulunur; hızlı arama en fazla 25 sonuç verir. Erişim/scope filtresi **eşleşmeden önce** uygulanır. Ayrı arama kümesi veya arama indeksinin performans garantisi iddia edilmez; mevcut ölçek PostgreSQL üzerinde ölçülür.

## Bildirim okundu durumu

`GET /api/v1/notifications/?status=all|unread|read&limit=50&offset=0` yalnız güncel kaydına erişilebilen, oturum sahibine gönderilmiş bildirimleri döndürür. Yanıt `results`, filtrelenmiş `count`, tüm yetkili kayıtların `unread_count` toplamı, `limit`, `offset`, `next_offset` taşır. Sayfa boyutu 1–100 aralığındadır. `read_at` ile `is_read` tutarlıdır. Geçersiz filtre/sayfalama 400'dür; başka alıcının veya yetkisi iptal edilmiş kaydın bildirim detayı 404'tür. Silinmiş veya bozuk kaynak kimlikli bildirimler listeyi bozmaz, sayaca katılmaz.

Her satırın `url` alanı sunucunun güncel kaynak politikasına göre ürettiği uygulama içi hedeftir. Personel tahsisi bildirimi ilgili talebi, vaka bildirimi ilgili değerlendirme kaydını açar; bu hedefler ana proje/vaka ayrıntısına erişim vermez. Bilinmeyen iç bildirim türü için hedef `null` olur; dış API'de bilinmeyen kaynak kapalıdır.

`POST /notifications/{id}/read/` varsayılan olarak okundu işaretler; `{read:false}` yeniden okunmamış yapar. `read` gerçek boolean olmalıdır. `POST /notifications/mark-all-read/` yalnız o anda yetkili ve görünür okunmamış kayıtları değiştirir; `{updated:n}` döndürür. Liste filtresi bu yazma işlemlerinin kapsamını değiştirmez. İşlemler audit ile aynı transaction'da kalıcıdır. Dış JWT salt okunurdur ve bu yazma işlemlerini kullanamaz; ikincil bildirim sorguları da ek organizasyon kapsamını korur. Okundu durumu e-posta teslimi veya aksiyonun tamamlanması anlamına gelmez.

Arayüz zili sunucunun toplamını gösterir; yalnız ilk sayfayı saymaz. Çekmece açıldığında, pencere odaklandığında ve 15 saniyelik aralıklarla yenilenir; yüklenmiş tüm sayfalar güncellenir. Okundu kaydı başarılı olmadan hedefe gidilmez. Eski yenileme yanıtları yeni okundu durumunu ezemez; kullanıcı değişince önbellek temizlenir. Bu periyodik yenileme gerçek zamanlı push teslimi değildir.

Kod: [seed](../../backend/core/management/commands/seed_demo.py), [API](../../backend/core/views.py), [policy](../../backend/core/policy.py), [serializer](../../backend/core/serializers.py). Testler: [referans seed](../../backend/core/tests/test_canonical_seed.py), [arama ve bildirim](../../backend/core/tests/test_directory_search_notifications.py), [JWT ikincil kapsam](../../backend/core/tests/test_api_scope_secondary.py). Gerçek koşu sonucu [QA raporunda](../QA_REPORT.md) saklanır; test dosyasının bulunması çalıştırıldığı anlamına gelmez.
