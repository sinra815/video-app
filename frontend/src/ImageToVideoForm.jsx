import { useEffect, useState } from "react";
import { createImageToVideoJob, getProviders, uploadFile } from "./api";
import MagicHourClaimButton from "./MagicHourClaimButton.jsx";

const MIN_DURATION_SECONDS = 1;
const MAX_DURATION_SECONDS = 10;
// Magic Hour image-to-video charges per rendered second, priced per model;
// a free-tier account defaults to their cheapest model (ltx-2.5), which
// falls in the ~24 credits/sec tier per Magic Hour's own published rates.
// Not billed by us - only used to suggest a duration the current balance
// can actually afford, so a low-credit account doesn't default to 5s and
// fail partway through rendering.
const MAGIC_HOUR_CREDITS_PER_SECOND = 24;

export default function ImageToVideoForm({ onJobCreated }) {
  const [image, setImage] = useState(null);
  const [prompt, setPrompt] = useState("");
  const [negativePrompt, setNegativePrompt] = useState("");
  const [duration, setDuration] = useState(5);
  const [providers, setProviders] = useState([]);
  const [provider, setProvider] = useState("magic_hour");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    getProviders("video")
      .then((list) => {
        setProviders(list);
        setProvider((current) =>
          list.some((p) => p.id === current && p.usable) ? current : list.find((p) => p.usable)?.id ?? current
        );

        const magicHour = list.find((p) => p.id === "magic_hour");
        if (magicHour?.usable && typeof magicHour.credits === "number") {
          const affordableSeconds = Math.floor(magicHour.credits / MAGIC_HOUR_CREDITS_PER_SECOND);
          setDuration(Math.max(MIN_DURATION_SECONDS, Math.min(MAX_DURATION_SECONDS, affordableSeconds)));
        }
      })
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
      const job = await createImageToVideoJob({
        image_file_id: upload.file_id,
        prompt,
        negative_prompt: negativePrompt || null,
        duration_seconds: Number(duration),
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
            <option key={p.id} value={p.id} disabled={!p.usable}>
              {p.label}
              {p.usable ? ` (크레딧 ${p.credits ?? "무제한"})` : " (사용 불가)"}
            </option>
          ))}
        </select>
      </label>
      {selected?.error && <p className="error-text">{selected.error}</p>}

      <p className="notice">
        이 기능은 <a href="https://magichour.ai" target="_blank" rel="noreferrer">Magic Hour</a>{" "}
        무료 크레딧으로 동작합니다. 크레딧이 부족해지면 아래 버튼으로 매일 한 번 magichour.ai에
        접속해서 출석 포인트를 받아두세요.
      </p>
      <MagicHourClaimButton />

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
          min={MIN_DURATION_SECONDS}
          max={MAX_DURATION_SECONDS}
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
