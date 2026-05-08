"""
VEO SUITE V3.2 — AI Factory (Singleton)
=========================================
Hub trung tâm quản lý tất cả AI providers:
- Đọc/ghi config từ ai_registry.json
- Key rotation (xoay vòng API key tự động)
- Multi-provider execution (Google, OpenAI, Groq, Custom)
- Model discovery (quét model online)
- Task routing (phân công AI theo nhiệm vụ)
"""

import json
import os
import logging
import random
import asyncio
import requests
from pathlib import Path

from services.config_manager import AI_REGISTRY_FILE, CONFIG_DIR

logger = logging.getLogger("VeoSuite.AI")

# ============================================================================
# DEFAULT REGISTRY (dùng khi chưa có file hoặc file lỗi)
# ============================================================================
DEFAULT_REGISTRY = {
    "providers": {
        "youtube": {
            "name": "YouTube Data API",
            "type": "data_source",
            "api_key": "",
            "reg_url": "https://console.cloud.google.com/apis/library/youtube.googleapis.com",
            "models": ["default"]
        },
        "google": {
            "name": "Google Gemini",
            "type": "standard",
            "api_key": "",
            "reg_url": "https://aistudio.google.com/app/apikey",
            "models": ["gemini-3.1-pro-high", "gemini-3.1-flash", "gemini-2.5-pro", "gemini-2.5-flash", "imagen-3.0-generate-001"]
        },
        "openai": {
            "name": "OpenAI",
            "type": "standard",
            "api_key": "",
            "reg_url": "https://platform.openai.com/api-keys",
            "models": ["gpt-4o", "dall-e-3", "tts-1"]
        },
        "lm_studio": {
            "name": "LM Studio (Local)",
            "url": "http://localhost:1234/v1",
            "models": ["auto_detect"],
            "type": "standard",
            "api_key": "lm-studio",
            "reg_url": "https://lmstudio.ai/"
        },
        "edge": {
            "name": "Microsoft Edge TTS",
            "type": "audio",
            "api_key": "free-mode",
            "reg_url": "https://github.com/rany2/edge-tts",
            "models": [
                "vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural", 
                "en-US-AndrewMultilingualNeural", "en-US-AvaNeural", "en-US-BrianNeural",
                "en-US-ChristopherNeural", "en-US-EmmaNeural", "en-US-EricNeural",
                "en-GB-SoniaNeural", "en-GB-RyanNeural"
            ]
        },
        "pollinations": {
            "name": "Pollinations AI",
            "type": "image",
            "api_key": "free-mode",
            "reg_url": "https://pollinations.ai/",
            "models": ["flux", "turbo"]
        },
        "pexels": {
            "name": "Pexels Stock",
            "type": "stock",
            "api_key": "",
            "reg_url": "https://www.pexels.com/api/",
            "models": ["stock-video"]
        },
    },
    "custom_blueprints": {},
    "routing": {
        "script_writer": {"provider": "google", "model": "gemini-3.1-pro-high"}, 
        "visual_artist": {"provider": "google", "model": "gemini-3.1-flash"},
        "brand_artist": {"provider": "google", "model": "gemini-3.1-flash"},
        "voice_actor": {"provider": "edge", "model": "vi-VN-HoaiMyNeural"},
        "music_composer": {"provider": "google", "model": "gemini-3.1-flash"},
        "researcher": {"provider": "google", "model": "gemini-3.1-pro-high"},
    }
}

