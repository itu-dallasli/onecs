# Yerel kabul verisi temizliği

`tests/cleanup_acceptance.py` yalnız exact kabul koşusu öneklerini önizler. Varsayılan kullanım salt okunur veritabanı sorgusudur; `.runtime` altına kimlik/sayı planı yazar. `flush`, seed, zaman aralığına göre toplu silme ve genel `QA-*` taraması kullanmaz.

```bash
.venv/bin/python tests/cleanup_acceptance.py \
  --run-prefix QA-INSIGHTS-73f9c543b2 \
  --run-prefix QA-INSIGHTS-687ac5e41f \
  --run-prefix QA-e3cc696020 \
  --run-prefix QA-7efa202cd3 \
  --output .runtime/cleanup-preview.json
```

Yeni koşuların JSON kanıtındaki `run_key` ayrıca verilmelidir. İlk üç eski dosyada bu alan olmadığı için yukarıdaki önekler root ile canlı salt okunur kayıt sayımıyla doğrulandı. Koşucu artık bu alanı kanıta ekler.

Kapsam exact başlık/ad kökleri ve açıkça tanımlanmış proje/vaka/iş/etkinlik sahiplik ilişkileridir. Aktör, alıcı, oluşturan veya yetki veren kişi üzerinden kayıt seçilmez. Reverse FK taraması kapsam genişletmez; dışarıda kalan bir referans varsa yalnız blocker üretir. Job ancak seçili QA genel/proje raporunun doğrudan job FK'si ve uyumlu rapor kimliği/kind payload'ıyla seçilir. Generic bildirim/outbox/audit kaynak türü ve kimliğiyle eşleştirilir; yanlış tipe ait aynı kimlik kapsam açmaz. Idempotency cache temizliği kapsam dışındadır ve hash ile korunur. Normal organizasyon, PM ataması, SLA politikası, LDAP kimliği/import'u, canlı entegrasyon ayarları ve gerçek AI profil sırları kapsam dışındadır. Yalnız adı exact test öneki olan **kapalı** AI profilinin kendi yapılandırma sürümleri temizlenebilir. AI kullanım/maliyet ledger'ı korunur.

Kullanıcı ve RoleGrant hiçbir koşulda seçilmez; `--extra-user-id` desteği yoktur. İlk taslaktaki genel reverse FK yaklaşımı bağımsız incelemede fazla geniş bulundu ve kullanılmadan kaldırıldı. Pasif test63 hesabı gizli/pasif kalır; görsel temizlik uğruna kullanıcı/LDAP/rol kaydı silinmez.

Uygulama için önce somut preview incelenir, sonra root koordine ederek worker'ı durdurur ve **preview'den sonra** gerçek veritabanı yedeğini alır. `--apply` ayrıca `--approved-plan` ve `--backup-file` ister. Yedek PostgreSQL custom dump (`PGDMP`) biçiminde olmalıdır. SHA değişmişse, canlı `RUNNING` iş varsa, korunan ters ilişki/FK döngüsü varsa veya yedek yok/boş/eskiyse yazma başlamaz. Kayıtlar kilitlenip kapsam tekrar doğrulanır. Bütün kullanıcı/rol kayıtları, öneksiz proje/iş/vaka/rapor ve proje alt kayıtları, non-QA config/version/profil, LDAP ve AI maliyet ledger'ı için tam satır hash'leri önce/sonra karşılaştırılır; sapma transaction'ı geri alır. Silme çocuklardan köklere, self-PROTECT iş zincirleri de gerçek yapraklardan yapılır.

**Mevcut doğrulama:** Ayrı klonda gerçek apply/preserve kontrolü 2,444 saniyede geçti. İlk deneme `ProgressEntry.previous` self-PROTECT nedeniyle transaction'ı tamamen geri aldı; genel self-FK yaprak sırası düzeltildi ve yeniden doğrulandı. Root'un canlı onayı/servis durdurması ve fresh preview sonrası 0600 PGDMP yedekle yerel uygulama 2,314 saniyede geçti. 29 korunan modelin tam satır hash'leri aynı, 38 kullanıcı/56 rol/7 öneksiz proje ve gerçek entegrasyon/cost/cache kayıtları korundu. [Klon kanıtı](../../tests/artifacts/cleanup-clone-proof.json), [canlı yerel kanıt](../../tests/artifacts/cleanup-live-verification.json). İki sahip olunan geçici clone DB ve dört geçici dump kaldırıldı; rollback yedeği ignored runtime'da tutulur. Bu, bütün kurum verilerinin RPO/RTO tatbikatının yapıldığı anlamına gelmez.

Önizleme planları ve kurum sırlarını içerebilen PostgreSQL dump dosyaları Git'e eklenmez. Genel QA raporuna yalnız önekler, sayılar, sonuç ve sır içermeyen doğrulama bilgisi girilir.
