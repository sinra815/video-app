import { useState } from "react";
import { getStoredPin, setStoredPin } from "./pin";

export default function ChangePinForm({ onClose }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState(null);
  const [done, setDone] = useState(false);

  function handleSubmit(e) {
    e.preventDefault();
    if (current !== getStoredPin()) {
      setError("현재 비밀번호가 올바르지 않습니다.");
      return;
    }
    if (next.length !== 4) {
      setError("새 비밀번호는 4자리 숫자여야 합니다.");
      return;
    }
    if (next !== confirm) {
      setError("새 비밀번호가 서로 다릅니다.");
      return;
    }
    setStoredPin(next);
    setDone(true);
    setError(null);
  }

  if (done) {
    return (
      <div className="panel">
        <p className="hint">비밀번호가 변경되었습니다.</p>
        <button type="button" className="button" onClick={onClose}>
          닫기
        </button>
      </div>
    );
  }

  return (
    <form className="panel" onSubmit={handleSubmit}>
      <label>
        현재 비밀번호
        <input
          type="password"
          inputMode="numeric"
          maxLength={4}
          autoFocus
          value={current}
          onChange={(e) => setCurrent(e.target.value.replace(/\D/g, "").slice(0, 4))}
        />
      </label>
      <label>
        새 비밀번호 (4자리)
        <input
          type="password"
          inputMode="numeric"
          maxLength={4}
          value={next}
          onChange={(e) => setNext(e.target.value.replace(/\D/g, "").slice(0, 4))}
        />
      </label>
      <label>
        새 비밀번호 확인
        <input
          type="password"
          inputMode="numeric"
          maxLength={4}
          value={confirm}
          onChange={(e) => setConfirm(e.target.value.replace(/\D/g, "").slice(0, 4))}
        />
      </label>
      {error && <p className="error-text">{error}</p>}
      <div className="row">
        <button type="submit" className="button">
          변경
        </button>
        <button type="button" className="button button-secondary" onClick={onClose}>
          취소
        </button>
      </div>
    </form>
  );
}
