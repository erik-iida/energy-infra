"""Daily API call counter kept in state/budget.json, so repeated or duplicate runs can't blow the quota."""
import json
from datetime import datetime, timezone

from . import config


class BudgetExceeded(RuntimeError):
    pass


class Budget:
    def __init__(self, name: str, cap: int = config.DAILY_CALL_CAP):
        self.path = config.STATE_DIR / f"budget_{name}.json"
        self.cap = cap
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        data = json.loads(self.path.read_text()) if self.path.exists() else {}
        self.calls = data.get("calls", 0) if data.get("date") == today else 0
        self.today = today

    def take(self, n: int = 1) -> None:
        if self.calls + n > self.cap:
            raise BudgetExceeded(f"daily cap of {self.cap} calls reached ({self.calls} used today)")
        self.calls += n
        self.save()

    @property
    def left(self) -> int:
        return self.cap - self.calls

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"date": self.today, "calls": self.calls, "cap": self.cap}))
