import { useEffect, useState } from "react";
import AiForm from "./AiForm.jsx";
import { getHealth } from "./api";
import ChangePinForm from "./ChangePinForm.jsx";
import ImageToVideoForm from "./ImageToVideoForm.jsx";
import JobHistory from "./JobHistory.jsx";
import JobStatus from "./JobStatus.jsx";
import PinLock from "./PinLock.jsx";

export default function App() {
  const [unlocked, setUnlocked] = useState(false);
  const [showChangePin, setShowChangePin] = useState(false);
  const [mode, setMode] = useState("image");
  const [job, setJob] = useState(null);
  const [colabAvailable, setColabAvailable] = useState(false);

  useEffect(() => {
    getHealth()
      .then((h) => setColabAvailable(h.colab_cli_available))
      .catch(() => setColabAvailable(false));
  }, []);

  if (!unlocked) {
    return <PinLock onUnlock={() => setUnlocked(true)} />;
  }

  return (
    <div className="app">
      <header>
        <h1>동영상 생성기</h1>
        <p className="subtitle">AI 텍스트-투-비디오 또는 사진+프롬프트로 동영상을 만드세요.</p>
        <button type="button" className="link-button" onClick={() => setShowChangePin(true)}>
          비밀번호 변경
        </button>
      </header>

      {showChangePin && <ChangePinForm onClose={() => setShowChangePin(false)} />}

      {!showChangePin && !job && (
        <>
          <nav className="tabs">
            <button
              className={mode === "ai" ? "tab active" : "tab"}
              onClick={() => setMode("ai")}
            >
              AI 텍스트-투-비디오
            </button>
            <button
              className={mode === "image" ? "tab active" : "tab"}
              onClick={() => setMode("image")}
            >
              사진 + 프롬프트
            </button>
            <button
              className={mode === "history" ? "tab active" : "tab"}
              onClick={() => setMode("history")}
            >
              작업 내역
            </button>
          </nav>

          {mode === "ai" && <AiForm onJobCreated={setJob} colabAvailable={colabAvailable} />}
          {mode === "image" && <ImageToVideoForm onJobCreated={setJob} />}
          {mode === "history" && <JobHistory onSelectJob={setJob} />}
        </>
      )}

      {!showChangePin && job && <JobStatus job={job} onReset={() => setJob(null)} />}
    </div>
  );
}
