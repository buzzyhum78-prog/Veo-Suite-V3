"""
VEO SUITE V3.3 — Audio Service (Multi-Engine TTS)
====================================================
Hỗ trợ 5 engine:
  1. Edge TTS (Free, có subtitle) — mặc định
  2. OpenAI TTS (Trả phí, chất lượng cao)
  3. Google Cloud TTS (WaveNet, trả phí)
  4. Kokoro TTS (Local, đang phát triển)
  5. LuxTTS (Voice Cloning, 150x realtime, 48kHz) — NEW

Tính năng:
  - VPN auto-retry khi Edge TTS bị chặn IP
  - AI Director chọn giọng theo topic/quốc gia
  - Text pre-processing cho giọng đọc tự nhiên
  - Voice cloning với 3 giây audio mẫu (LuxTTS)
"""

import asyncio
import json
import logging
import os
import re

import edge_tts

from services.config_manager import VOICE_CONFIG_FILE
from services.voice_constants import get_smart_voice_config
from services.vpn_manager import VPNManager

logger = logging.getLogger("VeoSuite.Audio")


class AudioService:
    """Multi-engine TTS service with VPN fallback."""

    def __init__(self):
        self.config = self._load_voice_config()

    def _load_voice_config(self) -> dict:
        """Load voice engine config từ file do Admin Tab tạo."""
        if VOICE_CONFIG_FILE.exists():
            try:
                with open(VOICE_CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                logger.warning("Voice config corrupted, using defaults")
        return {}

    # =========================================================================
    # PUBLIC: Tạo audio (entry point duy nhất)
    # =========================================================================

    def create_audio(self, text: str, output_path: str, meta_data: dict = None):
        """
        Tạo audio file. Returns (success: bool, message: str).

        Args:
            text: Nội dung cần đọc
            output_path: Đường dẫn file MP3 đầu ra
            meta_data: Dict chứa thông tin voice (country, topic, voice_id, rate, pitch...)
        """
        if not meta_data:
            meta_data = {}

        # Xác định engine
        engine = self._select_engine(meta_data)
        logger.info(f"TTS engine: {engine.upper()}")

        if engine == "openai":
            return self._create_openai_audio(text, output_path, meta_data)
        elif engine == "google":
            return self._create_google_audio(text, output_path, meta_data)
        elif engine == "kokoro":
            return self._create_kokoro_audio(text, output_path, meta_data)
        elif engine == "luxtts":
            return self._create_luxtts_audio(text, output_path, meta_data)
        else:
            return self._create_edge_audio(text, output_path, meta_data)

    def _select_engine(self, meta_data: dict) -> str:
        """Chọn engine theo thứ tự ưu tiên: override > config > edge."""
        if meta_data.get("provider_override"):
            return meta_data["provider_override"]
        if self.config.get("openai_enable"):
            return "openai"
        if self.config.get("google_enable"):
            return "google"
        return "edge"

    # =========================================================================
    # ENGINE 1: Edge TTS (Free + Subtitle + VPN Retry)
    # =========================================================================

    def _create_edge_audio(self, text: str, output_path: str, meta_data: dict):
        """Edge TTS với VPN auto-retry."""
        country = meta_data.get("country") or meta_data.get("p_country", "US")
        topic = meta_data.get("topic", "General")
        ai_config = get_smart_voice_config(country, topic)

        # Voice
        voice = (meta_data.get("voice_id")
                 or meta_data.get("voice_id_override")
                 or ai_config.get("voice_id", "vi-VN-HoaiMyNeural"))

        # Rate & Pitch
        raw_rate = meta_data.get("rate") or ai_config.get("rate", "+0%")
        raw_pitch = meta_data.get("pitch") or ai_config.get("pitch", "+0Hz")
        final_rate = self._enforce_sign(raw_rate, "%")
        final_pitch = self._enforce_sign(raw_pitch, "Hz")

        # Pre-process text
        processed_text = self._process_text(text)

        # Retry with VPN
        vpn = VPNManager()
        max_retries = 2

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"Edge TTS (attempt {attempt}): {voice} | rate={final_rate} pitch={final_pitch}")
                asyncio.run(self._edge_generate(processed_text, voice, output_path, final_rate, final_pitch))

                if os.path.exists(output_path) and os.path.getsize(output_path) > 1024:
                    srt_path = output_path.replace(".mp3", ".srt")
                    has_sub = os.path.exists(srt_path)
                    return True, f"Edge OK: {voice} | Sub: {'OK' if has_sub else 'N/A'}"
                else:
                    raise RuntimeError("Output file empty or blocked")

            except Exception as e:
                logger.warning(f"Edge TTS error (attempt {attempt}): {e}")
                if attempt < max_retries:
                    logger.info("Activating VPN for IP rotation...")
                    vpn.rotate_ip()
                else:
                    return False, f"Edge TTS failed: {e}"

        return False, "Edge TTS failed after all retries"

    async def _edge_generate(self, text: str, voice: str, output_path: str, rate: str, pitch: str):
        """Async Edge TTS generation với subtitle extraction."""
        communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
        base_path = os.path.splitext(output_path)[0]
        sub_path = f"{base_path}.srt"
        subs_data = []

        with open(output_path, "wb") as audio_file:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_file.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    subs_data.append(chunk)

        # Generate subtitle
        try:
            if subs_data:
                sub_maker = edge_tts.SubMaker()
                for s in subs_data:
                    sub_maker.feed(s)

                content = (sub_maker.generate_srt()
                           if hasattr(sub_maker, 'generate_srt')
                           else sub_maker.generate_subs())

                with open(sub_path, "w", encoding="utf-8") as f:
                    f.write(content)
            else:
                self._create_dummy_srt(output_path)
        except Exception as e:
            logger.warning(f"Subtitle generation failed: {e}")
            self._create_dummy_srt(output_path)

    # =========================================================================
    # ENGINE 2: OpenAI TTS
    # =========================================================================

    def _create_openai_audio(self, text: str, output_path: str, meta_data: dict):
        """OpenAI TTS (trả phí, chất lượng cao)."""
        api_key = self.config.get("openai_key")
        if not api_key:
            return False, "Chưa nhập OpenAI TTS Key!"

        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)

            # Map voice
            req_voice = meta_data.get("voice_id", "")
            if "Nam" in req_voice:
                final_voice = "onyx"
            elif "Nu" in req_voice:
                final_voice = "nova"
            else:
                final_voice = "alloy"

            model = self.config.get("openai_model", "tts-1")
            logger.info(f"OpenAI TTS: {model} / {final_voice}")

            response = client.audio.speech.create(
                model=model, voice=final_voice, input=text
            )
            response.stream_to_file(output_path)
            self._create_dummy_srt(output_path)
            return True, f"OpenAI OK: {final_voice}"

        except Exception as e:
            return False, f"OpenAI TTS error: {e}"

    # =========================================================================
    # ENGINE 3: Google Cloud TTS
    # =========================================================================

    def _create_google_audio(self, text: str, output_path: str, meta_data: dict):
        """Google Cloud TTS (WaveNet)."""
        json_path = self.config.get("google_json_path")
        if not json_path or not os.path.exists(json_path):
            return False, "Chưa cấu hình Google Cloud JSON!"

        try:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = json_path
            from google.cloud import texttospeech

            client = texttospeech.TextToSpeechClient()
            synthesis_input = texttospeech.SynthesisInput(text=text)
            voice_params = texttospeech.VoiceSelectionParams(
                language_code="vi-VN",
                name="vi-VN-Wavenet-C",
                ssml_gender=texttospeech.SsmlVoiceGender.MALE
            )
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3
            )

            logger.info("Google Cloud TTS rendering...")
            response = client.synthesize_speech(
                input=synthesis_input, voice=voice_params, audio_config=audio_config
            )
            with open(output_path, "wb") as out:
                out.write(response.audio_content)

            self._create_dummy_srt(output_path)
            return True, "Google TTS OK"

        except Exception as e:
            return False, f"Google TTS error: {e}"

    # =========================================================================
    # ENGINE 4: Kokoro TTS (Local Pro)
    # =========================================================================

    def _create_kokoro_audio(self, text: str, output_path: str, meta_data: dict):
        """Kokoro TTS (Local, high quality). Yêu cầu: pip install kokoro"""
        try:
            from kokoro import KModel
            import soundfile as sf
            
            # Khởi tạo model (nên dùng singleton hoặc cache trong thực tế)
            # Tạm thời giả định model đã có sẵn trong VEO_DB/models/kokoro
            model_path = self.config.get("kokoro_model_path", "VEO_DB/models/kokoro/kokoro-v0_19.pth")
            
            if not os.path.exists(model_path):
                return False, f"Không tìm thấy model Kokoro tại: {model_path}"
                
            self.progress_signal.emit("🎙️ Kokoro AI đang đọc (Local)...")
            
            # Logic gọi Kokoro (đơn giản hóa)
            # model = KModel(model_path)
            # voice = meta_data.get("voice_id", "af_heart")
            # audio, srt = model.create(text, voice=voice)
            
            # Placeholder: Trong thực tế sẽ gọi subprocess hoặc thư viện python
            return False, "Kokoro integration in progress (Dependency check required)."
            
        except ImportError:
            return False, "Thiếu thư viện 'kokoro'. Vui lòng cài đặt để dùng TTS Local Pro."
        except Exception as e:
            return False, f"Kokoro TTS error: {e}"

    # =========================================================================
    # ENGINE 5: LuxTTS (Voice Cloning — 150x Realtime)
    # =========================================================================
    # Repo: https://github.com/ysharma3501/LuxTTS
    # API: LuxTTS('YatharthS/LuxTTS', device) → encode_prompt(audio) → generate_speech(text, prompt)
    # Output: WAV 48kHz → Convert to MP3
    # =========================================================================

    _luxtts_model = None  # Singleton cache
    _luxtts_prompt_cache = {}  # Cache encoded prompts by file path

    def _create_luxtts_audio(self, text: str, output_path: str, meta_data: dict):
        """LuxTTS Voice Cloning (Local, 48kHz, 150x realtime).
        
        Requires: pip install git+https://github.com/ysharma3501/LuxTTS.git
        meta_data keys:
            - reference_audio: Path to reference voice file (3-10s WAV/MP3)
            - luxtts_steps: Number of inference steps (default: 4)
            - luxtts_speed: Speed factor (default: 1.0)
            - luxtts_t_shift: Sampling parameter (default: 0.9)
            - luxtts_rms: Volume normalization (default: 0.01)
        """
        try:
            import soundfile as sf
            from zipvoice.luxvoice import LuxTTS as LuxTTSModel
        except ImportError:
            return False, (
                "Thiếu thư viện LuxTTS. Cài đặt:\n"
                "pip install git+https://github.com/ysharma3501/LuxTTS.git"
            )

        # 1. Reference audio (bắt buộc cho voice cloning)
        ref_audio = meta_data.get("reference_audio", "")
        if not ref_audio or not os.path.exists(ref_audio):
            return False, (
                "Cần file audio mẫu (3-10 giây) để clone giọng.\n"
                "Đặt đường dẫn vào meta_data['reference_audio']"
            )

        try:
            # 2. Load model (Singleton — chỉ load 1 lần)
            if AudioService._luxtts_model is None:
                logger.info("🔄 Loading LuxTTS model (first time, may take ~30s)...")
                import torch
                device = "cuda" if torch.cuda.is_available() else "cpu"
                AudioService._luxtts_model = LuxTTSModel('YatharthS/LuxTTS', device=device)
                logger.info(f"✅ LuxTTS loaded on {device.upper()}")

            model = AudioService._luxtts_model

            # 3. Encode reference audio (cache by file path)
            rms = float(meta_data.get("luxtts_rms", 0.01))
            ref_duration = int(meta_data.get("luxtts_ref_duration", 5))
            
            cache_key = f"{ref_audio}_{rms}_{ref_duration}"
            if cache_key not in AudioService._luxtts_prompt_cache:
                logger.info(f"🎤 Encoding reference: {os.path.basename(ref_audio)}")
                encoded = model.encode_prompt(ref_audio, duration=ref_duration, rms=rms)
                AudioService._luxtts_prompt_cache[cache_key] = encoded
            else:
                logger.info("🎤 Using cached voice prompt")
            
            encoded_prompt = AudioService._luxtts_prompt_cache[cache_key]

            # 4. Generate speech
            num_steps = int(meta_data.get("luxtts_steps", 4))
            t_shift = float(meta_data.get("luxtts_t_shift", 0.9))
            speed = float(meta_data.get("luxtts_speed", 1.0))
            return_smooth = bool(meta_data.get("luxtts_smooth", False))

            logger.info(f"🎙️ LuxTTS generating (steps={num_steps}, speed={speed})...")
            
            # Pre-process text
            processed_text = self._process_text(text)
            
            final_wav = model.generate_speech(
                processed_text, encoded_prompt,
                num_steps=num_steps, t_shift=t_shift,
                speed=speed, return_smooth=return_smooth
            )

            # 5. Save WAV (48kHz)
            wav_data = final_wav.numpy().squeeze()
            wav_path = output_path.replace(".mp3", "_48k.wav")
            sf.write(wav_path, wav_data, 48000)

            # 6. Convert WAV → MP3 (via pydub or ffmpeg)
            self._convert_wav_to_mp3(wav_path, output_path)
            
            # Cleanup temp WAV
            try:
                os.remove(wav_path)
            except Exception:
                pass

            # 7. Create dummy SRT (LuxTTS doesn't produce subtitles)
            self._create_dummy_srt(output_path)

            if os.path.exists(output_path) and os.path.getsize(output_path) > 1024:
                return True, f"LuxTTS OK: Voice cloned from {os.path.basename(ref_audio)} (48kHz)"
            else:
                return False, "LuxTTS: Output file empty"

        except Exception as e:
            logger.error(f"LuxTTS error: {e}", exc_info=True)
            return False, f"LuxTTS error: {e}"

    @staticmethod
    def _convert_wav_to_mp3(wav_path: str, mp3_path: str):
        """Convert WAV to MP3 using pydub (preferred) or FFmpeg fallback."""
        try:
            from pydub import AudioSegment
            audio = AudioSegment.from_wav(wav_path)
            audio.export(mp3_path, format="mp3", bitrate="192k")
            return
        except ImportError:
            pass
        
        # Fallback: FFmpeg direct
        import subprocess
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", wav_path, "-b:a", "192k", mp3_path],
                capture_output=True, timeout=60
            )
        except Exception as e:
            logger.warning(f"WAV→MP3 conversion failed: {e}")
            # Last resort: just copy WAV as output
            import shutil
            shutil.copy(wav_path, mp3_path)

    # =========================================================================
    # HELPERS
    # =========================================================================

    @staticmethod
    def _enforce_sign(value, unit: str) -> str:
        """Chuẩn hoá rate/pitch: '+10%', '-5Hz'."""
        try:
            val_str = str(value).replace(unit, "").replace("+", "").strip()
            if not val_str:
                return f"+0{unit}"
            num = int(float(val_str))
            return f"{num:+d}{unit}"
        except (ValueError, TypeError):
            return f"+0{unit}"

    @staticmethod
    def _process_text(text: str) -> str:
        """Làm sạch text cho TTS tự nhiên."""
        if not text:
            return "Audio test content."

        clean = text.replace('"', '').replace("'", "")
        clean = clean.replace("[ngắt]", ". . . ")
        clean = re.sub(r'\[.*?\]', '', clean)
        clean = re.sub(r'\(.*?\)', '', clean)

        # Kiểm tra còn nội dung thực không
        check = re.sub(r'[^\w]', '', clean)
        if len(check) < 2:
            logger.warning("Text too short after cleanup, using original")
            return text

        return clean

    @staticmethod
    def _create_dummy_srt(audio_path: str):
        """Tạo SRT placeholder khi engine không hỗ trợ subtitle."""
        srt = audio_path.replace(".mp3", ".srt")
        with open(srt, "w", encoding="utf-8") as f:
            f.write("1\n00:00:00,000 --> 00:00:05,000\n(Subtitle not available)\n\n")

    @staticmethod
    def _manual_generate_srt(events: list) -> str:
        """Tạo SRT thủ công từ WordBoundary events."""
        srt_out = ""
        for i, event in enumerate(events):
            start = event['offset'] / 10000000
            duration = event['duration'] / 10000000
            end = start + duration
            text = event['text']

            def fmt(s):
                h = int(s // 3600)
                m = int((s % 3600) // 60)
                sec = int(s % 60)
                ms = int((s - int(s)) * 1000)
                return f"{h:02}:{m:02}:{sec:02},{ms:03}"

            srt_out += f"{i + 1}\n{fmt(start)} --> {fmt(end)}\n{text}\n\n"
        return srt_out