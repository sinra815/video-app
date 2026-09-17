const BASE = `${import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000"}/api`;

export async function uploadFile(file) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/uploads`, { method: "POST", body: form });
  if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
  return res.json();
}

export async function createSlideshowJob(payload) {
  const res = await fetch(`${BASE}/jobs/slideshow`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Job creation failed: ${res.status}`);
  return res.json();
}

export async function createAiJob(payload) {
  const res = await fetch(`${BASE}/jobs/ai`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Job creation failed: ${res.status}`);
  return res.json();
}

export async function createImageToVideoJob(payload) {
  const res = await fetch(`${BASE}/jobs/ai-image-to-video`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Job creation failed: ${res.status}`);
  return res.json();
}

export async function createImageEditJob(payload) {
  const res = await fetch(`${BASE}/jobs/ai-image-edit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Job creation failed: ${res.status}`);
  return res.json();
}

export async function getProviders() {
  const res = await fetch(`${BASE}/providers`);
  if (!res.ok) throw new Error(`Provider list failed: ${res.status}`);
  return res.json();
}

export async function listJobs() {
  const res = await fetch(`${BASE}/jobs`);
  if (!res.ok) throw new Error(`Job list failed: ${res.status}`);
  return res.json();
}

export async function getJob(jobId) {
  const res = await fetch(`${BASE}/jobs/${jobId}`);
  if (!res.ok) throw new Error(`Job lookup failed: ${res.status}`);
  return res.json();
}

export function downloadUrl(jobId) {
  return `${BASE}/jobs/${jobId}/download`;
}

export async function getHealth() {
  const res = await fetch(`${BASE}/health`);
  if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
  return res.json();
}
