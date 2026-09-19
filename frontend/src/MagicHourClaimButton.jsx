import { useState } from "react";

// Magic Hour's "claim 100 daily credits" button lives on their own logged-in
// dashboard - we can't click it or check whether it's already claimed from
// here (that would mean storing the user's Magic Hour login session on this
// server, which we don't do). This just opens magichour.ai and remembers,
// per device via localStorage, whether *this button* was clicked today, so
// it can show "충전완료" instead of nagging again - not a real confirmation
// that the claim succeeded on Magic Hour's side.
const STORAGE_KEY = "magicHourClaimedDate";

function todayString() {
  return new Date().toDateString();
}

export default function MagicHourClaimButton() {
  const [claimedToday, setClaimedToday] = useState(
    () => localStorage.getItem(STORAGE_KEY) === todayString()
  );

  function handleClick() {
    window.open("https://magichour.ai", "_blank", "noopener,noreferrer");
    localStorage.setItem(STORAGE_KEY, todayString());
    setClaimedToday(true);
  }

  return (
    <button
      type="button"
      className="button button-secondary"
      onClick={handleClick}
      disabled={claimedToday}
    >
      {claimedToday ? "오늘 충전완료" : "Claim 100 Daily Credits"}
    </button>
  );
}
