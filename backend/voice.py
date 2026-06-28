import os
import wave
import json
import threading
from pathlib import Path

AUDIO_DIR = Path(os.getenv("AUDIO_DIR", "data/audio"))
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# ─── Text-to-Speech ───

async def speak(text: str, voice: str = "es-MX-DaliaNeural") -> bytes:
    try:
        import edge_tts
        communicate = edge_tts.Communicate(text, voice)
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
        return audio_data
    except ImportError:
        fallback_tts(text)
        return b""
    except Exception as e:
        fallback_tts(text)
        return b""

def fallback_tts(text: str):
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.say(text)
        engine.runAndWait()
    except ImportError:
        pass
    except:
        pass

# ─── Speech-to-Text ───

STT_ENGINE = None
STT_LOCK = threading.Lock()

def init_stt():
    global STT_ENGINE
    try:
        from vosk import Model, KaldiRecognizer
        model_path = os.getenv("VOSK_MODEL_PATH", "models/vosk-model-small-es-0.42")
        if Path(model_path).exists():
            STT_ENGINE = Model(model_path)
            return True
        return False
    except ImportError:
        return False
    except Exception:
        return False

def transcribe(audio_path: str) -> str:
    global STT_ENGINE
    if STT_ENGINE is None and not init_stt():
        return transcribe_google(audio_path)

    with STT_LOCK:
        try:
            from vosk import KaldiRecognizer
            wf = wave.open(audio_path, "rb")
            if wf.getnchannels() != 1 or wf.getsampwidth() != 2:
                wf.close()
                return transcribe_google(audio_path)

            rec = KaldiRecognizer(STT_ENGINE, wf.getframerate())
            rec.SetWords(True)
            while True:
                data = wf.readframes(4000)
                if not data:
                    break
                rec.AcceptWaveform(data)
            wf.close()

            result = json.loads(rec.FinalResult())
            return result.get("text", "")
        except Exception:
            return transcribe_google(audio_path)

def transcribe_google(audio_path: str) -> str:
    try:
        import speech_recognition as sr
        r = sr.Recognizer()
        with sr.AudioFile(audio_path) as source:
            audio = r.record(source)
        return r.recognize_google(audio, language="es-ES")
    except ImportError:
        return "[voz: speech_recognition no instalado]"
    except Exception as e:
        return f"[Error de transcripción: {e}]"

def record_from_mic(duration: int = 10, sample_rate: int = 16000) -> str:
    try:
        import pyaudio as pa

        p = pa.PyAudio()
        stream = p.open(format=pa.paInt16,
                        channels=1,
                        rate=sample_rate,
                        input=True,
                        frames_per_buffer=1024)

        frames = []
        for _ in range(0, int(sample_rate / 1024 * duration)):
            data = stream.read(1024, exception_on_overflow=False)
            frames.append(data)

        stream.stop_stream()
        stream.close()

        # ⚠️ GUARDAR sample_width ANTES de terminate()
        sample_width = p.get_sample_size(pa.paInt16)
        p.terminate()

        tmp = AUDIO_DIR / f"recording_{os.urandom(4).hex()}.wav"
        wf = wave.open(str(tmp), 'wb')
        wf.setnchannels(1)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(b''.join(frames))
        wf.close()

        text = transcribe(str(tmp))
        tmp.unlink(missing_ok=True)
        return text

    except ImportError:
        return "[voz: PyAudio no instalado]"
    except Exception as e:
        return f"[Error de grabación: {e}]"
