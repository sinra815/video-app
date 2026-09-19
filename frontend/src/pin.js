const PIN_KEY = "video-app-pin";
const DEFAULT_PIN = "2848";
// sessionStorage (not localStorage) so the unlock only lasts "while
// connected" - it survives page reloads/navigation within the same tab,
// but clears when the tab/browser closes, unlike the PIN itself above.
const UNLOCK_SESSION_KEY = "video-app-unlocked";

export function getStoredPin() {
  return localStorage.getItem(PIN_KEY) || DEFAULT_PIN;
}

export function setStoredPin(pin) {
  localStorage.setItem(PIN_KEY, pin);
}

export function isSessionUnlocked() {
  return sessionStorage.getItem(UNLOCK_SESSION_KEY) === "1";
}

export function markSessionUnlocked() {
  sessionStorage.setItem(UNLOCK_SESSION_KEY, "1");
}
