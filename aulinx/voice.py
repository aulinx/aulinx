"""Voice interface — speech-to-text for hands-free desktop control.

Supports:
- Push-to-talk mode (hold a key to speak)
- Continuous listening with silence detection
- Uses faster-whisper (local, no cloud) or whisper.cpp

Install: pip install faster-whisper sounddevice numpy
"""

import asyncio
import os
import tempfile
import wave

from rich.console import Console

console = Console()


class VoiceInput:
    """Speech-to-text input for the agent."""

    def __init__(self, model_size: str = "base", language: str = "en"):
        self.model_size = model_size
        self.language = language
        self._whisper = None
        self._available = False

    async def initialize(self):
        """Load the Whisper model."""
        try:
            from faster_whisper import WhisperModel
            self._whisper = WhisperModel(
                self.model_size,
                device="auto",
                compute_type="auto",
            )
            self._available = True
            console.print(f"[dim]  Voice: faster-whisper ({self.model_size}) loaded[/dim]")
        except ImportError:
            console.print("[dim]  Voice: not available (install faster-whisper sounddevice numpy)[/dim]")
        except Exception as e:
            console.print(f"[dim]  Voice: failed to load ({e})[/dim]")

    @property
    def available(self) -> bool:
        return self._available

    async def listen(self, duration: float = 5.0, sample_rate: int = 16000) -> str | None:
        """Record audio and transcribe it.

        Returns the transcribed text, or None if nothing was detected.
        """
        if not self._available:
            return None

        try:
            import numpy as np
            import sounddevice as sd

            console.print("[gold1]Listening...[/gold1]", end=" ")

            # Record audio
            audio = sd.rec(
                int(duration * sample_rate),
                samplerate=sample_rate,
                channels=1,
                dtype="float32",
            )
            sd.wait()

            # Check if there's actual audio (not just silence)
            if np.max(np.abs(audio)) < 0.01:
                console.print("[dim]silence[/dim]")
                return None

            # Save to temp WAV file (faster-whisper needs a file)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                temp_path = f.name
                wav_file = wave.open(f, "w")
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(sample_rate)
                wav_file.writeframes((audio * 32767).astype("int16").tobytes())
                wav_file.close()

            # Transcribe
            segments, info = self._whisper.transcribe(
                temp_path,
                language=self.language,
                beam_size=5,
            )
            text = " ".join(s.text for s in segments).strip()

            # Cleanup
            os.unlink(temp_path)

            if text:
                console.print(f'[green]"{text}"[/green]')
                return text
            else:
                console.print("[dim]nothing detected[/dim]")
                return None

        except ImportError:
            console.print("[red]sounddevice not installed[/red]")
            return None
        except Exception as e:
            console.print(f"[red]Voice error: {e}[/red]")
            return None

    async def listen_continuous(self, callback, silence_threshold: float = 0.01, silence_duration: float = 1.5):
        """Continuously listen and call callback(text) when speech is detected.

        Uses voice activity detection to know when to transcribe.
        """
        if not self._available:
            return

        try:
            import numpy as np
            import sounddevice as sd

            sample_rate = 16000
            chunk_duration = 0.5  # 500ms chunks
            chunk_size = int(sample_rate * chunk_duration)
            silence_chunks = int(silence_duration / chunk_duration)

            console.print("[gold1]Voice: Continuous listening active[/gold1]")

            buffer = []
            silent_count = 0
            recording = False

            def audio_callback(indata, frames, time_info, status):
                nonlocal buffer, silent_count, recording

                level = np.max(np.abs(indata))

                if level > silence_threshold:
                    buffer.append(indata.copy())
                    silent_count = 0
                    recording = True
                elif recording:
                    buffer.append(indata.copy())
                    silent_count += 1

                    if silent_count >= silence_chunks:
                        # Speech ended — transcribe
                        audio_data = np.concatenate(buffer)
                        buffer = []
                        silent_count = 0
                        recording = False
                        # Schedule transcription
                        asyncio.get_event_loop().call_soon_threadsafe(
                            lambda: asyncio.create_task(self._transcribe_and_callback(audio_data, sample_rate, callback))
                        )

            with sd.InputStream(
                samplerate=sample_rate,
                channels=1,
                dtype="float32",
                blocksize=chunk_size,
                callback=audio_callback,
            ):
                while True:
                    await asyncio.sleep(0.1)

        except ImportError:
            console.print("[red]sounddevice not installed for continuous listening[/red]")
        except Exception as e:
            console.print(f"[red]Voice continuous error: {e}[/red]")

    async def _transcribe_and_callback(self, audio, sample_rate: int, callback):
        """Transcribe audio buffer and call the callback."""
        import tempfile
        import wave

        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                temp_path = f.name
                wav_file = wave.open(f, "w")
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(sample_rate)
                wav_file.writeframes((audio * 32767).astype("int16").tobytes())
                wav_file.close()

            segments, _ = self._whisper.transcribe(temp_path, language=self.language, beam_size=5)
            text = " ".join(s.text for s in segments).strip()
            os.unlink(temp_path)

            if text and len(text) > 2:
                console.print(f'[green]Voice: "{text}"[/green]')
                await callback(text)
        except Exception as e:
            console.print(f"[dim]Transcription error: {e}[/dim]")
