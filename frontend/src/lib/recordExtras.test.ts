import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "./api";
import {
  attachmentSelectionError,
  createRecordWithExtras,
  emptyRecordExtras,
  MAX_ATTACHMENT_SIZE,
} from "./recordExtras";

vi.mock("./api", async (importActual) => {
  const actual = await importActual<typeof import("./api")>();
  return { ...actual, api: vi.fn() };
});
const request = vi.mocked(api);
afterEach(() => request.mockReset());

describe("Record attachments and selected email recipients", () => {
  it("rejects oversized, active-content and excessive selections before upload", () => {
    expect(
      attachmentSelectionError([new File(["<svg/>"], "figure.svg")]),
    ).toContain("desteklenmiyor");
    expect(
      attachmentSelectionError([
        new File([new Uint8Array(MAX_ATTACHMENT_SIZE + 1)], "large.pdf"),
      ]),
    ).toContain("10 MB");
    expect(
      attachmentSelectionError(
        Array.from({ length: 6 }, (_, i) => new File(["data"], `${i}.txt`)),
      ),
    ).toContain("En fazla 5");
    expect(attachmentSelectionError([new File(["photo"], "photo.webp")])).toBe(
      "",
    );
  });
  it("stages a real multipart file and claims it together with explicit recipient preferences", async () => {
    request
      .mockResolvedValueOnce({ id: "attachment-1" })
      .mockResolvedValueOnce({ id: "work-1" });
    const file = new File(["proof"], "proof.pdf", { type: "application/pdf" });
    await createRecordWithExtras(
      "/work",
      { title: "İş" },
      { files: [file], sendEmail: true, recipientIds: ["person-1"] },
    );
    const upload = request.mock.calls[0][1]?.body as FormData;
    expect(upload).toBeInstanceOf(FormData);
    expect(upload.get("file")).toBe(file);
    expect(request.mock.calls[1][1]?.body).toEqual({
      title: "İş",
      attachment_ids: ["attachment-1"],
      send_email: true,
      notification_recipient_ids: ["person-1"],
    });
  });
  it("cleans staged files after a rejected create and preserves the original failure", async () => {
    request
      .mockResolvedValueOnce({ id: "attachment-1" })
      .mockRejectedValueOnce(new ApiError("Alıcı yetkisiz", 403))
      .mockResolvedValueOnce(null);
    await expect(
      createRecordWithExtras(
        "/cases",
        {},
        { ...emptyRecordExtras(), files: [new File(["proof"], "proof.txt")] },
      ),
    ).rejects.toThrow("Alıcı yetkisiz");
    expect(request.mock.calls[2]).toEqual([
      "/attachments/attachment-1",
      { method: "DELETE" },
    ]);
  });
  it("retries a lost response with the same request identity and payload", async () => {
    request
      .mockRejectedValueOnce(new ApiError("Bağlantı kesildi", 0))
      .mockResolvedValueOnce({ id: "project-1" });
    await createRecordWithExtras(
      "/projects",
      { title: "Proje" },
      emptyRecordExtras(),
    );
    expect(request).toHaveBeenCalledTimes(2);
    expect(request.mock.calls[1]).toEqual(request.mock.calls[0]);
  });
  it("does not post when email is enabled without a selected recipient", async () => {
    await expect(
      createRecordWithExtras(
        "/work",
        {},
        { ...emptyRecordExtras(), sendEmail: true },
      ),
    ).rejects.toThrow("en az bir kişi");
    expect(request).not.toHaveBeenCalled();
  });
});
