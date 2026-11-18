# Kişi iş yükü ve unit işi atama kapsamı

`PeopleViewSet` kişi rehberini, iş ayrıntısı erişimini ve unit işi atama yetkisini ayrı değerlendirir. Rehberde bir kişiyi görmek, işlerini veya projelerinin teknik ayrıntılarını görme ya da kendisine iş atama hakkı vermez.

## Endpointler

| Endpoint | Sonuç |
|---|---|
| `GET /api/v1/people/?assignable=true` | Yalnız güncel organizasyon yönetim kapsamındaki etkin kişiler |
| `GET /api/v1/people/{id}/assignable-scope/` | Kişi, `permissions` ve geçerli atama hedefi |
| `GET /api/v1/people/{id}/workload/` | Yetkili okuyucu için görünür işler, proje üyelikleri, vakalar ve katkılar |

Kişi listesi mevcut `search`, `org_id`, `include_descendants`, `role`, `limit`, `offset` filtrelerini korur. Varsayılan ve en yüksek sayfa boyutu 500'dür. Yanıt `results`, `count`, `limit`, `offset`, `next_offset` taşır. `assignable=true` bütün filtrelere ek olarak kişinin **birincil organizasyonunu** aktörün güncel `manager_scope_ids` kümesiyle sınırlar. Kod önekinden organizasyon ilişkisi türetilmez.

İş yükünü kişi kendisi veya `can_manage_org(actor, person.primary_org_id)` sonucu doğru olan güncel organizasyon yöneticisi açabilir. Başka çalışan, başka unit yöneticisi veya tek başına PM/SYSTEM_ADMIN rolü 403 alır. Etkin olmayan kişi rehber sorgusuna girmediği için 404 döner. Rolün iptali/süresinin dolması sonraki isteğe hemen yansır. Dış API istemcisinin organizasyon kapsamı ayrıca uygulanır.

## Alan sözleşmesi

`workload` yanıtı şu alanları içerir:

- `person`: mevcut `PersonSerializer` alanları.
- `summary`: `work_total`, `open_work`, `overdue_work`, `critical_work`, `projects`, `cases`, `contributions`, `by_context`.
- `by_context`: `UNIT_WORK`, `PROJECT_TASK`, `CASE_ACTION` başına **görünür atanmış tüm işlerin** sayısı. Açık iş sayısı ayrı alanındadır.
- `works`: en fazla 200 görünür atanmış iş; mevcut iş alanlarına ek `visibility`.
- `projects`: en fazla 100 görünür aktif üyelik/PM ilişkili proje; mevcut proje alanlarına ek `membership_role`.
- `cases`: en fazla 100 görünür koordinasyon/üyelik/aksiyon/katkı ilişkili vaka; SLA varsa düz `due_at` ve mevcut `sla` alanı.
- `contributions`: en fazla 100 görünür katkı; `visibility`, `context_type`, `context_id` ile birlikte.
- `permissions`: `can_view_workload`, `can_assign_work`, `can_create_personal_work`.
- `assignment`: `context='UNIT_WORK'`, `allowed_target`, `suggested_payload`.
- `limits`: koleksiyonların yukarıdaki sınırları. Sayaçlar kırpılmış liste uzunluklarından üretilmez.

Projelerde `membership_role` kayıttaki rolü korur; atanmış PM için `PROJECT_MANAGER` olur. Bu etiket aktöre yeni bir proje yönetim hakkı vermez. Projenin `DETAIL`/`SUMMARY` policy sonucu mevcut proje serializer'ıyla korunur.

Proje özeti okuyucusuna proje görevinin teknik açıklaması, beklenen teknik çıktı, sonuç, engel, üst iş açıklaması veya teknik katkı notları verilmez. Görevin başlığı, durumu, önceliği ve tarihi kaynak planlama metadata'sı olarak kalır; teknik alanlar boş ve `visibility='SUMMARY'` olur. Proje katkısının teknik metni de kişi katkı listesinde sabit bir sınırlı erişim açıklamasıyla gösterilir. Gizli proje/vaka kaydı, başlığı veya sayısı koleksiyonlara ve sayaçlara eklenmez.

Sorgular önce hedef kişinin atanmış işleri/üyelikleri/katkılarıyla sınırlandırılır; her aday güncel domain policy'den geçer. Bütün organizasyonun iş havuzunu yükleyip sonra kişiye göre kırpma yapılmaz. Hiç görünür kaydı olmayan yetkili kişi için boş koleksiyonlar gerçek sıfır sayaçlarla döner.

## Atama

`can_assign_work`, etkin aktörün etkin hedef kişinin birincil organizasyonunda güncel organizasyon yönetim yetkisi olmasını gerektirir. Proje yöneticiliği unit işi atama yetkisi vermez. Salt okunur dış JWT istemcisi için bu bayrak false olur. Yetki yoksa `allowed_target` ve `suggested_payload` null döner.

Yetkili hedef:

```json
{
  "context": "UNIT_WORK",
  "allowed_target": {
    "person_id": "UUID",
    "org_id": "UUID",
    "org_name": "Ekip adı"
  },
  "suggested_payload": {
    "assignee_id": "UUID",
    "personal": false,
    "kind": "TASK",
    "priority": "NORMAL"
  }
}
```

Gerçek oluşturma mevcut `POST /api/v1/work/` akışındadır. Gövde `title`, isteğe bağlı `description`, `expected_outcome`, `assignee_id`, `priority`, `personal`, `due_at`, `kind` alanlarını kullanır. `owner_org` veya `context` istemciden alınmaz; unit bağlamı ve organizasyon sunucuda atanır. Formal atama SLA'sı, bildirim, outbox ve audit mevcut domain akışında üretilir. Önizleme yetkisi oluşturma isteğinde yeniden kontrol edilir.

Sıradan çalışanın kendi kişi ekranındaki `can_assign_work` değeri false olabilir; `can_create_personal_work=true`, mevcut kişisel iş akışını gösterir. Kişisel iş yalnız kendisine ve `personal=true` ile açılır. Yönetici formundaki atama ile kişisel hedef birbirine dönüştürülmez.

## Doğrulama

Çalıştırılan komut:

```bash
python backend/manage.py test core.tests.test_people_workload core.tests.test_directory_search_notifications --noinput --verbosity 1
```

PostgreSQL üzerinde **20 test geçti**: 7 kişi iş yükü testi ile 13 mevcut rehber/arama/bildirim regresyonu. Hiyerarşi, başka unit/çalışan/PM reddi, kapalı kişi, iptal edilmiş/süresi dolmuş rol, proje özetinde teknik bilgi sızmaması ve yalnız görünür kayıtlardan hesaplanan sayaçlar sınandı. Strict OpenAPI doğrulaması ve temel Ruff kontrolleri de geçti.