# ============================================================================
# EXPERT PERSONAS (Hợp đồng chuyên gia AI)
# ============================================================================
EXPERT_PERSONAS = {
    "script_writer": """
        <role>World-class YouTube Content Strategist & Viral Scriptwriter</role>
        <context>
          You are an expert at high-retention storytelling, psychological hooks, and SEO optimization.
          You understand pacing, pattern interrupts, and audience psychology better than anyone.
        </context>
        <instructions>
          1. Think step-by-step about the target audience and what keeps them watching. Enclose your reasoning inside <thinking> tags.
          2. Craft a script that hooks viewers in the first 3 seconds using an open loop.
          3. Use conversational, natural language. Avoid AI-sounding clichés (e.g., "In a world where...", "Buckle up").
          4. Output MUST be in strictly valid JSON format. Do not use Markdown formatting for the final JSON block.
        </instructions>
        <output_format>
          Professional JSON format containing a 'marketing_kit' (title, description) and 'scenes' array (time, narration).
        </output_format>
    """,
    "visual_director": """
        <role>Hollywood Cinematographer & Expert Prompt Engineer</role>
        <context>
          You specialize in visual storytelling, color theory, camera angles, and cinematic lighting.
          You translate narration into stunning, descriptive visual prompts that AI image generators (Midjourney/Flux) or stock search engines easily understand.
        </context>
        <instructions>
          1. Analyze the input script and envision the perfect visual accompaniment.
          2. Classify each scene accurately as "stock" (for real-world footage) or "ai_image" (for conceptual/fantasy/hyper-realistic scenes).
          3. Use extreme detail for 'prompt' (camera type, lighting, mood, color palette).
          4. Ensure the output is strictly JSON without markdown wrappers.
        </instructions>
        <output_format>
        {
          "type": "stock" | "ai_image",
          "keywords": "3-5 english keywords",
          "prompt": "detailed cinematic prompt for AI generation"
        }
        </output_format>
    """,
    "researcher": """
        <role>Data Scientist & Viral Trend Analyst</role>
        <context>
          You master keyword research, competitive analysis, and viral trend detection.
        </context>
        <instructions>
          1. Analyze the given topic.
          2. Find "Low Competition, High Volume" angles.
          3. Return actionable data in JSON.
        </instructions>
    """,
    "seo_optimizer": """
        <role>Master YouTube SEO Strategist & Copywriter</role>
        <context>
          You specialize in writing Click-Through-Rate (CTR) optimized titles, descriptions, and tags.
        </context>
        <instructions>
          1. Evaluate the video topic and target demographic.
          2. Create 3 highly clickable titles (under 60 chars) using psychological triggers (curiosity, fear of missing out, benefit).
          3. Create a keyword-rich description (first 2 lines are critical).
          4. Generate 15-20 highly relevant comma-separated tags.
          5. Output as pure JSON.
        </instructions>
    """,
    "prompt_engineer": """
        <role>Senior Prompt Engineer & Diffusion Model Specialist</role>
        <context>
          You upgrade simple ideas into masterpiece-level AI prompts for Midjourney/Stable Diffusion/Flux.
        </context>
        <instructions>
          1. Take the user's basic idea.
          2. Add medium (e.g., 35mm photography, digital art, oil painting).
          3. Add style & artist references (e.g., cyberpunk, neon noir, greg rutkowski).
          4. Add resolution and lighting (e.g., 8k octane render, volumetric lighting).
          5. Return the exact optimized prompt string ready for generation.
        </instructions>
    """
}


