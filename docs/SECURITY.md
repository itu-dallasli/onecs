# onecs güvenlik sınırları

## Erişim

Tüm iş ekranları giriş gerektirir. Tarayıcı sunucu oturumu ve CSRF; dış salt okunur API dar JWT scope’u kullanır. Yetki sunucuda her listede, nesnede, raporda, aramada ve worker sonucunda tekrar kontrol edilir. System Admin teknik rolü üretimde iş verisini otomatik açmaz. Kendi başvurusunu onaylama gerçek kullanıcı kimliğiyle engellenir.

## Veri ve sırlar

Yerel `.env`, veritabanı ve çalışma çıktıları Git dışında kalır. Entegrasyon sırları şifrelenir, API yanıtları ve loglarda geri döndürülmez. Vaka kayıtları paylaşılabilir koordinasyon bilgisidir; hassas teknik kanıt kaynak sistemde kalır. Paylaşım kartı kaynağı açmaz.

## Entegrasyonlar

LDAP TLS sertifika doğrulaması ve açık grup eşlemesi kullanır. Model/posta bağlantı hedefleri izinli yapılandırmadan seçilir. Model girdi metni talimat kabul edilmez. AI atama, onay, izin veya SLA değiştiremez; rapor taslağı yönetici onayından geçer.

## Ortam ve kurtarma

Sentetik demo hesapları yalnız yerel geliştirme içindir. Üretim ortamı, secret anahtarı, HTTPS ve God Mode engeli deployment katmanında zorunlu doğrulanır. İşlerin durumu session yerine kalıcı job/outbox kayıtlarında tutulur. Pilot için gerçek LDAP, posta, model, yedek geri dönüş ve rol iptali kanıtı gerekir.

## Güvenlik sorunlarının ele alınması

Tekrarlanabilir senaryo, etkilenen rol/kayıt ve beklenen sınır kaydedilir. Gerçek parola veya hassas kayıt eklenmez. Düzeltme, negatif erişim testi ve ilgili akış testiyle doğrulanır. Yerel test başarısı kurum üretimi için güvenlik garantisi değildir.
