import { useState } from "react";
import { createImageToVideoJob, uploadFile } from "./api";

export default function ImageToVideoForm({ onJobCreated }) {
  const [image, setImage] = useState(null);
  const [prompt, setPrompt] = useState("");
  const [negativePrompt, setNegativePrompt] = useState("");
  const [duration, setDuration] = useState(5);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

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
      const job = await createImageToVideoJob({
        image_file_id: upload.file_id,
        prompt,
        negative_prompt: negativePrompt || null,
        duration_seconds: Number(duration),
      });
      onJobCreated(job);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="panel" onSubmit={handleSubmit}>
      <p className="notice">
        이 기능은 <a href="https://magichour.ai" target="_blank" rel="noreferrer">Magic Hour</a>{" "}
        무료 크레딧으로 동작합니다. 크레딧이 부족해지면 매일 한 번 magichour.ai에 접속해서 출석
        포인트를 받아두세요.
      </p>

      <label>
        사진
        <input type="file" accept="image/*" onChange={(e) => setImage(e.target.files[0] ?? null)} />
      </label>
      {image && <p className="hint">{image.name} 선택됨</p>}

      <label>
        프롬프트 (사진에 어떤 움직임/변화를 줄지)
        <textarea
          rows={3}
          placeholder="예: the waves gently crash on the shore"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
        />
      </label>

      <label>
        네거티브 프롬프트 (선택)
        <input
          type="text"
          value={negativePrompt}
          onChange={(e) => setNegativePrompt(e.target.value)}
        />
      </label>

      <label>
        길이(초)
        <input
          type="number"
          inputMode="numeric"
          min="1"
          max="10"
          step="1"
          value={duration}
          onChange={(e) => setDuration(e.target.value)}
        />
      </label>

      {error && <p className="error-text">{error}</p>}

      <button className="button" type="submit" disabled={busy}>
        {busy ? "업로드 중..." : "사진으로 AI 동영상 생성"}
      </button>
    </form>
  );
}
