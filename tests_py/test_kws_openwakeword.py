import numpy as np

from jarvis.asr.kws_openwakeword import FRAME_LENGTH, KwsConfig, KwsOpenWakeWord


class _FakeModel:
    def __init__(self):
        self.last_frame = None

    def predict(self, frame):
        self.last_frame = frame
        return {"hey_jarvis": 0.91, "alexa": 0.1}


class _FakeModelEmpty:
    def predict(self, frame):
        return {}


def test_kws_config_from_env_defaults(monkeypatch):
    monkeypatch.delenv("WAKEWORD_MODELS", raising=False)
    monkeypatch.delenv("WAKEWORD_THRESHOLD", raising=False)

    cfg = KwsConfig.from_env()
    assert cfg.wakeword_models == ["hey_jarvis"]
    assert cfg.threshold == 0.5


def test_kws_config_from_env_parses_values(monkeypatch):
    monkeypatch.setenv("WAKEWORD_MODELS", "hey_jarvis, alexa")
    monkeypatch.setenv("WAKEWORD_THRESHOLD", "0.72")

    cfg = KwsConfig.from_env()
    assert cfg.wakeword_models == ["hey_jarvis", "alexa"]
    assert cfg.threshold == 0.72


def test_kws_config_from_env_clamps_threshold(monkeypatch):
    monkeypatch.setenv("WAKEWORD_MODELS", "hey_jarvis")
    monkeypatch.setenv("WAKEWORD_THRESHOLD", "5")

    cfg = KwsConfig.from_env()
    assert cfg.threshold == 1.0


def test_process_frame_detects_and_converts_float_input():
    detector = KwsOpenWakeWord(KwsConfig(wakeword_models=["hey_jarvis"], threshold=0.5))
    fake_model = _FakeModel()
    detector._model = fake_model

    frame = np.ones(FRAME_LENGTH, dtype=np.float32) * 0.2
    result = detector.process_frame(frame)

    assert result.detected is True
    assert result.keyword == "hey_jarvis"
    assert result.score == 0.91
    assert fake_model.last_frame.dtype == np.int16
    assert fake_model.last_frame.shape == (FRAME_LENGTH,)


def test_process_frame_handles_empty_predictions():
    detector = KwsOpenWakeWord(KwsConfig(wakeword_models=["hey_jarvis"], threshold=0.5))
    detector._model = _FakeModelEmpty()

    frame = np.zeros(FRAME_LENGTH, dtype=np.int16)
    result = detector.process_frame(frame)

    assert result.detected is False
    assert result.keyword == ""
    assert result.score == 0.0
