"""Contract tests for the zero-cost Windows SAPI narration provider."""

from pathlib import Path
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.audio.windows_sapi_tts import WindowsSapiTTS
from tools.base_tool import BaseTool, ToolRuntime, ToolStatus, ToolTier


def test_contract_is_local_zero_cost_voice_tool() -> None:
    tool = WindowsSapiTTS()

    assert issubclass(WindowsSapiTTS, BaseTool)
    assert tool.name == "windows_sapi_tts"
    assert tool.provider == "windows_sapi"
    assert tool.runtime == ToolRuntime.LOCAL
    assert tool.tier == ToolTier.VOICE
    assert tool.estimate_cost({"text": "Narration"}) == 0.0
    assert tool.input_schema["properties"]["rate"]["minimum"] == -10


def test_empty_text_fails_before_starting_synthesis() -> None:
    result = WindowsSapiTTS().execute({"text": "   "})

    assert not result.success
    assert "Text is required" in result.error


def test_status_is_a_supported_tool_status() -> None:
    assert WindowsSapiTTS().get_status() in {ToolStatus.AVAILABLE, ToolStatus.UNAVAILABLE}
