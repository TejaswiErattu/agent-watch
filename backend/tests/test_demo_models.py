import importlib.util
from pathlib import Path

from agentwatch_api.pricing import pricing_table

MODELS_PATH = Path(__file__).resolve().parents[2] / "demo" / "models.py"


def _load_models():
    spec = importlib.util.spec_from_file_location("demo_models", MODELS_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_bedrock_model_is_us_inference_profile():
    assert _load_models().BEDROCK_MODEL_ID.startswith("us.anthropic.")


def test_demo_models_are_priced():
    m = _load_models()
    models = pricing_table()["models"]
    assert m.BEDROCK_MODEL_ID in models
    assert m.ANTHROPIC_MODEL_ID in models