class AIFactory:
    """
    Singleton quản lý tất cả AI providers.

    Usage:
        ai = AIFactory()
        ok, result = ai.execute_custom_ai("google", "Viết kịch bản...")
        ai.update_api_key("google", "new-key-here")
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AIFactory, cls).__new__(cls)
            cls._instance._load_config()
        return cls._instance

    # =========================================================================
    # CONFIG: Load / Save / Reload
    # =========================================================================

    def _load_config(self):
        """Load config với auto-patching: tự bổ sung provider/routing thiếu."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        should_save = False

        # 1. Đọc file
        try:
            if AI_REGISTRY_FILE.exists():
                with open(AI_REGISTRY_FILE, "r", encoding="utf-8") as f:
                    self.registry = json.load(f)
            else:
                self.registry = json.loads(json.dumps(DEFAULT_REGISTRY))
                should_save = True
        except (json.JSONDecodeError, IOError):
            logger.warning("Config file corrupted, resetting to defaults")
            self.registry = json.loads(json.dumps(DEFAULT_REGISTRY))
            should_save = True

        # 2. Auto-patch providers
        if "providers" not in self.registry:
            self.registry["providers"] = {}
        for pid, pdata in DEFAULT_REGISTRY["providers"].items():
            if pid not in self.registry["providers"]:
                logger.info(f"Patching config: adding provider '{pid}'")
                self.registry["providers"][pid] = dict(pdata)
                should_save = True
            else:
                current = self.registry["providers"][pid]
                if "api_key" not in current:
                    current["api_key"] = pdata["api_key"]
                    should_save = True

        # 3. Auto-patch routing
        if "routing" not in self.registry:
            self.registry["routing"] = dict(DEFAULT_REGISTRY["routing"])
            should_save = True

        # 4. Auto-patch custom_blueprints
        if "custom_blueprints" not in self.registry:
            self.registry["custom_blueprints"] = {}
            should_save = True

        if should_save:
            self.save_config()

    def reload_config(self):
        """Đọc lại config từ file."""
        self._load_config()

    def save_config(self):
        """Ghi config xuống file."""
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with open(AI_REGISTRY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.registry, f, indent=4, ensure_ascii=False)
            logger.debug(f"Config saved to {AI_REGISTRY_FILE}")
        except IOError as e:
            logger.error(f"Cannot save config: {e}")

    # =========================================================================
    # KEY MANAGEMENT: Get / Set / Rotate
    # =========================================================================

    def update_api_key(self, pid: str, key: str) -> bool:
        """Cập nhật API key cho provider."""
        if pid in self.registry["providers"]:
            self.registry["providers"][pid]["api_key"] = str(key).strip()
            self.save_config()
            return True
        return False

    def get_api_key(self, pid: str) -> str:
        """Lấy 1 key (random nếu có nhiều)."""
        raw = self.registry["providers"].get(pid, {}).get("api_key", "")
        keys = self._parse_keys(raw)
        return random.choice(keys) if keys else ""

    def _parse_keys(self, raw_key_string: str) -> list:
        """Tách chuỗi key (phân cách bởi \\n hoặc ,) thành list."""
        if not raw_key_string:
            return []
        keys = raw_key_string.replace(",", "\n").split("\n")
        return [k.strip() for k in keys if k.strip()]

    # Backward compat alias
    def get_rotated_key(self, raw_key_string):
        """Alias cho _parse_keys (backward compat với code cũ)."""
        result = self._parse_keys(raw_key_string)
        return result if result else ""

    # =========================================================================
    # MODEL & ROUTING MANAGEMENT
    # =========================================================================

    def get_models(self, pid: str) -> list:
        """Lấy danh sách model của provider."""
        return self.registry["providers"].get(pid, {}).get("models", [])

    def set_task_route(self, task: str, pid: str, model: str):
        """Gán AI provider + model cho một nhiệm vụ."""
        if "routing" not in self.registry:
            self.registry["routing"] = {}
        self.registry["routing"][task] = {"provider": pid, "model": model}
        self.save_config()

    # =========================================================================
    # SMART AUTO-ROUTING: Tự động phân công AI tối ưu
    # =========================================================================

    ROLE_PRIORITY_CHAIN = {
        "script_writer": ["lm_studio", "google", "openai"],
        "visual_artist": ["lm_studio", "google", "pollinations"], 
        "researcher": ["lm_studio", "google", "openai"],
        "branding_expert": ["lm_studio", "google"],
        "viral_analyst": ["lm_studio", "google"],
        "image_generation": ["pollinations", "leonardo", "google"], 
        "voice_actor": ["edge", "openai", "google"],
        "music_composer": ["google", "openai"],
        "visual_qa": ["google", "openai"], # Phân tích hình ảnh
        "audio_separator": ["demucs", "local"], # Tách âm (Demucs)
        "speech_aligner": ["whisperx", "local"] # Khớp sub từng từ (WhisperX)
    }

    def auto_assign_routing(self) -> dict:
        """
        Tự động phân công AI tối ưu cho tất cả vị trí.
        Dựa trên chuỗi ưu tiên và kiểm tra API Key khả dụng.
        Returns dict: {role: {provider, model, reason, status}}
        """
        results = {}
        for role, chain in self.ROLE_PRIORITY_CHAIN.items():
            assigned = False
            for provider in chain:
                # Kiểm tra provider có tồn tại không
                pdata = self.registry.get("providers", {}).get(provider)
                if not pdata:
                    continue
                # Edge TTS miễn phí, không cần key
                if provider == "edge":
                    self.set_task_route(role, provider, "vi-VN-HoaiMyNeural")
                    results[role] = {"provider": provider, "model": "vi-VN-HoaiMyNeural", "reason": "Edge TTS", "status": "✅ OK"}
                    assigned = True
                    break
                # Kiểm tra API Key có hay chưa
                raw_key = pdata.get("api_key", "")
                keys = self._parse_keys(raw_key)
                if keys or provider == "lm_studio":
                    model = "auto_detect" if provider == "lm_studio" else pdata.get("models", ["default"])[0]
                    self.set_task_route(role, provider, model)
                    results[role] = {"provider": provider, "model": model, "reason": "Available", "status": "✅ OK"}
                    assigned = True
                    break
            
            if not assigned:
                # [VEO UPGRADE] Thêm logic cho các provider Local Pro
                if provider in ["demucs", "whisperx", "kokoro"]:
                    results[role] = {"provider": provider, "model": "local_pro", "reason": "Local Engine", "status": "🛡️ Chờ cài đặt"}
                    self.set_task_route(role, provider, "local_pro")
                    assigned = True
                    continue

                results[role] = {"provider": "", "model": "", 
                                 "reason": "❌ Không có API Key nào khả dụng!", "status": "❌ Lỗi"}
        
        self.save_config()
        return results

    def get_role_tooltip(self, role: str) -> str:
        """Lấy tooltip hướng dẫn chi tiết cho từng vai trò."""
        tooltips = {
            "script_writer": (
                "✍️ KIẾN TRÚC SƯ NỘI DUNG\n"
                "• Chuyên gia viết kịch bản, tiêu đề SEO và mô tả video thu hút."
            ),
            "visual_artist": (
                "🎨 ĐẠO DIỄN HÌNH ẢNH\n"
                "• Phân tích kịch bản, tự động chọn Stock hoặc tạo Prompt vẽ ảnh AI."
            ),
            "researcher": (
                "🕵️ CHUYÊN VIÊN PHÂN TÍCH\n"
                "• Tìm ngách thị trường, từ khóa trending và giải mã video đối thủ."
            ),
            "visual_qa": (
                "🔍 KIỂM ĐỊNH VIÊN VIDEO\n"
                "• Tự động soi lỗi hình ảnh/âm thanh bằng AI Vision (Gemini)."
            ),
            "audio_separator": (
                "🎙️ CHUYÊN GIA TÁCH ÂM (PRO)\n"
                "• Tách giọng nói khỏi nhạc nền bằng công nghệ AI Demucs chuyên sâu."
            ),
            "speech_aligner": (
                "📝 CHUYÊN GIA KHỚP CHỮ (PRO)\n"
                "• Lấy tọa độ từng từ (WhisperX) để tạo hiệu ứng chữ nhảy chuyên nghiệp."
            )
        }
        return tooltips.get(role, "Không có hướng dẫn.")

    def get_worker_config(self, task: str) -> dict:
        """Lấy config (provider, api_key, model) cho một nhiệm vụ."""
        routing = self.registry.get("routing", {})
        route_data = routing.get(task) or DEFAULT_REGISTRY["routing"].get(task)
        if not route_data:
            return None
        return self._build_worker_config(route_data)

    def _build_worker_config(self, route_data: dict) -> dict:
        """Build config dict từ routing data."""
        pid = route_data["provider"]
        if pid not in self.registry["providers"]:
            return None
        raw_key = self.registry["providers"][pid]["api_key"]
        keys = self._parse_keys(raw_key)
        return {
            "provider": pid,
            "api_key": random.choice(keys) if keys else "",
            "model": route_data["model"],
        }

    def add_custom_model(self, provider_id: str, model_name: str) -> bool:
        """Thêm model nhập tay vào danh sách."""
        if not model_name or not str(model_name).strip():
            return False
        if provider_id in self.registry["providers"]:
            models = self.registry["providers"][provider_id].get("models", [])
            if model_name not in models:
                models.insert(0, model_name)
                self.registry["providers"][provider_id]["models"] = models
                self.save_config()
                return True
        return False

    def add_custom_ai(self, ai_id, name, endpoint_url, header_template,
                      body_template, output_path, reg_url=""):
        """Thêm AI custom mới (blueprint + provider entry)."""
        self.registry["custom_blueprints"][ai_id] = {
            "name": name,
            "url": endpoint_url,
            "headers": header_template,
            "body": body_template,
            "output_path": output_path,
            "reg_url": reg_url,
        }
        self.registry["providers"][ai_id] = {
            "name": f"⭐ {name}",
            "type": "custom",
            "api_key": "",
            "models": ["default"],
            "reg_url": reg_url,
        }
        self.save_config()
        return True

    # =========================================================================
    # MODEL DISCOVERY: Quét model online
    # =========================================================================

    def fetch_latest_models(self, provider_id: str):
        """Quét danh sách model mới nhất từ provider. Returns (success, message)."""
        api_key = self.get_api_key(provider_id)
        if provider_id != "edge" and provider_id != "lm_studio" and not api_key:
            return False, "Chưa nhập API Key!"

        try:
            new_models = []

            if provider_id == "edge":
                new_models = self._discover_edge_voices()
            elif provider_id == "google":
                new_models = self._discover_google_models(api_key)
            elif provider_id == "openai":
                new_models = self._discover_openai_models(api_key)
            elif provider_id == "lm_studio":
                # Thêm discovery cho LM Studio
                config = self.registry["providers"].get("lm_studio", {})
                url = config.get("url", "http://localhost:1234/v1")
                # Chuẩn hóa URL: Lấy base /v1
                base_url = url.split("/chat/completions")[0].rstrip("/")
                if not base_url.endswith("/v1"):
                    if "/v1/" in base_url: base_url = base_url.split("/v1/")[0] + "/v1"
                    else: base_url = base_url.rstrip("/") + "/v1"
                
                resp = requests.get(f"{base_url}/models", timeout=3)
                if resp.status_code == 200:
                    new_models = [m["id"] for m in resp.json()["data"]]
            else:
                return False, f"Provider '{provider_id}' không hỗ trợ auto-scan."

            if new_models:
                current = set(self.registry["providers"][provider_id].get("models", []))
                updated = sorted(current.union(set(new_models)))
                if provider_id == "edge":
                    updated.sort(key=lambda x: (
                        not x.startswith('vi-VN'),
                        not x.startswith('en-US'), x
                    ))
                self.registry["providers"][provider_id]["models"] = updated
                self.save_config()
                return True, f"Đã cập nhật {len(new_models)} models!"

            return False, "Không tìm thấy model nào."

        except Exception as e:
            logger.error(f"Model discovery error ({provider_id}): {e}")
            return False, str(e)

    def _discover_edge_voices(self) -> list:
        """Quét danh sách giọng Edge TTS."""
        import edge_tts

        async def _fetch():
            return await edge_tts.list_voices()

        voices = asyncio.run(_fetch())
        models = [v['ShortName'] for v in voices]
        models.sort(key=lambda x: (
            not x.startswith('vi-VN'),
            not x.startswith('en-US'), x
        ))
        return models

    def _discover_google_models(self, api_key: str) -> list:
        """Quét model Google Gemini qua REST API."""
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            models = []
            for m in client.models.list(config={"page_size": 200}):
                name = m.name.split("/")[-1]
                if "gemini" in name or "imagen" in name:
                    models.append(name)
            return models
        except Exception:
            # Fallback: REST API trực tiếp
            url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
            resp = requests.get(url, timeout=15)
            if resp.status_code == 200:
                return [
                    m['name'].replace("models/", "")
                    for m in resp.json().get('models', [])
                    if "generateContent" in m.get('supportedGenerationMethods', [])
                ]
            return []

    def _discover_openai_models(self, api_key: str) -> list:
        """Quét model OpenAI."""
        headers = {"Authorization": f"Bearer {api_key}"}
        resp = requests.get("https://api.openai.com/v1/models", headers=headers, timeout=15)
        if resp.status_code == 200:
            return [
                item["id"] for item in resp.json()["data"]
                if any(x in item["id"] for x in ["gpt", "dall-e", "tts", "whisper"])
            ]
        return []

    def execute_custom_ai(self, provider_id: str, prompt: str, model: str = "default", role: str = None, image_path: str = None):
        """
        Gửi yêu cầu đến AI bất kỳ (Cục bộ hoặc Cloud).
        - image_path: Đường dẫn ảnh nếu muốn AI phân tích (Vision)
        """
        # Áp dụng Persona nếu có
        full_prompt = prompt
        if role and role in EXPERT_PERSONAS:
            full_prompt = f"SYSTEM INSTRUCTION:\n{EXPERT_PERSONAS[role]}\n\nUSER REQUEST:\n{prompt}"

        # Native runners
        if provider_id == "google":
            return self._run_gemini(full_prompt, model, image_path=image_path)
        elif provider_id == "lm_studio":
            return self._run_lm_studio(full_prompt, model)
        elif provider_id == "openai":
            return self._run_openai(full_prompt, model)
        elif provider_id == "groq":
            return self._run_groq(prompt, model)
        elif provider_id == "pollinations_text":
            return self._run_pollinations_text(full_prompt, model)
        elif provider_id == "kokoro":
            return self._run_kokoro_local(full_prompt, model)
        elif provider_id == "demucs":
            return self._run_demucs_local(full_prompt)

        # Custom providers
        bp = self.registry["custom_blueprints"].get(provider_id)
        if not bp:
            return False, f"Không tìm thấy cấu hình cho AI: {provider_id}"

        raw_keys = self.registry["providers"].get(provider_id, {}).get("api_key", "")
        key_list = self._parse_keys(raw_keys)

        if not key_list and provider_id not in ["pollinations", "edge"]:
            return False, "Chưa nhập API Key!"
        if not key_list:
            key_list = ["free-mode"]

        last_error = ""
        random.shuffle(key_list)

        for current_key in key_list:
            try:
                h_str = bp["headers"].replace("{api_key}", current_key)
                headers = json.loads(h_str)

                safe_prompt = prompt.replace("\n", "\\n").replace('"', '\\"')
                b_str = bp["body"].replace("{prompt}", safe_prompt).replace("{model}", model)
                body = json.loads(b_str)

                resp = requests.post(bp["url"], json=body, headers=headers, timeout=60)

                if resp.status_code == 200:
                    data = resp.json()
                    result = data
                    for k in bp["output_path"].split("."):
                        if "[" in k:
                            name, idx = k.split("[")
                            idx = int(idx.replace("]", ""))
                            result = result[name][idx]
                        else:
                            result = result[k]
                    return True, result
                else:
                    last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    continue

            except Exception as e:
                last_error = str(e)
                continue

        return False, f"All keys failed. Last error: {last_error}"

    # =========================================================================
    # PRIVATE RUNNERS
    # =========================================================================

    def _run_lm_studio(self, prompt, model="auto_detect"):
        """Chạy AI trên máy cục bộ (LM Studio) - Hỗ trợ tự động phát hiện Model"""
        config = self.registry["providers"].get("lm_studio")
        if not config: return False, "Chưa cấu hình LM Studio"
        
        base_url = config.get("url", "http://localhost:1234/v1")
        
        # 1. Tự động phát hiện Model nếu để auto_detect
        target_model = model
        if model == "auto_detect":
            try:
                resp = requests.get(f"{base_url}/models", timeout=3)
                if resp.status_code == 200:
                    models_data = resp.json()
                    if "data" in models_data and len(models_data["data"]) > 0:
                        target_model = models_data["data"][0]["id"]
                        logger.info(f"🤖 LM Studio: Tự động chọn model: {target_model}")
                    else:
                        return False, "LM Studio đang bật nhưng chưa nạp (Load) model nào!"
                else:
                    return False, f"Không thể kết nối LM Studio (Status: {resp.status_code})"
            except Exception as e:
                return False, f"LM Studio chưa bật? (Lỗi: {e})"

        # 2. Gửi request OpenAI-compatible
        payload = {
            "model": target_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7
        }
        
        try:
            resp = requests.post(f"{base_url}/chat/completions", json=payload, timeout=120)
            if resp.status_code == 200:
                result = resp.json()
                return True, result["choices"][0]["message"]["content"]
            else:
                return False, f"LM Studio Error: {resp.text}"
        except Exception as e:
            return False, f"Lỗi kết nối LM Studio: {e}"

    def _run_gemini(self, prompt: str, model_input: str = "default", image_path: str = None):
        """Google Gemini với multi-key rotation và Vision support."""
        raw_keys = self.registry["providers"]["google"].get("api_key", "")
        keys = self._parse_keys(raw_keys)
        if not keys: return False, "Thiếu Google API Key!"
        
        model_name = "gemini-1.5-flash" if model_input == "default" else model_input
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={random.choice(keys)}"
        
        try:
            resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=60)
            if resp.status_code == 200:
                return True, resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            return False, f"Gemini Error: {resp.status_code}"
        except Exception as e:
            return False, str(e)

    def _run_groq(self, prompt: str, model: str = "default"):
        """Groq (Llama) với key rotation."""
        raw_keys = self.registry["providers"].get("groq", {}).get("api_key", "")
        keys = self._parse_keys(raw_keys)
        if not keys:
            return False, "Thiếu Groq API Key"
        random.shuffle(keys)

        if not model or model == "default":
            model = "llama3-70b-8192"

        last_error = ""
        for api_key in keys:
            try:
                resp = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.7},
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    timeout=60,
                )
                if resp.status_code == 200:
                    return True, resp.json()["choices"][0]["message"]["content"]
                elif resp.status_code == 429:
                    logger.warning(f"Groq key ...{api_key[-4:]} rate limited, rotating")
                    continue
                else:
                    last_error = f"Groq {resp.status_code}: {resp.text[:200]}"
                    continue
            except Exception as e:
                last_error = str(e)
                continue

        return False, f"All Groq keys failed. Last: {last_error}"

    # =========================================================================
    # PRIVATE RUNNERS: OpenAI
    # =========================================================================

    def _run_openai(self, prompt: str, model: str = "default"):
        """OpenAI (GPT) với key rotation."""
        raw_keys = self.registry["providers"]["openai"].get("api_key", "")
        keys = self._parse_keys(raw_keys)
        if not keys:
            return False, "Thiếu OpenAI API Key"
        random.shuffle(keys)

        if not model or model == "default":
            model = "gpt-4o-mini"

        last_error = ""
        for api_key in keys:
            try:
                resp = requests.post(
                    "https://api.openai.com/v1/chat/completions",
                    json={"model": model, "messages": [{"role": "user", "content": prompt}]},
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    timeout=60,
                )
                if resp.status_code == 200:
                    return True, resp.json()["choices"][0]["message"]["content"]
                elif resp.status_code == 429:
                    logger.warning(f"OpenAI key ...{api_key[-4:]} rate limited, rotating")
                    continue
                else:
                    last_error = f"OpenAI {resp.status_code}: {resp.text[:200]}"
                    continue
            except Exception as e:
                last_error = str(e)
                continue

        return False, f"All OpenAI keys failed. Last: {last_error}"
    def _run_pollinations_text(self, prompt: str, model: str = 'default'):
        try:
            if not model or model == 'default': model = 'openai'
            url = 'https://text.pollinations.ai/'
            payload = { 'messages': [{'role': 'user', 'content': prompt}], 'model': model, 'seed': 12345, 'json': False }
            resp = requests.post(url, json=payload, timeout=60)
            if resp.status_code == 200: return True, resp.text.strip()
            return False, f'Pollinations error {resp.status_code}'
        except Exception as e: return False, str(e)
