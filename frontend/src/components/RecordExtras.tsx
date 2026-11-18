import { useEffect, useId, useRef, useState } from "react";
import {
  Check,
  Download,
  FileText,
  ImagePlus,
  LoaderCircle,
  Mail,
  Paperclip,
  Search,
  X,
} from "lucide-react";
import { list, useResource } from "../lib/api";
import {
  ATTACHMENT_ACCEPT,
  MAX_ATTACHMENT_COUNT,
  attachmentSelectionError,
  attachmentSize,
} from "../lib/recordExtras";
import type { RecordExtrasValue } from "../lib/recordExtras";
import { ErrorState } from "./ui";
import "../styles/record-extras.css";

export { emptyRecordExtras } from "../lib/recordExtras";
export type { RecordExtrasValue } from "../lib/recordExtras";

type Recipient = {
  id: string;
  display_name?: string;
  username?: string;
  primary_org_name?: string;
  primary_org?: { name?: string; code?: string };
  is_active?: boolean;
};

function SelectedFile({
  file,
  disabled,
  onRemove,
}: {
  file: File;
  disabled?: boolean;
  onRemove: () => void;
}) {
  const [preview, setPreview] = useState("");
  useEffect(() => {
    if (!/^image\/(png|jpeg|webp)$/.test(file.type)) return;
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  return (
    <li className="record-extra-file">
      <span className="record-extra-file-icon">
        {preview ? <img src={preview} alt="" /> : <FileText size={21} />}
      </span>
      <span className="record-extra-file-name">
        <strong>{file.name}</strong>
        <small>{attachmentSize(file.size)}</small>
      </span>
      <button
        type="button"
        className="record-extra-remove"
        aria-label={`${file.name} dosyasını kaldır`}
        disabled={disabled}
        onClick={onRemove}
      >
        <X size={16} />
      </button>
    </li>
  );
}

export default function RecordExtras({
  value,
  onChange,
  defaultRecipients = [],
  disabled = false,
  emailHint = "Seçilen kişilere uygulamadaki bildirimlere yönlendiren kısa bir e-posta gönderilir. Alıcıların kayıt erişimi sunucuda doğrulanır; eksik e-posta adresi teslimi engelleyebilir.",
}: {
  value: RecordExtrasValue;
  onChange: (value: RecordExtrasValue) => void;
  defaultRecipients?: Recipient[];
  disabled?: boolean;
  emailHint?: string;
}) {
  const inputId = useId();
  const [fileError, setFileError] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [dragging, setDragging] = useState(false);
  const [knownPeople, setKnownPeople] = useState<Recipient[]>([]);
  const previousDefaults = useRef<string[]>([]);
  const defaultIds = defaultRecipients
    .map((person) => person.id)
    .filter(Boolean);
  const defaultsKey = defaultIds.join(",");
  useEffect(() => {
    const previous = previousDefaults.current;
    previousDefaults.current = defaultIds;
    if (!value.sendEmail || previous.join(",") === defaultsKey) return;
    const next = [
      ...new Set([
        ...value.recipientIds.filter((id) => !previous.includes(id)),
        ...defaultIds,
      ]),
    ];
    onChange({ ...value, recipientIds: next });
  }, [defaultsKey, value.sendEmail]);
  useEffect(() => {
    const timer = window.setTimeout(() => setQuery(search.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [search]);
  const people = useResource<any>(
    value.sendEmail
      ? `/people?limit=60&search=${encodeURIComponent(query)}`
      : null,
    undefined,
    0,
  );
  useEffect(() => {
    if (!people.data) return;
    setKnownPeople((previous) => [
      ...new Map(
        [...previous, ...list<Recipient>(people.data)].map((person) => [
          person.id,
          person,
        ]),
      ).values(),
    ]);
  }, [people.data]);
  const byId = new Map(
    [...knownPeople, ...defaultRecipients].map((person) => [person.id, person]),
  );
  const options = [
    ...new Map(
      [...defaultRecipients, ...list<Recipient>(people.data)]
        .filter((person) => person.is_active !== false)
        .map((person) => [person.id, person]),
    ).values(),
  ];

  function addFiles(incoming: File[]) {
    if (disabled) return;
    const next = [...value.files];
    for (const file of incoming) {
      if (
        !next.some(
          (existing) =>
            existing.name === file.name &&
            existing.size === file.size &&
            existing.lastModified === file.lastModified,
        )
      )
        next.push(file);
    }
    const error = attachmentSelectionError(next);
    setFileError(error);
    if (!error) onChange({ ...value, files: next });
  }
  function toggleRecipient(id: string) {
    onChange({
      ...value,
      recipientIds: value.recipientIds.includes(id)
        ? value.recipientIds.filter((current) => current !== id)
        : [...value.recipientIds, id],
    });
  }
  return (
    <section
      className="record-extras"
      aria-label="Dosyalar ve e-posta bildirimi"
    >
      <div className="record-extras-section">
        <div className="record-extras-heading">
          <Paperclip size={18} />
          <div>
            <strong>Dosya ve fotoğraflar</strong>
            <small>İsteğe bağlı · En fazla 5 dosya, dosya başına 10 MB</small>
          </div>
          <span>
            {value.files.length}/{MAX_ATTACHMENT_COUNT}
          </span>
        </div>
        <label
          htmlFor={inputId}
          className={`record-extra-dropzone${dragging ? " is-dragging" : ""}${disabled ? " is-disabled" : ""}`}
          onDragOver={(event) => {
            event.preventDefault();
            if (!disabled) setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            addFiles(Array.from(event.dataTransfer.files));
          }}
        >
          <ImagePlus size={23} />
          <span>
            <strong>Dosya seçin veya bu alana sürükleyin</strong>
            <small>
              PDF, Word, Excel, PowerPoint, metin, CSV, PNG, JPG ve WebP
            </small>
          </span>
          <input
            id={inputId}
            type="file"
            multiple
            accept={ATTACHMENT_ACCEPT}
            disabled={disabled}
            onChange={(event) => {
              addFiles(Array.from(event.target.files || []));
              event.target.value = "";
            }}
          />
        </label>
        {!!value.files.length && (
          <ul className="record-extra-files">
            {value.files.map((file, index) => (
              <SelectedFile
                key={`${file.name}-${file.size}-${file.lastModified}`}
                file={file}
                disabled={disabled}
                onRemove={() => {
                  onChange({
                    ...value,
                    files: value.files.filter((_, i) => i !== index),
                  });
                  setFileError("");
                }}
              />
            ))}
          </ul>
        )}
        {fileError && (
          <p className="record-extras-error" role="alert">
            {fileError}
          </p>
        )}
        {disabled && !!value.files.length && (
          <p className="record-extras-progress" role="status">
            <LoaderCircle size={15} />
            Dosyalar yükleniyor, kayıt hazırlanıyor…
          </p>
        )}
        <p className="record-extras-note">
          Ekleri yalnızca bu kayda erişimi olan kişiler indirebilir. Dosyalar
          e-postaya eklenmez.
        </p>
      </div>
      <div className="record-extras-section">
        <label className="record-extras-email-switch">
          <input
            type="checkbox"
            checked={value.sendEmail}
            disabled={disabled}
            onChange={(event) =>
              onChange({
                ...value,
                sendEmail: event.target.checked,
                recipientIds: event.target.checked
                  ? [...new Set([...value.recipientIds, ...defaultIds])]
                  : value.recipientIds,
              })
            }
          />
          <Mail size={18} />
          <span>
            <strong>Seçilen kişilere e-posta bildirimi gönder</strong>
            <small>{emailHint}</small>
          </span>
        </label>
        {value.sendEmail && (
          <div className="record-extras-recipients">
            <label className="record-extras-search">
              <Search size={16} />
              <input
                value={search}
                disabled={disabled}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Ad, kullanıcı adı veya birim ara…"
                aria-label="E-posta bildirimi alıcısı ara"
              />
            </label>
            {!!value.recipientIds.length && (
              <div
                className="record-extra-recipient-tags"
                aria-label="Seçilen e-posta alıcıları"
              >
                {value.recipientIds.map((id) => (
                  <span key={id}>
                    {byId.get(id)?.display_name ||
                      byId.get(id)?.username ||
                      "Seçilen kişi"}
                    <button
                      type="button"
                      disabled={disabled}
                      aria-label={`${byId.get(id)?.display_name || "Kişi"} alıcısını kaldır`}
                      onClick={() => toggleRecipient(id)}
                    >
                      <X size={12} />
                    </button>
                  </span>
                ))}
              </div>
            )}
            {people.error ? (
              <ErrorState message={people.error} onRetry={people.refresh} />
            ) : (
              <div
                className="record-extra-recipient-options"
                role="group"
                aria-label="E-posta alıcıları"
              >
                {people.loading && (
                  <p className="record-extras-note">Kişiler yükleniyor…</p>
                )}
                {options.map((person) => (
                  <label key={person.id}>
                    <input
                      type="checkbox"
                      disabled={
                        disabled ||
                        (!value.recipientIds.includes(person.id) &&
                          value.recipientIds.length >= 20)
                      }
                      checked={value.recipientIds.includes(person.id)}
                      onChange={() => toggleRecipient(person.id)}
                    />
                    <span>
                      <strong>{person.display_name || person.username}</strong>
                      <small>
                        {person.primary_org_name ||
                          person.primary_org?.name ||
                          person.primary_org?.code ||
                          ""}
                      </small>
                    </span>
                    {value.recipientIds.includes(person.id) && (
                      <Check size={15} />
                    )}
                  </label>
                ))}
                {!people.loading && !options.length && (
                  <p className="record-extras-note">
                    Bu arama için kişi bulunamadı.
                  </p>
                )}
              </div>
            )}
            <p
              className={
                value.recipientIds.length
                  ? "record-extras-note"
                  : "record-extras-error"
              }
            >
              {value.recipientIds.length
                ? `${value.recipientIds.length}/20 kişi seçildi. Bu seçim kayıt erişimi veya görev ataması vermez.`
                : "E-posta bildirimi için en az bir kişi seçin."}
            </p>
          </div>
        )}
      </div>
    </section>
  );
}

export function RecordAttachments({
  resourceType,
  resourceId,
  enabled = true,
}: {
  resourceType: string;
  resourceId: string;
  enabled?: boolean;
}) {
  const resource = useResource<any>(
    enabled
      ? `/attachments?resource_type=${encodeURIComponent(resourceType)}&resource_id=${encodeURIComponent(resourceId)}`
      : null,
    undefined,
    0,
  );
  const attachments = list<any>(resource.data);
  if (!enabled || (!resource.loading && !resource.error && !attachments.length))
    return null;
  return (
    <section
      className="record-attachments detail-block"
      aria-label="Kayıt ekleri"
    >
      <h3>
        <Paperclip size={17} />
        Dosyalar ve fotoğraflar
      </h3>
      {resource.loading ? (
        <p className="record-extras-note">Ekler yükleniyor…</p>
      ) : resource.error ? (
        <ErrorState message={resource.error} onRetry={resource.refresh} />
      ) : (
        <ul className="record-extra-files">
          {attachments.map((item) => (
            <li key={item.id} className="record-extra-file">
              <span className="record-extra-file-icon">
                <FileText size={21} />
              </span>
              <span className="record-extra-file-name">
                <strong>{item.name}</strong>
                <small>
                  {attachmentSize(item.size)}
                  {item.status === "PENDING_SCAN"
                    ? " · Güvenlik taraması bekleniyor"
                    : item.status === "REJECTED" || item.status === "BLOCKED"
                      ? " · Dosya kullanıma kapalı"
                      : item.scan_status === "unscanned"
                        ? " · Güvenlik taraması yapılmadı"
                        : ""}
                </small>
              </span>
              {item.status === "READY" ? (
                <a
                  className="record-extra-download"
                  href={`/api/v1/attachments/${encodeURIComponent(item.id)}/download/`}
                  aria-label={`${item.name} dosyasını indir`}
                >
                  <Download size={17} />
                  <span>İndir</span>
                </a>
              ) : (
                <span className="record-extra-pending">
                  {item.status === "PENDING_SCAN" ? "Bekliyor" : "Kapalı"}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
