import { useState } from "react";
import { createSlideshowJob, uploadFile } from "./api";

export default function SlideshowForm({ onJobCreated }) {
  const [images, setImages] = useState([]);
  const [audio, setAudio] = useState(null);
  const [secondsPerImage, setSecondsPerImage] = useState(3);
  const [transitionSeconds, setTransitionSeconds] = useState(0.8);
  const [resolution, setResolution] = useState("1280x720");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    if (images.length === 0) {
      setError("이미지를 하나 이상 선택하세요.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const imageUploads = await Promise.all(images.map((f) => uploadFile(f)));
      const audioUpload = audio ? await uploadFile(audio) : null;

      const job = await createSlideshowJob({
        image_file_ids: imageUploads.map((u) => u.file_id),
        audio_file_id: audioUpload ? audioUpload.file_id : null,
        seconds_per_image: Number(secondsPerImage),
        transition_seconds: Number(transitionSeconds),
        resolution,
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
      <label>
        이미지 (여러 장 선택 가능)
        <input
          type="file"
          accept="image/*"
          multiple
          onChange={(e) => setImages(Array.from(e.target.files))}
        />
      </label>
      {images.length > 0 && <p className="hint">{images.length}장 선택됨</p>}

      <label>
        배경 음악 (선택)
        <input type="file" accept="audio/*" onChange={(e) => setAudio(e.target.files[0] ?? null)} />
      </label>

      <div className="row">
        <label>
          이미지당 표시 시간(초)
          <input
            type="number"
            inputMode="decimal"
            min="0.5"
            step="0.5"
            value={secondsPerImage}
            onChange={(e) => setSecondsPerImage(e.target.value)}
          />
        </label>
        <label>
          전환 시간(초)
          <input
            type="number"
            inputMode="decimal"
            min="0"
            step="0.1"
            value={transitionSeconds}
            onChange={(e) => setTransitionSeconds(e.target.value)}
          />
        </label>
      </div>

      <label>
        해상도
        <select value={resolution} onChange={(e) => setResolution(e.target.value)}>
          <option value="1280x720">1280x720 (HD)</option>
          <option value="1920x1080">1920x1080 (Full HD)</option>
          <option value="854x480">854x480 (SD)</option>
        </select>
      </label>

      {error && <p className="error-text">{error}</p>}

      <button className="button" type="submit" disabled={busy}>
        {busy ? "업로드 중..." : "동영상 생성"}
      </button>
    </form>
  );
}
