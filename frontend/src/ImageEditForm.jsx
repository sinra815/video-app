import { useEffect, useState } from "react";
import { createImageEditJob, getProviders, uploadFile } from "./api";

export default function ImageEditForm({ onJobCreated }) {
  const [image, setImage] = useState(null);
  const [prompt, setPrompt] = useState("");
  const [providers, setProviders] = useState([]);
  const [provider, setProvider] = useState("magic_hour");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    getProviders()
      .then(setProviders)
      .catch(() => setProviders([]));
  }, []);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!image) {
      setError("사진을 선택하세요.");
      return;
    }
    if (!prompt.trim()) {
      setError("프롬프트를 입력하세요.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const upload = await uploadFile(image);
      const job = await createImageEditJob({
        image_file_id: upload.file_id,
        prompt,
        provider,
      });
      onJobCreated(job);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const selected = providers.find((p) => p.id === provider);

  return (
    <form className="panel" onSubmit={handleSubmit}>
      <label>
        생성 API
        <select value={provider} onChange={(e) => setProvider(e.target.value)}>
          {providers.map((p) => (
            <option key={p.id} value={p.id}>
              {p.label}
              {p.configured ? ` (크레딧 ${p.credits ?? "확인 실패"})` : " (설정 안 됨)"}
            </option>
          ))}
        </select>
      </label>
      {selected?.error && <p className="error-text">크레딧 조회 실패: {selected.error}</p>}

      <label>
        사진
        <input type="file" accept="image/*" onChange={(e) => setImage(e.target.files[0] ?? null)} />
      </label>
      {image && <p className="hint">{image.name} 선택됨</p>}

      <label>
        프롬프트 (사진을 어떻게 바꿀지)
        <textarea
          rows={3}
          placeholder="예: give the person sunglasses and a red jacket"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
        />
      </label>

      {error && <p className="error-text">{error}</p>}

      <button className="button" type="submit" disabled={busy}>
        {busy ? "업로드 중..." : "사진 편집하기"}
      </button>
    </form>
  );
}
