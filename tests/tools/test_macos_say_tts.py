from types import SimpleNamespace
from unittest.mock import patch
import wave

from tools.audio.macos_say_tts import MacOSSayTTS
from tools.base_tool import ToolStatus


def test_say_is_unavailable_off_macos():
    with patch('tools.audio.macos_say_tts.platform.system', return_value='Linux'):
        assert MacOSSayTTS().get_status() == ToolStatus.UNAVAILABLE


def test_say_does_not_fall_back_to_wrong_locale(tmp_path):
    with patch.object(MacOSSayTTS, 'get_status', return_value=ToolStatus.AVAILABLE), \
         patch('tools.audio.macos_say_tts.subprocess.run', return_value=SimpleNamespace(stdout='Alex en_US # Hello')) as run:
        result = MacOSSayTTS().execute({'text':'Xin chào', 'voice':'Linh', 'language_code':'vi_VN',
                                      'output_path':str(tmp_path / 'voice.wav')})
    assert not result.success
    assert 'no voice fallback' in result.error
    assert run.call_count == 1


def test_say_checks_samples_and_supports_installed_decorated_name(tmp_path):
    for frames in (0, 2400):
        output = tmp_path / 'voice.wav'
        def run(args, **kwargs):
            if args == ['say', '-v', '?']:
                return SimpleNamespace(stdout='Linh (Vietnamese (Vietnam)) vi_VN # Xin chào')
            if args[0] == 'say':
                assert args[2] == 'Linh (Vietnamese (Vietnam))'
                assert kwargs['input'] == 'Xin chào'
            else:
                with wave.open(str(output), 'wb') as audio:
                    audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(24000)
                    audio.writeframes(b'\0\0' * frames)
            return SimpleNamespace(stdout='')
        with patch.object(MacOSSayTTS, 'get_status', return_value=ToolStatus.AVAILABLE), \
             patch('tools.audio.macos_say_tts.subprocess.run', side_effect=run):
            result = MacOSSayTTS().execute({'text':'Xin chào','voice':'Linh','language_code':'vi_VN',
                                          'output_path':str(output)})
        assert result.success == bool(frames)
        if not frames: assert 'zero audio samples' in result.error
