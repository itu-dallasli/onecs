# Gerçekçi gösterim portföyü

`seed_showcase`, `seed_demo` ile kurulu yerel demo organizasyonuna bağlantılı örnek içerik ekler.
Üretimde çalışmaz. Kullanıcı, parola, LDAP bağlantısı, rol veya organizasyon yapısını değiştirmez.
E-posta, dış bildirim veya yapay zekâ isteği üretmez. İçerikteki sonuçlar kurgusal gösterim verisidir.

## Kullanım

Önce yerel PostgreSQL veritabanının yedeğini alın. Organizasyon henüz kurulmadıysa
`ONECS_DEMO_PASSWORD` ortam değişkenini tanımlayarak `seed_demo` komutunu çalıştırın.

```bash
python backend/manage.py seed_showcase --polish-legacy-cards
```

Komut sekiz proje, proje görevleri, ekip katkıları, beş paylaşım, üç anons, üç etkinlik,
katılım ve anket yanıtları, iki vaka, kişisel işler, sertifikalar ve haftalık rapor ekler.
Projeler başvuru, planlama, devam, bağımlılık bekleme ve tamamlanma aşamalarını gösterir.
Kurgusal içerik olduğu detay metninin sonunda belirtilir; başlıklarda QA kodu bulunmaz.

Proje analizleri özelliği kuruluysa teslimat planları, üç tarihli ilerleme serisi,
paydaş kapanış anketi ve düzenlenebilir kural tabanlı raporlar da eklenir.
Ekip ağırlıkları toplamı 100'dür. Her ekipte eşit ağırlıklı iki teslimat bulunur;
liste ilerlemesi bu değerlerin ağırlıklı ortalamasının yuvarlanmış halidir.
Eksik kalite veya paydaş değerlendirmesi tamamlanmış gibi gösterilmez.

## Tekrar çalıştırma ve sınırlar

UUID5 kimlikleri sürümlü fixture anahtarlarından türetilir. Daha önce oluşturulan bir proje,
görev, kart veya rapor yeniden yazılmaz; kullanıcının düzenlemeleri ve silinen alt kayıtları
geri yüklenmez. Aynı başlıktaki kullanıcı kaydı fixture olarak benimsenmez.
Kaynak proje görünürlüğü paylaşım kartından bağımsız kalır; yalnız demo hesapları üye yapılır.
Proje içeriği için demo PM, kart yayını için demo direktör hesabı kullanılır.

`--polish-legacy-cards`, yalnız özgün `seed_demo` yazarına **ve eksiksiz eski metne** uyan
üç kartın açıklamasını iyileştirir. Düzenlenmiş kartlar korunur. Bu seçenek QA kayıtlarını silmez.
Eski kabul testi kayıtlarının temizliği ayrı ve açık kayıt sahipliği/yedek kontrolü gerektirir.

## Doğrulama

```bash
python backend/manage.py test core.tests.test_showcase_seed
```

Kontroller: durum/ilerleme tutarlılığı, dolu detaylar, bekleyen işlerin engel ve sonraki adımı,
kapanış kanıtları, tekrar çalıştırmada değişikliklerin korunması, LDAP hesabının benimsenmemesi,
üretim engeli ve dış iş kuyruğu oluşturulmaması. Proje analizleri varsa teslimat hesabı,
ilerleme serisi, anket kapsamı ve rapor düzenlemelerinin korunması ayrıca doğrulanır.
