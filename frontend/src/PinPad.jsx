// Digit entry via on-screen buttons only (no <input>), so focusing this
// never pops up the phone's native keyboard. Requires an explicit "확인"
// press to submit rather than auto-submitting on the 4th digit.
export default function PinPad({ value, onChange, maxLength = 4, onComplete }) {
  function press(digit) {
    if (value.length < maxLength) {
      onChange(value + digit);
    }
  }

  function backspace() {
    onChange(value.slice(0, -1));
  }

  function clearAll() {
    onChange("");
  }

  function confirm() {
    if (value.length === maxLength) {
      onComplete(value);
    }
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
        <button type="button" className="pin-key pin-key-text" onClick={clearAll}>
          모두
          <br />
          지우기
        </button>
        <button type="button" className="pin-key" onClick={() => press("0")}>
          0
        </button>
        <button type="button" className="pin-key" onClick={backspace} aria-label="한 자리 지우기">
          ⌫
        </button>
      </div>
      <button
        type="button"
        className="button pin-confirm"
        disabled={value.length !== maxLength}
        onClick={confirm}
      >
        확인
      </button>
    </div>
  );
}
