import { useState } from "react";
import { createAiJob } from "./api";

export default function AiForm({ onJobCreated, colabAvailable }) {
  const [prompt, setPrompt] = useState("");
  const [negativePrompt, setNegativePrompt] = useState("");
  const [duration, setDuration] = useState(4);
  const [gpu, setGpu] = useState("T4");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!prompt.trim()) {
      setError("프롬프트를 입력하세요.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const job = await createAiJob({
        prompt,
        negative_prompt: negativePrompt || null,
        duration_seconds: Number(duration),
        gpu,
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
        프롬프트
        <textarea
          rows={3}
          placeholder="예: a golden retriever running on a beach at sunset"
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
            max="10"
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

      {error && <p className="error-text">{error}</p>}

      <button className="button" type="submit" disabled={busy}>
        {busy ? "요청 중..." : "AI 동영상 생성"}
      </button>
    </form>
  );
}
