from controller.selector import ServerSelector


def test_s4_controller_mode_can_be_selected_from_environment(monkeypatch):
    monkeypatch.setenv("CDN_MODE", "static")
    assert ServerSelector().cdn_mode == "static"


def test_s4_invalid_controller_mode_falls_back_to_dynamic(monkeypatch):
    monkeypatch.setenv("CDN_MODE", "typo")
    assert ServerSelector().cdn_mode == "dynamic"
