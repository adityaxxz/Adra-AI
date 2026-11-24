/** `<name>.zip` using only characters that are safe on every filesystem. */
export function zipName(name: string, suffix = ''): string {
  const safe = `${name}${suffix}`.replace(/[^A-Za-z0-9._-]+/g, '-').replace(/^[-.]+|[-.]+$/g, '');
  return `${safe || 'download'}.zip`;
}

/** Saves a blob through a temporary link (the download needs the auth header, so a plain href won't do). */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
