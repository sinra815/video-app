import { useCallback, useEffect, useState } from "react";
import { listJobs } from "./api";

const MODE_LABELS = {
  ai_text_to_video: "AI 텍스트-투-비디오",
  ai_image_to_video: "AI 이미지-투-비디오",
  ai_image_edit: "AI 사진 편집",
};

function formatTime(unixSeconds) {
  return new Date(unixSeconds * 1000).toLocaleString();
}

export default function JobHistory({ onSelectJob }) {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try {
      const data = await listJobs();
      setJobs(data);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, 5000);
    return () => clearInterval(interval);
  }, [load]);

  return (
    <div className="panel">
      <div className="job-history-header">
        <span>작업 내역</span>
        <button type="button" className="link-button" onClick={load}>
          새로고침
        </button>
      </div>

      {loading && <p className="hint">불러오는 중...</p>}
      {error && <p className="error-text">{error}</p>}
      {!loading && jobs.length === 0 && <p className="hint">아직 요청한 작업이 없습니다.</p>}

      {jobs.length > 0 && (
        <ul className="job-list">
          {jobs.map((j) => (
            <li key={j.id} className="job-list-item" onClick={() => onSelectJob(j)}>
              <div className="job-list-main">
                <span className={`badge badge-${j.status}`}>{j.status}</span>
                <span className="job-list-mode">{MODE_LABELS[j.mode] ?? j.mode}</span>
              </div>
              <div className="job-list-meta">
                <span>{formatTime(j.created_at)}</span>
                <span className="job-progress">
                  {j.status === "failed" ? j.error : j.progress}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
