const apiBase = import.meta.env.VITE_API_BASE_URL || "http://localhost:7004";

export async function downloadAuthenticated(path: string, token: string, filename: string): Promise<void> {
  const response = await fetch(`${apiBase}${path}`, { headers: { Authorization: `Bearer ${token}` } });
  if (!response.ok) throw new Error("导出失败");
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
