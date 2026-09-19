import { useState } from "react";
import { createAiJob } from "./api";

export default function AiForm({ onJobCreated, colabAvailable }) {
  const [prompt, setPrompt] = useState("");
  const [negativePrompt, setNegativePrompt] = useState("");
  const [duration, setDuration] = useState(4);
  // L4/A100 fail every time with "Backend rejected accelerator ... no quota
  // or entitlement" on this free Colab account (confirmed against real
  // failed jobs) - T4 is the only tier this account can actually use, so
  // it's not offered as a choice.
  const gpu = "T4";
  const [notifyEmail, setNotifyEmail] = useState(
    () => localStorage.getItem("notifyEmail") || "sinra815@gmail.com"
  );
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
      if (notifyEmail) localStorage.setItem("notifyEmail", notifyEmail);
      const job = await createAiJob({
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
            inputMode="numeric"
            min="1"
            max="10"
            step="1"
            value={duration}
            onChange={(e) => setDuration(e.target.value)}
          />
        </label>
        <label>
          GPU
          <input type="text" value="T4 (무료 Colab 계정에서 사용 가능한 유일한 옵션)" disabled />
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
        {busy ? "요청 중..." : "AI 동영상 생성"}
      </button>
    </form>
  );
}
