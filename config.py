import ctypes
import yaml
from pathlib import Path

_ai = yaml.safe_load((Path(__file__).parent / "ai_config.yaml").read_text(encoding="utf-8"))

OLLAMA_BASE_URL = _ai["ollama"]["base_url"]
OLLAMA_MODEL    = _ai["ollama"]["model"]
OLLAMA_TIMEOUT  = _ai["ollama"]["timeout"]

TEMPERATURE = _ai["generation"]["temperature"]
NUM_PREDICT = _ai["generation"]["num_predict"]
THINK       = _ai["generation"].get("think")

SYSTEM_PROMPT  = _ai["system_prompt"].strip()
EMOTION_COLORS  = _ai["emotions"]["colors"]
DEFAULT_EMOTION = _ai["emotions"]["default"]

STT_MODEL    = _ai["stt"]["model"]
STT_LANGUAGE = _ai["stt"]["language"]

WALK_SPEED_PX  = 2
WALK_TIMER_MS  = 16
PAUSE_MIN_MS   = 2000
PAUSE_MAX_MS   = 6000
WALK_MIN_MS    = 3000
WALK_MAX_MS    = 10000

_screen_h = ctypes.windll.user32.GetSystemMetrics(1)

CHAR_SIZE      = int(_screen_h // 2 * 1.5)
WINDOW_MARGIN  = 4

CHAT_WIDTH     = max(300, CHAR_SIZE * 2)
CHAT_HEIGHT    = 160
CHAT_OFFSET_Y  = -(CHAR_SIZE + 20)

MIC_SAMPLE_RATE   = 16000
MIC_CHANNELS      = 1
VAD_ENERGY_THRESH = 0.015
VAD_SPEECH_FRAMES = 4
VAD_SILENCE_MS    = 600
