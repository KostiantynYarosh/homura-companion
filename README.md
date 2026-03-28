<img width="3561" height="1286" alt="Image" src="https://github.com/user-attachments/assets/0d0ed116-a478-4397-9e7e-d499d2669ab5" />

## Homura - AI Desktop Companion

A living desktop companion powered by a local LLM. She sits on your screen, listens to your voice, reacts with emotions, and remembers things about you.

## Features

- **Voice activation** - wake word "Homura" with fuzzy matching (works even with mispronunciations)
- **Streaming AI responses** - powered by Ollama running locally, no cloud required
- **Emotion system** - character reacts with animated expressions (happy, sad, blushed, angry, surprised, shy, thinking)
- **System audio listening** - she can listen to what's playing on your PC (music, Discord calls, etc.) and comment on it
- **Persistent memory** - remembers facts about you across sessions (up to 50 facts)
- **Rich idle animations** - breathing, ear twitches, foot stomps, yawning, tippy-toes, side-eye and much more
- **Hoodie system** - ask her to put on or take off her hoodie
- **System tray** - always-on-top toggle, hide/show, quit

## Demo
<img src="https://github.com/user-attachments/assets/7281f8a6-2f29-45ae-9959-c09dd7b5a88a" width="550"/>


## Requirements

- Windows 10/11 (WASAPI loopback required for system audio)
- [Ollama](https://ollama.com) running locally
- Python 3.11+
- NVIDIA GPU recommended (8GB+ VRAM), CPU works too

## Installation

```bash
git clone https://github.com/yourname/homura
cd homura
pip install -r requirements.txt
```

Pull a model in Ollama:
```bash
ollama pull qwen2.5:14b       # recommended (fits in 16GB VRAM)
# or
ollama pull mistral-nemo:12b  # good alternative
# or
ollama pull qwen2.5:7b        # faster, less VRAM
#or any other model you want
```

## Running

```bash
python main.py
```

On first launch, Faster-Whisper will download the `medium` STT model (~1.5GB). Subsequent launches are instant.

## Configuration

Edit `ai_config.yaml`:

```yaml
ollama:
  model: "qwen2.5:14b"   # change to any Ollama model

generation:
  temperature: 0.75  # creativity: 0.0 = deterministic, 1.0 = very random
  num_predict: 250   # max tokens per response, lower = faster

system_prompt: |   # edit freely to change her name, language, tone, and behavior
  You are Homura - a desktop companion with personality.

stt:
  model: "medium"        # tiny / base / small / medium / large
  language: "ru"         # ru, en, or null for auto-detect
  wake_words:            # exact substrings matched against STT output
    - "homura"
    - "homurа"
  wake_fuzzy:            # used for fuzzy matching (catches mispronunciations)
    - "homura"
  wake_fuzzy_ratio: 0.65 # similarity threshold 0.0–1.0
```

To rename the companion and change the wake word, just update `wake_words` and `wake_fuzzy` with the new name and its likely mispronunciations, then update the `system_prompt` with the new name.

## Language

By default Homura is configured for **Russian** - STT, wake words, and the AI system prompt are all set to Russian. Everything can be changed in `ai_config.yaml`:

```yaml
stt:
  language: "ru"         # STT language: "en", "de", "ja", "zh", etc. or null for auto-detect

  wake_words:            # change name to your language
    - "homura"
    - "homurа"          
  wake_fuzzy:            
    - "homura"

system_prompt: | # rewrite system prompt to your language
  ALWAYS respond in the same language as the user. 
  # adjust the rest of the prompt to fit your language and character
```

The underlying LLM (Ollama) supports whatever languages your chosen model knows. Models like `qwen2.5` or `mistral-nemo` handle English, Russian, Chinese, German, French, Japanese and many more out of the box.

**PC Audio mode:**
1. Say "Homura, listen to the music"
2. She starts capturing system audio (up to 15 sec)
3. Transcription is sent to the AI as `[PC_AUDIO] <text>` - clearly labeled so she knows it's not your speech
4. Say "Homura stop" to end early

## Animations

All sprites are in [Aseprite](https://www.aseprite.org/) `.ase` format. The app parses them natively, no export needed.

| Animation | Trigger |
|-----------|---------|
| Breathing | Default idle |
| Side-eye glance | Random, 45-90 sec |
| Foot stomp (L/R) | Random, 20-65 sec |
| Tippy-toes | Random, 30-75 sec |
| Ear twitch (L/R) | Random, 25-70 sec |
| Yawn | Random, 3-4 min |
| Talking | While AI is streaming response |
| Emotions | After AI response completes |
| Hoodie | Voice command or AI tag |

## Tech Stack

- **UI**: PyQt6
- **STT**: [Faster-Whisper](https://github.com/SYSTRAN/faster-whisper)
- **LLM**: [Ollama](https://ollama.com) (local, any model)
- **System audio**: PyAudioWPatch (WASAPI loopback)
- **Sprite format**: Aseprite `.ase` (custom parser)

