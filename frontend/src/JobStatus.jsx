import { useEffect, useState } from "react";
import { downloadUrl, getJob } from "./api";

export default function JobStatus({ job, onReset }) {
  const [current, setCurrent] = useState(job);

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

  return (
    <div className="job-status">
      <div className="job-status-header">
        <span className={`badge badge-${current.status}`}>{current.status}</span>
        <span className="job-progress">{current.progress}</span>
      </div>

      {current.status === "failed" && (
        <p className="error-text">{current.error}</p>
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
