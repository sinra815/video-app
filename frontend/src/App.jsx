import { useEffect, useState } from "react";
import AiForm from "./AiForm.jsx";
import { getHealth } from "./api";
import JobStatus from "./JobStatus.jsx";
import SlideshowForm from "./SlideshowForm.jsx";

export default function App() {
  const [mode, setMode] = useState("slideshow");
  const [job, setJob] = useState(null);
  const [colabAvailable, setColabAvailable] = useState(false);

  useEffect(() => {
    getHealth()
      .then((h) => setColabAvailable(h.colab_cli_available))
      .catch(() => setColabAvailable(false));
  }, []);

  return (
    <div className="app">
      <header>
        <h1>동영상 생성기</h1>
        <p className="subtitle">이미지 슬라이드쇼 또는 AI 텍스트-투-비디오로 동영상을 만드세요.</p>
      </header>

      {!job && (
        <>
          <nav className="tabs">
            <button
              className={mode === "slideshow" ? "tab active" : "tab"}
              onClick={() => setMode("slideshow")}
            >
              이미지 슬라이드쇼
            </button>
            <button
              className={mode === "ai" ? "tab active" : "tab"}
              onClick={() => setMode("ai")}
            >
              AI 텍스트-투-비디오
            </button>
          </nav>

          {mode === "slideshow" ? (
            <SlideshowForm onJobCreated={setJob} />
          ) : (
            <AiForm onJobCreated={setJob} colabAvailable={colabAvailable} />
          )}
        </>
      )}

      {job && <JobStatus job={job} onReset={() => setJob(null)} />}
    </div>
  );
}
