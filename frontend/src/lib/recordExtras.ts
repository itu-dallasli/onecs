import { api, ApiError } from "./api";

export const MAX_ATTACHMENT_COUNT = 5;
export const MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024;
export const ATTACHMENT_ACCEPT =
  ".pdf,.txt,.csv,.png,.jpg,.jpeg,.webp,.docx,.xlsx,.pptx";
const allowedExtensions = new Set(ATTACHMENT_ACCEPT.split(","));

export type RecordExtrasValue = {
  files: File[];
  sendEmail: boolean;
  recipientIds: string[];
};

export function emptyRecordExtras(): RecordExtrasValue {
  return { files: [], sendEmail: false, recipientIds: [] };
}

export function attachmentSelectionError(files: File[]): string {
  if (files.length > MAX_ATTACHMENT_COUNT)
    return `En fazla ${MAX_ATTACHMENT_COUNT} dosya ekleyebilirsiniz.`;
  for (const file of files) {
    if (!file.size) return `“${file.name}” boş bir dosya.`;
    if (file.size > MAX_ATTACHMENT_SIZE)
      return `“${file.name}” 10 MB sınırını aşıyor.`;
    const extension = file.name
      .toLocaleLowerCase("en-US")
      .match(/\.[^.]+$/)?.[0];
    if (!extension || !allowedExtensions.has(extension))
      return `“${file.name}” desteklenmiyor. PDF, Office belgesi, metin veya fotoğraf seçin.`;
  }
  return "";
}

export function attachmentSize(size: number): string {
  return size >= 1024 * 1024
    ? `${(size / (1024 * 1024)).toLocaleString("tr-TR", { maximumFractionDigits: 1 })} MB`
    : `${Math.max(1, Math.ceil(size / 1024))} KB`;
}

async function postWithRetry<T = any>(path: string, body: unknown): Promise<T> {
  const headers = { "X-Request-ID": crypto.randomUUID() };
  try {
    return await api<T>(path, { method: "POST", headers, body });
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 0) throw error;
    return api<T>(path, { method: "POST", headers, body });
  }
}

/** Keep a failed create from leaving its successfully staged files behind. */
export async function createRecordWithExtras<T = any>(
  path: string,
  payload: Record<string, unknown>,
  extras: RecordExtrasValue,
): Promise<T> {
  const validationError = attachmentSelectionError(extras.files);
  if (validationError) throw new Error(validationError);
  if (extras.sendEmail && !extras.recipientIds.length)
    throw new Error("E-posta bildirimi için en az bir kişi seçin.");
  if (extras.recipientIds.length > 20)
    throw new Error("E-posta bildirimi için en fazla 20 kişi seçebilirsiniz.");
  const stagedIds: string[] = [];
  try {
    // Sequential staging makes cleanup deterministic even if one upload fails.
    for (const file of extras.files) {
      const body = new FormData();
      body.append("file", file);
      const attachment = await postWithRetry<{ id: string }>(
        "/attachments",
        body,
      );
      stagedIds.push(attachment.id);
    }
    return await postWithRetry<T>(path, {
      ...payload,
      attachment_ids: stagedIds,
      send_email: extras.sendEmail,
      notification_recipient_ids: extras.sendEmail ? extras.recipientIds : [],
    });
  } catch (error) {
    await Promise.allSettled(
      stagedIds.map((id) => api(`/attachments/${id}`, { method: "DELETE" })),
    );
    throw error;
  }
}
