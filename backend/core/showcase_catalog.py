"""Fictional, connected scenarios for an explorable product demo.

The values below describe sample outcomes, never production measurements.
Stable keys belong to fixtures; names and descriptions belong to the reader.
"""

from dataclasses import dataclass

DEMO_FOOTER = "Örnek çalışma · Bu içerik ve ölçümler kurgusal gösterim verisidir."
PEOPLE = {
    "IS": "demo_is", "SAA": "demo_saa", "CDC": "demo_cdc",
    "IAM": "iamemployee", "OS": "demo_os", "SM": "demo_sm", "MSS": "demo_mss",
}


@dataclass(frozen=True)
class Team:
    code: str
    weight: int
    deliveries: tuple  # (title, progress, evidence); equal weights within a team
    done: str
    next_step: str
    blocker: str = ""


@dataclass(frozen=True)
class Scenario:
    key: str
    title: str
    owner: str
    status: str
    priority: str
    due_days: int
    description: str
    outcome: str
    note: str
    teams: tuple[Team, ...]

    @property
    def progress(self):
        return round(sum(
            team.weight * sum(d[1] for d in team.deliveries) / len(team.deliveries)
            for team in self.teams
        ) / 100)


PROJECTS = (
    Scenario(
        "pam", "Ayrıcalıklı erişimlerde süreli yetki dönüşümü", "IAM", "IN_PROGRESS", "CRITICAL", 18,
        "Üretim yönetim erişimlerini kalıcı yetkilerden onaylı ve süreli erişime taşıyoruz. "
        "Kapsam: 24 kritik uygulama, 146 servis hesabı ve üç operasyon ekibi.\n\n"
        "İlk dalgada hesap sahipliği ve rol matrisi tamamlandı. İkinci dalgada oturum kaydı, "
        "acil erişim ve otomatik yetki sonlandırma kontrolleri birlikte doğrulanıyor. "
        "Değişiklikler önce pilot ortamda, ardından bakım penceresinde uygulanacak.",
        "24 uygulamada doğrulanmış hesap sahipliği; pilotta tüm ayrıcalıklı oturumların kaydı; "
        "acil erişim testinin ve operasyon devir kontrol listesinin onaylanması.",
        "Envanter tamamlandı. Kalan çalışma, süreli erişim kuralları ve operasyon kabulü; "
        "geçiş iki bakım penceresine bölündü.",
        (
            Team("IAM", 50, (
                ("Servis hesabı ve rol sahipliği matrisi", 100, "146 hesabın sahibi ve kullanım amacı eşleştirildi; 18 kullanılmayan hesap kapsamdan çıkarıldı."),
                ("Süreli yetki ve acil erişim politikaları", 80, "12 pilot rolün 10'unda otomatik süre sonu doğrulandı; iki istisna için iş sahibi görüşü bekleniyor."),
            ), "24 uygulamanın hesap envanteri kapatıldı; 10 rolün süre sonu testi başarılı.",
                "Kalan iki rolün istisna kararını alıp acil erişim tatbikatını tamamlamak."),
            Team("IS", 25, (
                ("PAM bağlantıları ve oturum kayıtları", 80, "Beş bağlantının dördünde kayıt ve geri oynatma doğrulandı; son bağlantı bakım penceresine alındı."),
                ("Operasyon kabulü ve geri dönüş planı", 60, "Geri dönüş adımları prova edildi; vardiya devir kontrol listesi gözden geçiriliyor."),
            ), "Dört bağlantı için oturum kayıtları ve geri dönüş adımları doğrulandı.",
                "Son bağlantıyı bakım penceresinde açıp vardiya ekibiyle kabulü yapmak."),
            Team("OS", 25, (
                ("Yetki yükseltme ve oturum sonlandırma testleri", 100, "Sekiz negatif senaryo tamamlandı; kapatılan oturumla yeniden işlem yapılamadığı doğrulandı."),
                ("Pilot kapanış yeniden testleri", 80, "Beş bulgunun dördü kapandı; son bulgunun düzeltmesi test ortamına alındı."),
            ), "Sekiz negatif senaryoda yetki sınırı korundu; dört bulgu yeniden testle kapandı.",
                "Son düzeltmenin yeniden testini yapıp kanıt paketini PM'ye iletmek."),
        ),
    ),
    Scenario(
        "api", "Müşteri API'lerinde yetkilendirme standardı", "OS", "IN_PROGRESS", "HIGH", 27,
        "Mobil ve web kanallarının kullandığı 18 API için nesne düzeyi yetkilendirme, "
        "servis kimliği ve kayıt standardı oluşturuluyor.\n\n"
        "Üç ürün ekibiyle ortak test sözleşmesi hazırlandı. Bulgular yalnız kapanış kanıtı "
        "doğrulandıktan sonra tamamlandı sayılıyor. Kapsam dışı kalan eski uç noktalar için "
        "geçiş sonuna kadar telafi edici kontrol uygulanacak.",
        "18 API için kontrol matrisi, CI kontrol adımı ve izlenebilir kapanış kanıtı. "
        "Ürün ekiplerine örnek testler ve ortak kabul ölçütleriyle devir.",
        "Kontrol matrisi yayında. Ürün ekipleri testleri CI akışlarına alıyor; tespit kuralları "
        "paralel olarak doğrulanıyor.",
        (
            Team("OS", 50, (
                ("API kontrol matrisi ve test sözleşmesi", 100, "18 API envanterde; 42 yetkilendirme senaryosu ürün ekipleriyle gözden geçirildi."),
                ("Nesne düzeyi yetki testleri ve yeniden test", 60, "Altı kritik senaryonun dördü düzeltildi; iki yeniden test planlandı."),
            ), "42 senaryolu ortak test paketi hazır; dört kritik senaryo yeniden doğrulandı.",
                "Kalan iki düzeltmeyi ürün ekiplerinin sürüm adayında test etmek."),
            Team("SAA", 25, (
                ("Mimari kontrol ve istisna matrisi", 60, "Üç ürünün ikisi mimari kontrolden geçti; eski API için telafi kontrolü taslağı var."),
                ("Ürün ekipleri için CI güvenlik rehberi", 40, "Örnek pipeline iki depoda denendi; hata mesajları geliştirici geri bildirimiyle sadeleştirildi."),
            ), "İki ürünün mimari kontrolü tamamlandı; örnek pipeline ürün ekibiyle denendi.",
                "Eski API istisnasını karara bağlayıp CI rehberini üçüncü ekiple doğrulamak."),
            Team("CDC", 25, (
                ("API suistimal tespit kuralları", 40, "Beş kuraldan ikisi örnek trafikle doğrulandı; eşik değerleri pilotta gözleniyor."),
                ("Alarm doğrulama ve operasyon devri", 20, "İlk alarm senaryosu vardiya ekibine gösterildi; üç senaryo için trafik üretimi hazırlanıyor."),
            ), "İki tespit kuralı pilotta; ilk alarmın bağlamı ve kayıt alanları doğrulandı.",
                "Kalan senaryoları canlandırıp alarm inceleme adımlarını vardiyaya devretmek."),
        ),
    ),
    Scenario(
        "cloud", "Bulut hesaplarında güvenli başlangıç paketi", "IS", "IN_PROGRESS", "HIGH", 35,
        "Yeni bulut hesaplarının merkezi log, şifreleme, ağ sınırı ve etiketleme kurallarıyla "
        "açılması için tekrar kullanılabilir başlangıç paketi hazırlanıyor.\n\n"
        "Dört pilot hesap üzerinde altyapı kodu ve sapma tespitleri deneniyor. Mevcut hesapların "
        "toplu dönüşümü bu fazın dışında; pilot sonuçları sonraki fazın kapsamını belirleyecek.",
        "Dört pilot hesapta merkezi log akışı, anahtar yönetimi ve politika kontrolü; "
        "hata durumunda uygulanabilir geri dönüş rehberi.",
        "Temel modüller çalışıyor. Log akışı testleri sürüyor; anahtar rotasyonu ve sapma "
        "tespiti sonraki sprintte tamamlanacak.",
        (
            Team("IS", 50, (
                ("Hesap açılış ve ağ sınırı modülleri", 60, "Dört pilot hesabın üçü modülle açıldı; ağ sınırı kontrol listesi tamamlandı."),
                ("Şifreleme ve anahtar rotasyonu", 40, "Varsayılan şifreleme açık; rotasyon için iki servis bağımlılığı test ediliyor."),
            ), "Üç hesap standart modülle açıldı; varsayılan şifreleme kontrol edildi.",
                "Dördüncü hesabı açıp servis anahtarı rotasyonunu kesintisiz prova etmek."),
            Team("CDC", 25, (
                ("Merkezi log toplama ve saklama", 40, "İki hesap log gönderiyor; eksik olay türleri için yönlendirme kuralı hazırlandı."),
                ("Politika sapması alarm paketi", 20, "İlk sapma alarmı doğrulandı; yanlış pozitif senaryoları derleniyor."),
            ), "İki hesabın logları merkezi izlemeye ulaşıyor; ilk sapma alarmı doğrulandı.",
                "Eksik olay türlerini ekleyip saklama süresi ve alarm eşiklerini kontrol etmek."),
            Team("SAA", 25, (
                ("Bulut kontrol kataloğu", 40, "20 kontrolün sekizi kanıtla eşleştirildi; ağ kontrolü gözden geçirildi."),
                ("Pilot kabul ve geri dönüş rehberi", 20, "Geri dönüş adımları taslak; ürün ekibiyle prova zamanı ayrıldı."),
            ), "Sekiz kontrol için kanıt yöntemi tanımlandı; pilot kabul taslağı hazır.",
                "Geri dönüş provasını izleyip kontrol kanıtlarını katalogda tamamlamak."),
        ),
    ),
    Scenario(
        "detection", "Kimlik tabanlı tehditlerde tespit kapsamı", "CDC", "IN_PROGRESS", "HIGH", 14,
        "Şüpheli oturum, MFA yorgunluğu ve ayrıcalıklı hesap suistimali için tespit "
        "kapsamını genişletiyoruz.\n\nKural sayısına ek olarak olay bağlamı, inceleme süresi "
        "ve yanlış pozitifler izleniyor. Her kural için örnek saldırı senaryosu, beklenen "
        "kayıt ve vardiya inceleme adımı birlikte hazırlanıyor.",
        "12 tespit kuralının örnek trafikle doğrulanması; olay bağlamı eksiksiz alarm kartı "
        "ve güncel vardiya inceleme rehberi.",
        "Kuralların büyük bölümü doğrulandı. Son aşama, yanlış pozitif eşikleri ve vardiya kabulü.",
        (
            Team("CDC", 50, (
                ("Tespit kuralı ve olay bağlamı paketi", 100, "12 kural hazır; kullanıcı, cihaz ve oturum alanları alarm kartına eklendi."),
                ("Vardiya doğrulaması ve eşik ayarı", 80, "Beş vardiya senaryosunun dördü tamamlandı; kalan eşik için bir günlük gözlem planlandı."),
            ), "12 kuralın bağlam alanları tamamlandı; dört vardiya senaryosu kabul edildi.",
                "Son eşik ayarını gözlemleyip vardiya kabul kaydını kapatmak."),
            Team("IAM", 25, (
                ("Kimlik olayları veri kalitesi", 100, "Oturum ve MFA olaylarının kaynak kimlikleri eşleştirildi; zaman damgası farkları giderildi."),
                ("Servis hesabı istisnalarının doğrulanması", 60, "10 istisnanın altısı doğrulandı; dört hesap sahibiyle takip görüşmesi planlandı."),
            ), "Kimlik olayları ortak zaman çizgisine alındı; altı servis istisnası doğrulandı.",
                "Dört hesap sahibinden kullanım teyidi alıp istisna listesini sonlandırmak."),
            Team("OS", 25, (
                ("Kontrollü saldırı canlandırması", 100, "MFA yorgunluğu ve şüpheli oturum senaryolarında beklenen alarmlar oluştu."),
                ("Kapsam kapanış ve yeniden test", 80, "Beş yeniden testten dördü tamamlandı; son test vardiya değişiminde yapılacak."),
            ), "Kontrollü senaryolar beklenen alarmları üretti; dört yeniden test tamamlandı.",
                "Vardiya değişiminde kalan senaryoyu çalıştırıp kapanış notunu paylaşmak."),
        ),
    ),
    Scenario(
        "handover", "Yönetilen güvenlik hizmetinde operasyon devri", "MSS", "WAITING", "NORMAL", 24,
        "Yeni hizmet kapsamı için izleme kaynakları, müşteri sorumlulukları ve eskalasyon "
        "zinciri tek kabul planında birleştiriliyor.\n\nOperasyon rehberi hazır. Geçişin "
        "devamı, pilot kaynağın ağ erişimi ve müşteri tarafındaki teknik irtibat teyidine bağlı. "
        "Bu bağımlılık çözülmeden canlı geçiş yapılmayacak.",
        "Onaylı hizmet kapsamı, erişim doğrulama tutanağı, eskalasyon provası ve imzalı "
        "operasyon kabul kontrol listesi.",
        "Pilot log kaynağına ağ erişimi bekleniyor. Teknik irtibat ve açılış penceresi "
        "netleştiğinde uçtan uca kabul testi yapılacak.",
        (
            Team("MSS", 50, (
                ("Hizmet kapsamı ve eskalasyon rehberi", 100, "Hizmet saatleri, sorumluluk matrisi ve üç seviyeli eskalasyon akışı gözden geçirildi."),
                ("Uçtan uca operasyon kabulü", 20, "Masa başı eskalasyon provası tamamlandı; canlı log akışıyla doğrulama bekliyor."),
            ), "Sorumluluk matrisi ve masa başı eskalasyon provası tamamlandı.",
                "Erişim açıldıktan sonra log kaynağı ve eskalasyonu uçtan uca doğrulamak.",
                "Müşteri teknik irtibatından ağ erişimi teyidi bekleniyor; takip görüşmesi iki gün sonra."),
            Team("IS", 25, (
                ("Pilot kaynak bağlantı kontrolleri", 60, "Test bağlantısı hazır; üretim kaynağının izin kuralı onay aşamasında."),
                ("Log sürekliliği ve yedek yol testi", 20, "Yedek yol tasarımı hazır; kaynak erişimi sonrası kayıp ve gecikme testi yapılacak."),
            ), "Test bağlantısı ve yedek yol tasarımı hazırlandı.",
                "Ağ kuralı açılınca kayıp, gecikme ve yedek yol testlerini tamamlamak.",
                "Üretim kaynağı için ağ izin kuralı henüz açılmadı."),
            Team("SM", 25, (
                ("Hizmet kabul ölçütleri", 100, "Kabul ölçütleri ve değişiklik penceresi hizmet sahibiyle gözden geçirildi."),
                ("Geçiş kararı ve paydaş kabulü", 20, "Karar gündemi hazır; teknik kabul kanıtı bekleniyor."),
            ), "Hizmet kabul ölçütleri paydaşlarla netleştirildi.",
                "Teknik kanıt geldikten sonra geçiş kararını gündeme almak.",
                "Teknik kabul tamamlanmadan geçiş kararı verilmeyecek."),
        ),
    ),
    Scenario(
        "access-pilot", "Süreli erişim pilotu ve operasyon kabulü", "IAM", "COMPLETED", "HIGH", -4,
        "Altı pilot uygulamada süreli erişim, hesap sahipliği ve acil erişim adımları "
        "doğrulandı. Pilot sonrası sorumluluklar operasyon ekiplerine devredildi.\n\n"
        "32 ayrıcalıklı hesabın tamamı iş sahibiyle eşleştirildi; kullanılmayan yedi kalıcı "
        "yetki kaldırıldı. İki vardiyada geri dönüş ve acil erişim provası yapıldı. "
        "Kazanımlar ikinci dalganın kontrol listesine aktarıldı.",
        "Altı uygulama için kabul tutanağı, doğrulanmış rol matrisi ve operasyon devir rehberi. "
        "Açık kritik bulgu bırakılmadan pilot kapanışı.",
        "Tüm teslimatlar ve yeniden testler tamamlandı. Kapanış anketi alındı; "
        "öğrenimler sonraki dalgaya aktarıldı.",
        (
            Team("IAM", 50, (
                ("Hesap sahipliği ve süreli erişim kabulü", 100, "32 hesabın sahipliği doğrulandı; yedi gereksiz yetki kaldırıldı; altı uygulamada süre sonu çalışıyor."),
                ("Operasyon devir ve kullanıcı rehberi", 100, "İki vardiyaya devir yapıldı; talep ve acil erişim adımları rehberde birleştirildi."),
            ), "Altı uygulamada süreli erişim kabul edildi; tüm hesapların iş sahibi belli.",
                "İkinci dalgada aynı kontrol listesini kullanıp ilk ayın istisnalarını izlemek."),
            Team("IS", 25, (
                ("Oturum kaydı ve geri dönüş provası", 100, "Kayıtların geri oynatılması ve geri dönüş iki vardiyada doğrulandı."),
                ("İzleme ve operasyon kontrol listesi", 100, "Bağlantı kesintisi alarmları test edildi; günlük kontrol sorumluları atandı."),
            ), "Kayıt, alarm ve geri dönüş kontrolleri iki vardiyada başarıyla prova edildi.",
                "İlk ayın bağlantı ve kayıt sürekliliğini haftalık gözden geçirmek."),
            Team("OS", 25, (
                ("Yetki sınırı ve acil erişim yeniden testi", 100, "12 negatif test tamamlandı; süre dolduktan sonra erişim reddedildi."),
                ("Pilot kapanış kanıt paketi", 100, "Tüm yeniden test çıktıları kabul kontrol listesiyle eşleştirildi; açık kritik bulgu yok."),
            ), "12 negatif test ve kapanış kanıt kontrolü tamamlandı; açık kritik bulgu kalmadı.",
                "İkinci dalgada pilotun negatif test paketini yeniden kullanmak."),
        ),
    ),
    Scenario(
        "recovery", "Kritik hizmetler için kurtarma tatbikatı", "IS", "PLANNED", "HIGH", 45,
        "Kimlik ve güvenlik izleme hizmetlerinin kurtarma bağımlılıklarını masa başı "
        "tatbikatla gözden geçireceğiz.\n\nİlk oturumda bağımlılık haritası ve karar sahipleri "
        "netleşecek. İkinci oturumda yedekten dönüş senaryosu ve iletişim zinciri çalışılacak. "
        "Canlı hizmetlerde kesinti yaratacak bir adım bu fazın kapsamında değil.",
        "Onaylı tatbikat senaryosu, güncel bağımlılık haritası ve sorumlusu/termini belirli "
        "iyileştirme aksiyonları.",
        "Kapsam onaylandı, başlangıç oturumu gelecek hafta. Uygulama teslimatları henüz başlamadı.",
        (
            Team("IS", 50, (("Kurtarma bağımlılık haritası", 0, "Başlangıç oturumunda servis sahipleriyle hazırlanacak."), ("Yedekten dönüş tatbikat planı", 0, "Senaryo ve geri dönüş ölçütleri ilk oturumdan sonra netleşecek.")), "Kapsam ve servis sahipleri belirlendi.", "Bağımlılık haritasını başlangıç oturumunda çıkarmak."),
            Team("IAM", 25, (("Kimlik hizmeti kurtarma senaryosu", 0, "Kimlik bağımlılıkları ve acil erişim adımları çalışılacak."), ("Erişim sürekliliği kontrol listesi", 0, "Servis sahipleriyle gözden geçirilecek.")), "Tatbikata katılacak kimlik operasyon temsilcileri belirlendi.", "Acil erişim ve kimlik bağımlılıklarını taslaklamak."),
            Team("CDC", 25, (("İzleme sürekliliği senaryosu", 0, "Log ve alarm sürekliliği masa başı senaryoya alınacak."), ("Tatbikat iletişim rehberi", 0, "Vardiya ve olay iletişimi için karar ağacı hazırlanacak.")), "Vardiya katılımcıları ve hedef servisler belirlendi.", "Alarm ve iletişim bağımlılıklarını haritaya eklemek."),
        ),
    ),
    Scenario(
        "renewals", "Sertifika yenilemelerinde erken uyarı ve sahiplik", "SAA", "SUBMITTED", "NORMAL", 40,
        "Sertifika ve güvenlik ürünü yenilemelerini iş sahibi, teknik sorumlu ve bütçe "
        "takvimiyle birlikte takip etme önerisi.\n\nİlk fazda 60/30/7 günlük uyarılar, "
        "yenileme kanıtı ve sorumlu değişikliği akışı kurulacak. Talep PM değerlendirmesinde; "
        "onaydan sonra envanter kapsamı ve ekip tahsisi netleşecek.",
        "Sahibi belli yenileme envanteri, üç kademeli uyarı planı ve kanıtla kapanan yenileme akışı.",
        "Proje başvurusu incelemede. Kapsam ve kaynak kararı sonrası başlangıç tarihi netleşecek.",
        (),
    ),
)

