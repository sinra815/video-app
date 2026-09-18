import { useEffect, useState } from "react";
import AiForm from "./AiForm.jsx";
import { getHealth } from "./api";
import ChangePinForm from "./ChangePinForm.jsx";
import ImageEditForm from "./ImageEditForm.jsx";
import ImageToVideoForm from "./ImageToVideoForm.jsx";
import JobHistory from "./JobHistory.jsx";
import JobStatus from "./JobStatus.jsx";
import PinLock from "./PinLock.jsx";
import { isSessionUnlocked, markSessionUnlocked } from "./pin";

export default function App() {
  const [unlocked, setUnlocked] = useState(isSessionUnlocked);
  const [showChangePin, setShowChangePin] = useState(false);
  const [mode, setMode] = useState("edit");
  const [job, setJob] = useState(null);
  const [colabAvailable, setColabAvailable] = useState(false);

  useEffect(() => {
    getHealth()
      .then((h) => setColabAvailable(h.colab_cli_available))
      .catch(() => setColabAvailable(false));
  }, []);

  if (!unlocked) {
    return (
      <PinLock
        onUnlock={() => {
          markSessionUnlocked();
          setUnlocked(true);
        }}
      />
    );
  }

  return (
    <div className="app">
      <header>
        <h1>AI 사진/동영상 생성기</h1>
        <p className="subtitle">사진을 올리고 프롬프트로 원하는 모습으로 바꾸거나, 동영상으로 만드세요.</p>
        <button type="button" className="link-button" onClick={() => setShowChangePin(true)}>
          비밀번호 변경
        </button>
      </header>

      {showChangePin && <ChangePinForm onClose={() => setShowChangePin(false)} />}

      {!showChangePin && !job && (
        <>
          <nav className="tabs">
            <button
              className={mode === "edit" ? "tab active" : "tab"}
              onClick={() => setMode("edit")}
            >
              사진 편집
            </button>
            <button
              className={mode === "image" ? "tab active" : "tab"}
              onClick={() => setMode("image")}
            >
              사진 + 프롬프트(영상)
            </button>
            <button
              className={mode === "ai" ? "tab active" : "tab"}
              onClick={() => setMode("ai")}
            >
              AI 텍스트-투-비디오
            </button>
            <button
              className={mode === "history" ? "tab active" : "tab"}
              onClick={() => setMode("history")}
            >
              작업 내역
            </button>
          </nav>

          {mode === "edit" && <ImageEditForm onJobCreated={setJob} />}
          {mode === "ai" && <AiForm onJobCreated={setJob} colabAvailable={colabAvailable} />}
          {mode === "image" && <ImageToVideoForm onJobCreated={setJob} />}
          {mode === "history" && <JobHistory onSelectJob={setJob} />}
        </>
      )}

      {!showChangePin && job && <JobStatus job={job} onReset={() => setJob(null)} />}
    </div>
  );
}
