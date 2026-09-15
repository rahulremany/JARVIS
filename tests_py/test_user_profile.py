from pathlib import Path

from jarvis.session.user_profile import UserProfileStore


def test_profile_store_defaults_and_update(tmp_path: Path):
    store = UserProfileStore(tmp_path / ".state")

    initial = store.get()
    assert initial["preferred_tone"] == "direct"
    assert initial["goals"] == []

    updated = store.update(
        name="Rahul",
        preferred_tone="collaborative",
        coding_style_notes=["small diffs", "tests first"],
        goals=["ship camera mouse"],
        constraints=["prioritize_speed"],
    )

    assert updated["name"] == "Rahul"
    assert updated["preferred_tone"] == "collaborative"
    assert updated["coding_style_notes"] == ["small diffs", "tests first"]
    assert updated["goals"] == ["ship camera mouse"]
    assert updated["constraints"] == ["prioritize_speed"]

    reloaded = store.get()
    assert reloaded["name"] == "Rahul"
    assert reloaded["goals"] == ["ship camera mouse"]
