# Atlas geliştirme ve doğrulama yöntemi

Atlas, `UYGULAMA_PLANI.md` ve `MIMARI_TASARIM.md` Revizyon 3 üzerinden geliştirilmektedir. Bu belgelerdeki hedefler ile çalışan sürümün kanıtı ayrıdır. Uygulanan/test edilen kapsam `TEST_MATRIX.md` ve `QA_REPORT.md` içinde izlenir.

## İş paylaşımı

| Sorumlu | Sahiplik | İnceleme sınırı |
| --- | --- | --- |
| Proje koordinasyonu | Bağımlılıklar, yerel altyapı, kurulum, birleştirme, yayın öncesi kontrol | Ortak API sözleşmesi ve entegrasyon test sonuçları |
| Backend agentı | Django domain modelleri, servisler, policy, API, migration, worker | Alt test agentıyla domain ve negatif yetki testleri |
| Frontend agentı | React kabuk, sayfalar, API bağlantısı, kullanıcı akışları | Ayarlar alt agentıyla sekmeler ve formlar |
| Entegrasyon agentı | LDAP, SMTP, AI ayarı/testi, secret saklama, admin API | Eksik yapılandırmada açık hata; dış servise sahte başarı yok |
| QA agentı | Bağımsız HTTP kabul akışları ve kabul matrisi | Ayrı rol oturumları, anonim/CSRF/scope testleri ve tarayıcı doğrulaması |

Agent kayıtları `development/agent-worklog.jsonl` dosyasındadır. Kayıtlar gerçek görev ve komut sonuçlarını özetler; ham konuşma, parola veya kurum verisi içermez. Kullanılan kodlama aracı Codex’tir. Bu kayıt ürün içindeki AI model kullanımından ayrıdır.

## Kabul yaklaşımı

Önce küçük akışlar çalışır hale getirilir, sonra başka rol ve servislerle birleştirilir. İş kuralları için PostgreSQL üzerinde domain testleri; HTTP sınırında session/CSRF ve gerçek JSON sözleşmesi; arayüzde giriş, navigasyon, form, hızlı aksiyon ve hata durumları doğrulanır. Test sonucu, çalıştırılan komut ve kapsam açık yazılır.

Mock servis testi ile gerçek kurum entegrasyonu farklıdır. Yerel AI/SMTP test sunucusu adaptörün davranışını doğrular; kurum LDAP’ı, kullanıcı posta kutusu veya onaylı model hesabına bağlantıyı doğrulamaz. Üretim kabulü için pilot kapısındaki gerçek entegrasyon, yedek geri dönüş ve rol iptali testleri ayrıca gerekir.

## Tasarım kaynağı

Penpard’ın sade kurumsal arayüzü görsel referanstır: açık gri canvas, beyaz kartlar, koyu gri ana aksiyon, ince altın vurgu, dar sol gezinme ve sekmeli ayarlar. Atlas’ın kaynak kodu ve veritabanı ayrıdır. Penpard erişim anahtarı, entegrasyon sırları ve iş kayıtları Atlas’a taşınmaz.

## Desteklenen araç sürümleri

Python/Django bağımlılıkları `requirements.lock.txt`, frontend bağımlılıkları `frontend/package-lock.json` ile sabitlenir. İlk kurulumda Django 5.2 LTS ve Python 3.13 kullanıldı. Django Python uyumluluğu [resmî sürüm notlarında](https://docs.djangoproject.com/en/5.2/releases/5.2/) ve DRF desteği [resmî yayın notlarında](https://www.django-rest-framework.org/community/release-notes/) doğrulandı. Frontend için Node.js 22.12 veya sonrası önerilir; [Vite gereksinimleri](https://vite.dev/guide/) izlenir.

Bağımlılık taraması ve testler belirli bir andaki kanıttır; sonraki güncellemelerde aynı kontroller tekrar çalıştırılır.
