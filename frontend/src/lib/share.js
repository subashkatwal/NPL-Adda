/**
 * Share a fan-card image with the best mechanism the browser offers:
 * native file share -> native link share -> copy link + download the image.
 * Returns which path was used so the UI can tell the fan what happened.
 */
export async function shareCard({ blob, fileName, title, text, url }, nav = globalThis.navigator) {
  const file = blob ? new File([blob], fileName, { type: "image/png" }) : null;
  try {
    if (file && nav?.canShare?.({ files: [file] })) {
      await nav.share({ files: [file], title, text });
      return "shared-file";
    }
    if (nav?.share) {
      await nav.share({ title, text, url });
      return "shared-link";
    }
  } catch (err) {
    if (err?.name === "AbortError") return "cancelled";
  }
  let copied = false;
  try {
    await nav?.clipboard?.writeText(`${text} ${url}`);
    copied = Boolean(nav?.clipboard);
  } catch {
    copied = false;
  }
  if (blob) downloadBlob(blob, fileName);
  return copied ? "copied-and-downloaded" : "downloaded";
}

export function downloadBlob(blob, fileName) {
  const href = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement("a"), { href, download: fileName });
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(href), 1000);
}
