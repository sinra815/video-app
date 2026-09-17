import { useState } from "react";
import { getStoredPin, setStoredPin } from "./pin";
import PinPad from "./PinPad.jsx";

const LABELS = {
  current: "현재 비밀번호",
  next: "새 비밀번호 (4자리)",
  confirm: "새 비밀번호 확인",
};

export default function ChangePinForm({ onClose }) {
  const [step, setStep] = useState("current");
  const [pin, setPin] = useState("");
  const [newPin, setNewPin] = useState("");
  const [error, setError] = useState(null);

  function handleCurrentComplete(value) {
    if (value !== getStoredPin()) {
      setError("현재 비밀번호가 올바르지 않습니다.");
      setPin("");
      return;
    }
    setError(null);
    setPin("");
    setStep("next");
  }

  function handleNextComplete(value) {
    setNewPin(value);
    setPin("");
    setError(null);
    setStep("confirm");
  }

  function handleConfirmComplete(value) {
    if (value !== newPin) {
      setError("새 비밀번호가 서로 다릅니다. 다시 입력하세요.");
      setPin("");
      setNewPin("");
      setStep("next");
      return;
    }
    setStoredPin(value);
    setStep("done");
  }

  if (step === "done") {
    return (
      <div className="panel">
        <p className="hint">비밀번호가 변경되었습니다.</p>
        <button type="button" className="button" onClick={onClose}>
          닫기
        </button>
      </div>
    );
  }

  const handlers = {
    current: handleCurrentComplete,
    next: handleNextComplete,
    confirm: handleConfirmComplete,
  };

  return (
    <div className="panel">
      <p className="hint">{LABELS[step]}</p>
      <PinPad value={pin} onChange={setPin} onComplete={handlers[step]} />
      {error && <p className="error-text">{error}</p>}
      <button type="button" className="button button-secondary" onClick={onClose}>
        취소
      </button>
    </div>
  );
}
