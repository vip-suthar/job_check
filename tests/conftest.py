import pytest

from detector import model


@pytest.fixture(autouse=True)
def no_trained_model(monkeypatch):
    """Results must not depend on whether instance/model.joblib has been trained locally."""
    monkeypatch.setattr(model, "load", lambda: None)
