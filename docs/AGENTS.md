# Atlas geliştirme kuralları

- Ürünün adı Atlas’tır. Türkçe arayüz, React/TypeScript + Django/DRF + PostgreSQL temelini koru.
- `docs/UYGULAMA_PLANI.md` ve `docs/MIMARI_TASARIM.md` güncel gereksinim kaynağıdır. Proje ölçümü ek kararları `docs/flows/PROJECT_INSIGHTS.md` altında tutulur. Uygulanmayan kapsamı tamamlandı diye gösterme.
- Proje yönetimini PM kapsamından, unit işlerini organizasyon kapsamından, vaka aksiyonlarını vaka üyeliğinden yetkilendir. Okuma hakkı yazma/onay hakkı değildir.
- API ve worker aynı domain/policy servislerini kullanır. Kritik işlem, audit ve outbox aynı transaction’da yazılır.
- Gerçek aktör kimliğini koru. God Mode yalnız sentetik test ortamında; kullanıcı görünümü denemesinde bypass kapalıdır.
- Secret’ları, gerçek kurum verisini veya ham model girdilerini commit/log/agent kanıtına ekleme.
- Her değişiklikte ilgili negatif yetki, durum geçişi ve kalıcılık testini çalıştır. PostgreSQL eşzamanlılığını SQLite ile doğrulanmış sayma.
- Bağımsız frontend/backend/QA işleri ayrı sahipliklerle paralel ilerler; ortak sözleşme değişikliklerini diğer sorumlulara bildir.
- Dış LDAP/SMTP/AI/Teams bağlantısını yalnız gerçek test sonucu doğrular; bağlantısız durumu açık göster.
- README, akış/servis belgeleri ve test matrisi gerçek kodla birlikte güncellenir. Test sonucu ve AI katkı kanıtı gerçek çıktıya bağlanır.
- Ana README ve AI çalışma dizinleri dışındaki yardımcı Markdown dosyaları `docs/` altında tutulur. Test kodu ve makine kanıtı `tests/` içinde kalabilir.
- Proje teslimat ilerlemesi, kalite ve paydaş memnuniyeti farklı ölçümlerdir. Eksik veri sıfır başarı sayılmaz; AI önerisi ve insan düzenlemesi kaynak/sürüm/gerekçeyle ayrılır.
