const PIN_KEY = "video-app-pin";
const DEFAULT_PIN = "2848";

export function getStoredPin() {
  return localStorage.getItem(PIN_KEY) || DEFAULT_PIN;
}

export function setStoredPin(pin) {
  localStorage.setItem(PIN_KEY, pin);
}