CARDS = (
    ("pilot-learning", "IAM", "Süreli erişim pilotunda işe yarayan üç adım", "LESSON", "access-pilot",
     "Hesap sahibini en başta belirlemek, acil erişimi iki vardiyada prova etmek ve kapanış kanıtını tek listede toplamak devri kolaylaştırdı. "
     "Altı uygulamalık pilotun kontrol listesini ikinci dalgada da kullanıyoruz. Ayrıntılarda rol matrisi, geri dönüş adımları ve takip notları var."),
    ("api-help", "OS", "API yetkilendirme testlerini birlikte gözden geçirelim", "HELP", "api",
     "18 API için 42 senaryolu kontrol paketi hazırladık. Nesne sahipliği ve servisler arası yetki sınırında ürün ekiplerinin geri bildirimini bekliyoruz. "
     "Özellikle çok kiracılı yapılarda karşılaştığınız uç durumları paylaşım oturumuna getirebilirsiniz."),
    ("detection-win", "CDC", "Alarm sayısından inceleme kalitesine: kimlik senaryoları", "SUCCESS", "detection",
     "12 kimlik tespit kuralında kullanıcı, cihaz ve oturum bağlamını aynı alarmda birleştirdik. "
     "Vardiya doğrulamasında ilk dört senaryo tamamlandı. Sıradaki adım yanlış pozitif eşiklerini son gözlemle netleştirmek."),
    ("cloud-review", "IS", "Bulut başlangıç paketinde pilot geri bildirimi arıyoruz", "HELP", "cloud",
     "Üç pilot hesabı ortak altyapı modülüyle açtık; varsayılan şifreleme ve ağ sınırı kontrolleri hazır. "
     "Hesap açılış deneyimini ve geri dönüş adımlarını ürün ekipleriyle birlikte iyileştirmek istiyoruz."),
    ("handover-learning", "MSS", "Operasyon devrinde önce sorumluluk matrisi", "LESSON", "handover",
     "Masa başı eskalasyon provası, kimin hangi kararı vereceğini erken görünür kıldı. "
     "Teknik erişim gecikse de kabul ölçütlerini ve iletişim zincirini önceden netleştirebildik. Rehberde üç seviyeli eskalasyon örneği bulunuyor."),
)
