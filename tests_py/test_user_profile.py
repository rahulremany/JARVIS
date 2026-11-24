from pathlib import Path

from jarvis.session.user_profile import UserProfileStore


def test_profile_store_defaults_and_update(tmp_path: Path):
    store = UserProfileStore(tmp_path / ".state")

    initial = store.get()
    assert initial["preferred_tone"] == "direct"
    assert initial["goals"] == []

    updated = store.update(
        name="Ada",
        preferred_tone="collaborative",
        coding_style_notes=["small diffs", "tests first"],
        goals=["ship weather station"],
        constraints=["prioritize_speed"],
    )

    assert updated["name"] == "Ada"
    assert updated["preferred_tone"] == "collaborative"
    assert updated["coding_style_notes"] == ["small diffs", "tests first"]
    assert updated["goals"] == ["ship weather station"]
    assert updated["constraints"] == ["prioritize_speed"]

    reloaded = store.get()
    assert reloaded["name"] == "Ada"
    assert reloaded["goals"] == ["ship weather station"]
