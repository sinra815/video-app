import { useEffect, useState } from "react";
import { downloadUrl, getJob } from "./api";

// Cloudflare's "Capacity temporarily exceeded" (code 3040) on the image-edit
// provider is the one failure mode confirmed transient in practice (a
// shared free-tier GPU pool being momentarily full, not a real error in the
// request) - auto-retry only for this specific signature, spread out with
// a real delay between attempts so each retry is a short-lived fresh job
// instead of one long-held thread (a longer single retry loop on the
// backend was confirmed to crash the server once - see cloudflare_image_edit.py).
const AUTO_RETRY_ERROR_MARKER = '"code":3040';
const MAX_AUTO_RETRIES = 5;
const AUTO_RETRY_DELAY_MS = 30000;

export default function JobStatus({ job, onReset, onRetry }) {
  const [current, setCurrent] = useState(job);
  const [autoRetryCount, setAutoRetryCount] = useState(0);
  const [autoRetrying, setAutoRetrying] = useState(false);

  useEffect(() => {
    setCurrent(job);
    if (job.status === "done" || job.status === "failed") return;

    const interval = setInterval(async () => {
      try {
        const updated = await getJob(job.id);
        setCurrent(updated);
        if (updated.status === "done" || updated.status === "failed") {
          clearInterval(interval);
        }
      } catch (err) {
        console.error(err);
        clearInterval(interval);
        setCurrent((prev) => ({
          ...prev,
          status: "failed",
          progress: "failed",
          error: "작업 상태를 확인할 수 없습니다 (서버가 재시작되었을 수 있습니다). 다시 시도해주세요.",
        }));
      }
    }, 1500);

    return () => clearInterval(interval);
  }, [job]);

  useEffect(() => {
    const isCapacityError = current.status === "failed" && current.error?.includes(AUTO_RETRY_ERROR_MARKER);
    if (!isCapacityError || !onRetry || autoRetryCount >= MAX_AUTO_RETRIES) return;

    setAutoRetrying(true);
    const timer = setTimeout(async () => {
      try {
        await onRetry();
      } finally {
        setAutoRetryCount((c) => c + 1);
        setAutoRetrying(false);
      }
    }, AUTO_RETRY_DELAY_MS);

    return () => clearTimeout(timer);
    // current.status/current.error (not the whole object) are the only
    // fields that should re-trigger this - a progress-only update on the
    // same failed job shouldn't restart the timer.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current.status, current.error, onRetry, autoRetryCount]);

  async function handleManualRetry() {
    setAutoRetryCount(0);
    await onRetry();
  }

  return (
    <div className="job-status">
      <div className="job-status-header">
        <span className={`badge badge-${current.status}`}>{current.status}</span>
        <span className="job-progress">{current.progress}</span>
      </div>

      {current.status === "failed" && (
        <p className="error-text">{current.error}</p>
      )}

      {autoRetrying && (
        <p className="hint">
          일시적인 용량 문제로 보여 {AUTO_RETRY_DELAY_MS / 1000}초 후 자동으로 다시 시도합니다 (
          {autoRetryCount + 1}/{MAX_AUTO_RETRIES})...
        </p>
      )}

      {current.status === "failed" && onRetry && (
        <button className="button button-secondary" onClick={handleManualRetry}>
          다시 시도
        </button>
      )}

      {current.status === "done" && current.mode === "ai_image_edit" && (
        <div className="job-result">
          <img src={downloadUrl(current.id)} alt="편집된 사진" />
          <a className="button" href={downloadUrl(current.id)} download>
            사진 다운로드
          </a>
        </div>
      )}

      {current.status === "done" && current.mode !== "ai_image_edit" && (
        <div className="job-result">
          <video controls src={downloadUrl(current.id)} />
          <a className="button" href={downloadUrl(current.id)} download>
            동영상 다운로드
          </a>
        </div>
      )}

      <button className="link-button" onClick={onReset}>
        새로 만들기
      </button>
    </div>
  );
}
