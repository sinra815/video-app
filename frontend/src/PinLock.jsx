import { useState } from "react";
import { getStoredPin } from "./pin";
import PinPad from "./PinPad.jsx";

export default function PinLock({ onUnlock }) {
  const [pin, setPin] = useState("");
  const [error, setError] = useState(null);

  function handleComplete(value) {
    if (value === getStoredPin()) {
      onUnlock();
    } else {
      setError("비밀번호가 올바르지 않습니다.");
      setPin("");
    }
  }

  return (
    <div className="app">
      <header>
        <h1>동영상 생성기</h1>
        <p className="subtitle">비밀번호 4자리를 입력하세요.</p>
      </header>
      <div className="panel">
        <PinPad
          value={pin}
          onChange={(v) => {
            setPin(v);
            setError(null);
          }}
          onComplete={handleComplete}
        />
        {error && <p className="error-text">{error}</p>}
      </div>
    </div>
  );
}
