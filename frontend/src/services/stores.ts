export async function createStore({
  token,
  name,
}: {
  token: string;
  name: string;
}) {
  const res = await fetch("/api/stores", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      "X-Requested-With": "XMLHttpRequest",
    },
    body: JSON.stringify({ display_name: name }),
  });

  if (!res.ok) {
    const text = await res.text();
    const error = new Error(text || "Failed to create store");
    (error as Error & { status?: number }).status = res.status;
    throw error;
  }
}
