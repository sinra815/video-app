import { useEffect, useRef } from "react";

// Digit entry via on-screen buttons only (no <input>), so focusing this
// never pops up the phone's native keyboard.
export default function PinPad({ value, onChange, maxLength = 4, onComplete }) {
  const firedFor = useRef("");

  useEffect(() => {
    if (value.length === maxLength && onComplete && firedFor.current !== value) {
      firedFor.current = value;
      onComplete(value);
    }
    if (value.length < maxLength) {
      firedFor.current = "";
    }
  }, [value, maxLength, onComplete]);

  function press(digit) {
    if (value.length < maxLength) {
      onChange(value + digit);
    }
  }

  function backspace() {
    onChange(value.slice(0, -1));
  }

  return (
    <div className="pin-pad">
      <div className="pin-dots">
        {Array.from({ length: maxLength }).map((_, i) => (
          <span key={i} className={i < value.length ? "pin-dot filled" : "pin-dot"} />
        ))}
      </div>
      <div className="pin-keys">
        {["1", "2", "3", "4", "5", "6", "7", "8", "9"].map((d) => (
          <button type="button" key={d} className="pin-key" onClick={() => press(d)}>
            {d}
          </button>
        ))}
        <button type="button" className="pin-key pin-key-empty" tabIndex={-1} aria-hidden="true" />
        <button type="button" className="pin-key" onClick={() => press("0")}>
          0
        </button>
        <button type="button" className="pin-key" onClick={backspace} aria-label="지우기">
          ⌫
        </button>
      </div>
    </div>
  );
}
