from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


@dataclass
class UserProfile:
    name: str = ""
    preferred_tone: str = "direct"
    coding_style_notes: list[str] = field(default_factory=list)
    goals: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class UserProfileStore:
    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.profile_path = self.state_dir / "user_profile.json"

    def _load_raw(self) -> dict[str, Any]:
        if not self.profile_path.exists():
            return asdict(UserProfile())
        try:
            data = json.loads(self.profile_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return asdict(UserProfile())

        base = asdict(UserProfile())
        base.update({k: v for k, v in data.items() if k in base})
        return base

    def get(self) -> dict[str, Any]:
        return self._load_raw()

    def update(
        self,
        name: Optional[str] = None,
        preferred_tone: Optional[str] = None,
        coding_style_notes: Optional[list[str]] = None,
        goals: Optional[list[str]] = None,
        constraints: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        current = self._load_raw()

        if name is not None:
            current["name"] = name.strip()
        if preferred_tone is not None:
            current["preferred_tone"] = preferred_tone.strip() or "direct"
        if coding_style_notes is not None:
            current["coding_style_notes"] = [item.strip() for item in coding_style_notes if item.strip()]
        if goals is not None:
            current["goals"] = [item.strip() for item in goals if item.strip()]
        if constraints is not None:
            current["constraints"] = [item.strip() for item in constraints if item.strip()]

        current["updated_at"] = datetime.utcnow().isoformat()
        self.profile_path.write_text(json.dumps(current, indent=2), encoding="utf-8")
        return current
