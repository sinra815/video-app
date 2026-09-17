import { useState } from "react";
import { createImageToVideoJob, uploadFile } from "./api";

export default function ImageToVideoForm({ onJobCreated, colabAvailable }) {
  const [image, setImage] = useState(null);
  const [prompt, setPrompt] = useState("");
  const [negativePrompt, setNegativePrompt] = useState("");
  const [duration, setDuration] = useState(2);
  const [gpu, setGpu] = useState("T4");
  const [notifyEmail, setNotifyEmail] = useState(() => localStorage.getItem("notifyEmail") || "");
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
      if (notifyEmail) localStorage.setItem("notifyEmail", notifyEmail);
      const job = await createImageToVideoJob({
        image_file_id: upload.file_id,
        prompt,
        negative_prompt: negativePrompt || null,
        duration_seconds: Number(duration),
        gpu,
        notify_email: notifyEmail || null,
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
      {!colabAvailable && (
        <p className="notice">
          이 서버에는 google-colab-cli가 연결되어 있지 않습니다 (Linux/macOS + Google 계정 인증 필요).
          작업을 제출할 수는 있지만 실패로 처리됩니다. 백엔드 README의 Colab 연동 섹션을 참고하세요.
        </p>
      )}

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

      <div className="row">
        <label>
          길이(초)
          <input
            type="number"
            min="1"
            max="4"
            step="1"
            value={duration}
            onChange={(e) => setDuration(e.target.value)}
          />
        </label>
        <label>
          GPU
          <select value={gpu} onChange={(e) => setGpu(e.target.value)}>
            <option value="T4">T4</option>
            <option value="L4">L4</option>
            <option value="A100">A100</option>
          </select>
        </label>
      </div>

      <label>
        완료 시 알림 받을 이메일 (선택)
        <input
          type="email"
          placeholder="you@example.com"
          value={notifyEmail}
          onChange={(e) => setNotifyEmail(e.target.value)}
        />
      </label>

      {error && <p className="error-text">{error}</p>}

      <button className="button" type="submit" disabled={busy}>
        {busy ? "업로드 중..." : "사진으로 AI 동영상 생성"}
      </button>
    </form>
  );
}
