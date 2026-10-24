import { describe, expect, it, vi } from "vitest";

import { shareCard } from "../lib/share.js";

const blob = new Blob(["png"], { type: "image/png" });
const args = { blob, fileName: "card.png", title: "T", text: "Backing Rhinos", url: "http://x" };

describe("shareCard", () => {
  it("uses native file sharing when available", async () => {
    const nav = { canShare: () => true, share: vi.fn().mockResolvedValue() };
    expect(await shareCard(args, nav)).toBe("shared-file");
    expect(nav.share.mock.calls[0][0].files[0].name).toBe("card.png");
  });

  it("falls back to link sharing when files are unsupported", async () => {
    const nav = { canShare: () => false, share: vi.fn().mockResolvedValue() };
    expect(await shareCard(args, nav)).toBe("shared-link");
  });

  it("copies the link and downloads when sharing is unavailable", async () => {
    URL.createObjectURL = vi.fn(() => "blob:x");
    URL.revokeObjectURL = vi.fn();
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const nav = { clipboard: { writeText: vi.fn().mockResolvedValue() } };
    expect(await shareCard(args, nav)).toBe("copied-and-downloaded");
    expect(nav.clipboard.writeText).toHaveBeenCalledWith("Backing Rhinos http://x");
    expect(click).toHaveBeenCalled();
  });

  it("reports a cancelled native share", async () => {
    const nav = { canShare: () => true, share: vi.fn().mockRejectedValue(Object.assign(new Error(), { name: "AbortError" })) };
    expect(await shareCard(args, nav)).toBe("cancelled");
  });
});
