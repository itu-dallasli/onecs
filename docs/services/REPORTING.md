# Yönetim raporu ve ekip pivot görünümü

`/reports` listesindeki rapor, aynı modal içinde **Genel Rapor** ve ekip bazlı görünümlerle açılır. Genel Rapor ilk sekme ve pivot tablonun ilk satırıdır. Ekip satırı veya sekmesi seçilince yalnız o ekibin rapora alınmış kaynakları gösterilir. Bu görünüm, bütün ekibin tüm faaliyetlerinin eksiksiz dökümü iddiası taşımaz.

## Kaynak ve bölüm sözleşmesi

`GET /api/v1/reports/{id}/pivot/` mevcut raporun kimliğini, sürümünü, içerik hash'ini, dönemini, genel özeti ve `teams` listesini döndürür. Her özet `source_count`, `counts` ve sıralı `sections` alanlarına sahiptir. Sayaçlar tekil `(type,id)` kaynağı üzerinden hesaplanır: açık, tamamlanan, aktif kritik ve dönem sonuna göre gecikmiş. Bir kaynak birden çok sinyal taşıyabilir; ancak tek bir ana bölüme ve tek bir ekibe yerleştirilir. Genel toplam, ekip satırlarının toplamıdır.

| Bölüm | Kural |
| --- | --- |
| Öne çıkanlar | Tamamlanmış veya kapatılmış kaynaklar |
| Kritik konular ve kararlar | Açık kritik veya gönderilmiş/doğrulama bekleyen kaynaklar |
| Engeller ve gecikmeler | Dönem sonuna göre gecikmiş; bekleyen/engellenmiş veya iptal/reddedilmiş kaynaklar |
| Bilgi ve projeler | Diğer kaynaklar |
| Sonraki adımlar | Kaynakta ayrı sonraki adım verisi yoksa boş olduğu açıkça belirtilir; öneri uydurulmaz |

Tamamlanmış kaynak eski bir kritik öncelik taşısa bile aktif kritik sayılmaz. İptal/reddedilmiş kaynak açık veya tamamlandı sayısına eklenmez. Gecikme raporun `period_end` günü dahil Europe/Istanbul sınırına göre hesaplanır; raporu ertesi gün açmak geçmiş raporun sayılarını değiştirmez. Bu sınıflandırma mevcut snapshot durumunu kullanır; geçmişteki gerçek durumun yeniden inşası değildir.

## Kalıcılık ve yetki

Yeni kaynak snapshot'ı `owner_org:{id,name,code}` bilgisini de saklar. Ekip adı sonradan değişse veya kaynak izinli başka ekibe taşınsa bile raporun kayıtlı ekip etiketi değişmez. Eski raporlarda eksik ekip bilgisi yalnız güncel erişimi doğrulanan kaynaktan tamamlanır; `metadata_provenance=current_authorized` veya `mixed` bu farkı arayüzde açıklar. Raporun kaynakları, metni, hash'i ve sürümü GET sırasında değiştirilmez.

Pivot mevcut rapor liste/detay politikasını paylaşır. Rapor sahibi kendi raporunu, kapsam yöneticisi yalnız kaynakların tamamını okuyabildiği onaylı alt kapsam raporunu görebilir. Projede yalnız yönetim özetine erişmek detay snapshot içeren PM raporunu açmaz. Rol veya kaynak erişimi kaldırılırsa pivot da kapanır. Bozuk/silinmiş kaynaklar raporu açılır hale getirmez. Salt okunur servis tokenı ek organizasyon ve kapsam sınırını korur; rapor yönetim düğmelerine izin alamaz.

Kaydedilmiş AI veya kurallı genel metin yalnız Genel Rapor görünümünde gösterilir. Ekip sekmesi, genel AI metnini o ekibe özel üretilmiş gibi sunmaz. Raporu açmak, ekip değiştirmek veya tabloyu incelemek model çağırmaz. Üretim ve onay mevcut ayrı sürümlü işlemlerdir. Markdown düğmesi kayıtlı genel raporu indirir; yazdırma seçili görünümü kullanır.

## Arayüz

Modal geniş ekranda ekip karşılaştırma tablosunu, dar ekranda kontrollü yatay kaydırmayı kullanır. Sekmeler yön tuşları/Home/End ile, ekip satırları gerçek düğmelerle seçilir. Genel görünüm her rapor açılışında önce gelir. Farklı rapor/kullanıcı/sürüm değişiminde eski pivot kullanılmaz; hash/sürüm uyuşmazlığı ve erişim hatası açık yeniden yükleme durumu gösterir. Metin güvenilir HTML olarak çalıştırılmaz.

Kod: `backend/core/report_pivot.py`, `ReportViewSet.pivot`, `snapshot_source`, `ReportPivot.tsx`. Testler: `backend/core/tests/test_report_pivot.py`, mevcut `test_report_rollup.py`/`test_worker.py` ve frontend pivot testleri. Gerçek çalıştırma sonuçları [QA raporunda](../QA_REPORT.md) tutulur.
