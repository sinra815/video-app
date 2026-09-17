import { useState } from "react";
import { getStoredPin } from "./pin";

export default function PinLock({ onUnlock }) {
  const [pin, setPin] = useState("");
  const [error, setError] = useState(null);

  function handleSubmit(e) {
    e.preventDefault();
    if (pin === getStoredPin()) {
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
      <form className="panel" onSubmit={handleSubmit}>
        <label>
          비밀번호
          <input
            type="password"
            inputMode="numeric"
            pattern="[0-9]*"
            maxLength={4}
            autoFocus
            value={pin}
            onChange={(e) => {
              setPin(e.target.value.replace(/\D/g, "").slice(0, 4));
              setError(null);
            }}
          />
        </label>
        {error && <p className="error-text">{error}</p>}
        <button className="button" type="submit" disabled={pin.length !== 4}>
          확인
        </button>
      </form>
    </div>
  );
}
