/** Display labels preserve canonical directory names in the API. */
const labels: Record<string, string> = {
  "cyber security": "Siber Güvenlik",
  "infrastructure security": "Altyapı Güvenliği",
  "security assurance & architecture": "Güvenlik Güvence ve Mimarisi",
  "cyber defence center": "Siber Savunma Merkezi",
  "identity access management": "Kimlik ve Erişim Yönetimi",
  "offensive security": "Ofansif Güvenlik",
  "security management": "Güvenlik Yönetimi",
  "managed security services": "Yönetilen Güvenlik Hizmetleri",
  "application security testing": "Uygulama Güvenliği Testleri",
  "security services management": "Güvenlik Hizmetleri Yönetimi",
  "security services operations": "Güvenlik Hizmetleri Operasyonları",
  "identity management operations": "Kimlik Yönetimi Operasyonları",
  "access management operations": "Erişim Yönetimi Operasyonları",
  "cyber defence center analysis": "Siber Savunma Merkezi Analiz Ekibi",
  "digital forensics incident response":
    "Dijital Adli İnceleme ve Olay Müdahalesi",
};

export function organizationLabel(value = "") {
  return labels[value.toLowerCase()] || value;
}
