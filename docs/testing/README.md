# onecs kabul doğrulaması

Bu dizindeki testler canlı HTTP uçlarını farklı kullanıcı oturumlarıyla kullanır. Domain testleri `backend/core/tests/` altındadır; buradaki testler onlardan ayrı olarak API sözleşmesini ve katmanlar arasındaki görünür sonucu doğrular.

Testler yalnız sentetik geliştirme/test verisinde çalıştırılır. Proje, iş, vaka, anket ve yetki kayıtları oluşturur; temiz veri gerektiğinde uygulamanın `seed_demo` komutuyla ayrı bir test veritabanı hazırlanır. Gerçek kurumsal veride çalıştırılmaz.

`api_acceptance.py` haricî Python paketi gerektirmez. API sunucusu, worker, PostgreSQL ve sentetik rol hesapları hazırken proje kökünden çalıştırın:

```bash
python3 tests/api_acceptance.py --base-url http://127.0.0.1:8000 --allow-mutations
```

Koşucu `ONECS_DEMO_PASSWORD` ortam değerini, yoksa proje kökündeki `.env` dosyasındaki aynı anahtarı okur; parolayı argümana veya rapora yazmaz. Farklı sentetik ortam dosyası `--env-file /mutlak/yol/test.env` ile seçilebilir. Sunucuyu başlatmak veya veri sıfırlamak bu komutun görevi değildir. Sonuç `tests/artifacts/api-acceptance.json` içine yazılır; atlanan veya başarısız kontroller ayrıca görünür. Arka plan rapor kontrolü için worker çalışmalıdır.

Son gerçek koşu ve ortam `docs/QA_REPORT.md` içinde tutulur. LDAP, kurumsal posta, Teams veya ücretli model için sahte başarılı bağlantı sonucu üretilmez.

Kabul kapsamı ve eksikler `docs/TEST_MATRIX.md` içindedir. Bir kabul maddesine ait birkaç kontrolün geçmesi, o maddenin tüm varyasyonlarının doğrulandığı anlamına gelmez.

Yeni UI/organizasyon/entegrasyon değişikliğinin kabul listesi [UI_SMOKE_PLAN.md](UI_SMOKE_PLAN.md) içindedir. Sadece değişen bir HTTP akışını yeniden doğrulamak için metodun tam adını seçebilirsiniz:

```bash
python3 tests/api_acceptance.py --allow-mutations --test test_48_notification_read_is_recipient_scoped --output tests/artifacts/notification-targeted.json
```

Seçili koşu, bütün testlerin çalıştığı anlamına gelmez; artifact içindeki `selection` alanı bunu ayırır. AI profil testi yalnız kendisinin oluşturduğu kapalı sentetik profilleri düzenleyip arşivler; canlı bağlantı/default seçim testi yapmaz. Rapor üretim testi etkin AI sağlayıcısını kullanabileceğinden, tüm kabul koşusu canlı AI yapılandırılmadan önce veya açık koordinasyonla çalıştırılır.

## Yeni proje içgörüleri ve veri koruma yardımcıları

[Yeni özellik kabul planı](FEATURE_ACCEPTANCE.md), `tests/project_insights_acceptance.py` dosyasındaki 21 ayrı gerçek HTTP senaryosunu ve kalan UI/yarış varyasyonlarını açıklar. Genel 46 testten farklı kanıt dosyası kullanılır; AI proje testleri açık `RULE_BASED` modundadır.

[Yerel temizlik yönergesi](CLEANUP.md), `tests/cleanup_acceptance.py` exact sahiplik önizlemesini ve `tests/cleanup_clone_proof.py` ayrı klon doğrulayıcısını açıklar. Bunlar uygulama servisleri değildir; üretimde kullanılmaz. Son klon ve yerel apply/preserve kanıtları `cleanup-clone-proof.json` / `cleanup-live-verification.json`, son read-only kaynak geri yükleme kanıtı `restore-project-insights.json` dosyalarıdır. Geçmiş baseline artifact'leri üzerine yazılmaz.
