from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QPushButton, QGroupBox, QFormLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QComboBox, QMessageBox, QInputDialog, QTabWidget,
    QScrollArea, QDialog, QTextEdit, QApplication, QProgressBar,
    QStackedWidget, QCheckBox, QFileDialog
)
from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QColor, QBrush 
from services.ai_factory import AIFactory
import json
import os # <--- [MỚI] Thêm cái này để xử lý file config
from ui.widgets.ops_tab import OpsTab
from ui.style_kit import apply_kind, apply_accent  # PR-5e: dynamic-property style helpers

# File lưu cấu hình riêng cho Voice
VOICE_CONFIG_FILE = "VEO_DB/voice_engine_config.json"
# [MỚI] File lưu cấu hình Proxy riêng biệt để Radar Tab đọc
PROXY_CONFIG_FILE = "VEO_DB/proxy_config.json"
# ============================================================================
# KHO TÀNG AI (ULTIMATE PRESETS) - KHO MẪU ĐỈNH CAO
# ============================================================================
AI_TEMPLATES = {
    "--- CHỌN MẪU CÓ SẴN (PRESETS) ---": {}, 
    "🗣️ Microsoft Edge TTS (Miễn phí & Cực hay)": {
        "id": "edge",
        "name": "Microsoft Edge Free",
        "url": "local_library", # Đánh dấu là chạy offline/local lib
        "headers": "{}",
        "body": "{}", 
        "output": "binary",
        "reg_url": "https://github.com/rany2/edge-tts",
        "api_key": "free-mode" # Không cần key
    },
    "🚀 OpenRouter (Cổng kết nối 100+ AI: GPT-4, Claude, Llama...)": {
        "id": "openrouter",
        "name": "OpenRouter (All-in-One)",
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "headers": '{"Authorization": "Bearer {api_key}", "Content-Type": "application/json", "HTTP-Referer": "https://veosuite.com"}',
        "body": '{"model": "{model}", "messages": [{"role": "user", "content": "{prompt}"}]}',
        "output": "choices[0].message.content",
        "reg_url": "https://openrouter.ai/keys"
    },
    "🧠 LM Studio (Local AI - Chạy trên máy của bạn)": {
        "id": "lm_studio",
        "name": "LM Studio Local",
        "url": "http://localhost:1234/v1/chat/completions",
        "headers": '{"Content-Type": "application/json"}',
        "body": '{"model": "auto_detect", "messages": [{"role": "user", "content": "{prompt}"}]}',
        "output": "choices[0].message.content",
        "reg_url": "https://lmstudio.ai/"
    },
    "🧠 DeepSeek (Code/Logic cực rẻ - Ngon bổ rẻ)": {
        "id": "deepseek",
        "name": "DeepSeek Chat",
        "url": "https://api.deepseek.com/chat/completions",
        "headers": '{"Authorization": "Bearer {api_key}", "Content-Type": "application/json"}',
        "body": '{"model": "deepseek-chat", "messages": [{"role": "user", "content": "{prompt}"}], "stream": false}',
        "output": "choices[0].message.content",
        "reg_url": "https://platform.deepseek.com/api_keys"
    },

    "⚡ Groq (Llama 3/Mixtral - Tốc độ bàn thờ & FREE)": {
        "id": "groq",
        "name": "Groq Super Fast",
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "headers": '{"Authorization": "Bearer {api_key}", "Content-Type": "application/json"}',
        "body": '{"model": "llama3-70b-8192", "messages": [{"role": "user", "content": "{prompt}"}]}',
        "output": "choices[0].message.content",
        "reg_url": "https://console.groq.com/keys"
    },

    "🧠 Anthropic Claude 3.5 Sonnet (Viết lách đỉnh cao)": {
        "id": "anthropic",
        "name": "Claude 3.5 Sonnet",
        "url": "https://api.anthropic.com/v1/messages",
        "headers": '{"x-api-key": "{api_key}", "anthropic-version": "2023-06-01", "Content-Type": "application/json"}',
        "body": '{"model": "claude-3-5-sonnet-20240620", "max_tokens": 1024, "messages": [{"role": "user", "content": "{prompt}"}]}',
        "output": "content[0].text",
        "reg_url": "https://console.anthropic.com/settings/keys"
    },

    "🎨 Stability AI (Vẽ ảnh SD3 Core - Siêu đẹp)": {
        "id": "stability",
        "name": "Stable Diffusion 3",
        "url": "https://api.stability.ai/v2beta/stable-image/generate/core",
        "headers": '{"Authorization": "Bearer {api_key}", "Accept": "image/*"}', 
        "body": '{"prompt": "{prompt}", "output_format": "jpeg"}', 
        "output": "binary",
        "reg_url": "https://platform.stability.ai/account/keys"
    },

    "🎥 Runway ML (Tạo Video động Gen-3 Alpha)": {
        "id": "runway",
        "name": "Runway Gen-3",
        "url": "https://api.runwayml.com/v1/image_to_video", 
        "headers": '{"Authorization": "Bearer {api_key}", "X-Runway-Version": "2024-09-13", "Content-Type": "application/json"}',
        "body": '{"promptImage": "{prompt}", "model": "gen3a_turbo", "durationSeconds": 5}',
        "output": "output_url", # (Lưu ý: Runway trả về Async task, cần xử lý worker riêng sau này, nhưng cứ thêm config vào trước)
        "reg_url": "https://runwayml.com/"
    },

    "🎨 HuggingFace (Flux Schnell - Vẽ ảnh FREE)": {
        "id": "hf_flux",
        "name": "Flux Schnell (HF Free)",
        "url": "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-schnell",
        "headers": '{"Authorization": "Bearer {api_key}"}',
        "body": '{"inputs": "{prompt}"}',
        "output": "binary",
        "reg_url": "https://huggingface.co/settings/tokens"
    },

    "🗣️ ElevenLabs (Giọng đọc Siêu thực)": {
        "id": "elevenlabs",
        "name": "ElevenLabs Voice",
        "url": "https://api.elevenlabs.io/v1/text-to-speech/eleven_multilingual_v2",
        "headers": '{"xi-api-key": "{api_key}", "Content-Type": "application/json"}',
        "body": '{"text": "{prompt}", "model_id": "eleven_multilingual_v2", "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}}',
        "output": "binary",
        "reg_url": "https://elevenlabs.io/app/speech-synthesis"
    },

    "🔍 Perplexity (Tìm kiếm thông tin thời gian thực)": {
        "id": "perplexity",
        "name": "Perplexity Online",
        "url": "https://api.perplexity.ai/chat/completions",
        "headers": '{"Authorization": "Bearer {api_key}", "Content-Type": "application/json"}',
        "body": '{"model": "llama-3-sonar-large-32k-online", "messages": [{"role": "user", "content": "{prompt}"}]}',
        "output": "choices[0].message.content",
        "reg_url": "https://www.perplexity.ai/settings/api"
    },
    
    "🇫🇷 Mistral AI (Châu Âu - Thông minh & Rẻ)": {
        "id": "mistral",
        "name": "Mistral Large",
        "url": "https://api.mistral.ai/v1/chat/completions",
        "headers": '{"Authorization": "Bearer {api_key}", "Content-Type": "application/json"}',
        "body": '{"model": "mistral-large-latest", "messages": [{"role": "user", "content": "{prompt}"}]}',
        "output": "choices[0].message.content",
        "reg_url": "https://console.mistral.ai/api-keys/"
    }
}

class AdminTab(QWidget):
    log_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.ai = AIFactory()
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        
        lbl_title = QLabel("🛡️ TRUNG TÂM QUẢN TRỊ AI (AI COMMAND CENTER)")
        lbl_title.setObjectName("adminTitleLabel")  # PR-5e: styled via global QSS
        main_layout.addWidget(lbl_title)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("adminSubTabs")  # PR-5e: styled via global QSS
        
        self.tab_resources = QWidget()
        self.setup_resources_tab()
        
        self.tab_routing = QWidget()
        self.setup_routing_tab()
        
        # --- [MỚI] THÊM TAB VOICE ENGINE ---
        self.tab_voice = QWidget()
        self.setup_voice_engine_tab() # Hàm này sẽ viết ở bước 4

        # --- [MỚI] THÊM TAB VPN ---
        self.tab_vpn = QWidget()
        self.setup_vpn_tab()
        # --------------------------

        self.tab_ops = OpsTab()  # Gọi class OpsTab từ file kia
        
        self.tabs.addTab(self.tab_resources, "🔑 Kho Tài Nguyên & API Keys")
        self.tabs.addTab(self.tab_routing, "🤖 Phân Công Nhiệm Vụ")
        self.tabs.addTab(self.tab_voice, "🎧 Xưởng Voice (Engine)") # <--- THÊM DÒNG NÀY
        self.tabs.addTab(self.tab_vpn, "🌐 VPN & Mạng (Anti-Ban)") # <--- Add Tab Mới
        self.tabs.addTab(self.tab_ops, "🛡️ An Ninh & VPS")

        main_layout.addWidget(self.tabs)

    # =========================================================================
    # TAB MỚI: 🎧 CẤU HÌNH VOICE ENGINE (ĐA LUỒNG)
    # =========================================================================
    def setup_voice_engine_tab(self):
        layout = QVBoxLayout(self.tab_voice)
        
        lbl = QLabel("Quản lý các bộ máy tạo giọng nói (Voice Engines). Chọn phương án phù hợp cho từng loại kênh.")
        lbl.setObjectName("hintLabel")  # PR-5e: italic hint via global QSS
        layout.addWidget(lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        v_cont = QVBoxLayout(container)

        # --- BLOCK 1: EDGE TTS (VỆ TINH) ---
        grp_edge = QGroupBox("🟢 1. MICROSOFT EDGE TTS (Miễn Phí - Kênh Vệ Tinh)")
        apply_accent(grp_edge, "emerald")  # PR-5e
        l_edge = QVBoxLayout(grp_edge)
        l_edge.addWidget(QLabel("✅ Trạng thái: Luôn Sẵn Sàng (Tích hợp sẵn)"))
        l_edge.addWidget(QLabel("ℹ️ Chiến thuật: Dùng cho Video số lượng lớn, News, Shorts vệ tinh."))
        v_cont.addWidget(grp_edge)

        # --- BLOCK 2: OPENAI TTS (KÊNH CHÍNH) ---
        grp_openai = QGroupBox("💎 2. OPENAI TTS (Chất Lượng Cao - Kênh Chính)")
        apply_accent(grp_openai, "lilac")  # PR-5e
        l_oa = QFormLayout(grp_openai)
        
        self.chk_openai_enable = QCheckBox("Kích hoạt OpenAI TTS")
        self.txt_openai_key_voice = QLineEdit()
        self.txt_openai_key_voice.setPlaceholderText("sk-proj-xxxxxxxx (Lấy từ Kho Key hoặc nhập mới)")
        self.cb_openai_model = QComboBox(); self.cb_openai_model.addItems(["tts-1 (Nhanh)", "tts-1-hd (Chuẩn Studio)"])
        
        l_oa.addRow(self.chk_openai_enable)
        l_oa.addRow("API Key:", self.txt_openai_key_voice)
        l_oa.addRow("Model:", self.cb_openai_model)
        v_cont.addWidget(grp_openai)

        # --- BLOCK 3: GOOGLE CLOUD TTS (SIÊU THỰC) ---
        grp_google = QGroupBox("🌎 3. GOOGLE CLOUD TTS (WaveNet - Kênh Chính/Review)")
        apply_accent(grp_google, "red")  # PR-5e
        l_gg = QFormLayout(grp_google)
        
        self.chk_google_enable = QCheckBox("Kích hoạt Google Cloud TTS")
        
        h_file = QHBoxLayout()
        self.txt_google_json = QLineEdit()
        self.txt_google_json.setPlaceholderText("Đường dẫn file .json Service Account (Key)")
        btn_pick_json = QPushButton("📂 Chọn File")
        btn_pick_json.clicked.connect(self.pick_google_json)
        h_file.addWidget(self.txt_google_json); h_file.addWidget(btn_pick_json)
        
        l_gg.addRow(self.chk_google_enable)
        l_gg.addRow("Key File (JSON):", h_file)
        l_gg.addRow(QLabel("<i>* Đăng ký Google Cloud Console -> IAM -> Service Accounts -> Create Key (JSON)</i>"))
        v_cont.addWidget(grp_google)

        # --- BLOCK 4: CUSTOM / LOCAL (TƯƠNG LAI) ---
        grp_custom = QGroupBox("🔌 4. CUSTOM / LOCAL API (Nâng cấp sau)")
        apply_accent(grp_custom, "amber")  # PR-5e
        l_cus = QFormLayout(grp_custom)
        self.chk_custom_enable = QCheckBox("Kích hoạt Custom API (Coqui/Bark Local)")
        self.txt_custom_url = QLineEdit()
        self.txt_custom_url.setPlaceholderText("VD: http://localhost:5000/tts")
        l_cus.addRow(self.chk_custom_enable)
        l_cus.addRow("API Endpoint:", self.txt_custom_url)
        v_cont.addWidget(grp_custom)

        scroll.setWidget(container)
        layout.addWidget(scroll)

        # Footer Button
        btn_save = QPushButton("💾 LƯU CẤU HÌNH VOICE")
        btn_save.setMinimumHeight(40)
        apply_kind(btn_save, "primary")  # PR-5e
        btn_save.clicked.connect(self.save_voice_config)
        layout.addWidget(btn_save)

        # Load config khi mở
        self.load_voice_config()

    def pick_google_json(self):
        f, _ = QFileDialog.getOpenFileName(self, "Chọn file JSON Google Cloud", "", "JSON Files (*.json)")
        if f: self.txt_google_json.setText(f)

    def load_voice_config(self):
        if os.path.exists(VOICE_CONFIG_FILE):
            try:
                with open(VOICE_CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                # OpenAI
                self.chk_openai_enable.setChecked(data.get("openai_enable", False))
                self.txt_openai_key_voice.setText(data.get("openai_key", ""))
                idx = self.cb_openai_model.findText(data.get("openai_model", "tts-1"))
                if idx >= 0: self.cb_openai_model.setCurrentIndex(idx)

                # Google
                self.chk_google_enable.setChecked(data.get("google_enable", False))
                self.txt_google_json.setText(data.get("google_json_path", ""))

                # Custom
                self.chk_custom_enable.setChecked(data.get("custom_enable", False))
                self.txt_custom_url.setText(data.get("custom_url", ""))

            except Exception as e: print(f"Lỗi load voice config: {e}")

    def save_voice_config(self):
        config = {
            "openai_enable": self.chk_openai_enable.isChecked(),
            "openai_key": self.txt_openai_key_voice.text().strip(),
            "openai_model": self.cb_openai_model.currentText(),
            
            "google_enable": self.chk_google_enable.isChecked(),
            "google_json_path": self.txt_google_json.text().strip(),
            
            "custom_enable": self.chk_custom_enable.isChecked(),
            "custom_url": self.txt_custom_url.text().strip()
        }
        
        try:
            if not os.path.exists("VEO_DB"): os.makedirs("VEO_DB")
            with open(VOICE_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4)
            QMessageBox.information(self, "Thành công", "✅ Đã lưu cấu hình Engine Voice!\n(AudioService sẽ tự động đọc file này)")
            self.log_signal.emit("🎧 Đã cập nhật cấu hình Voice Engine.")
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", str(e))
            self.log_signal.emit(f"❌ Lỗi lưu cấu hình Voice: {e}")

    # =========================================================================
    # TAB 3: QUẢN LÝ VPN & MẠNG (NEW SECTION)
    # =========================================================================
    def setup_vpn_tab(self):
        layout = QVBoxLayout(self.tab_vpn)
        
        lbl_desc = QLabel("Cấu hình Mạng & Proxy để tránh bị chặn IP khi quét dữ liệu diện rộng.")
        lbl_desc.setObjectName("hintLabel")  # PR-5e: italic hint via global QSS
        layout.addWidget(lbl_desc)

        # --- [MỚI] KHUNG 1: CẤU HÌNH PROXY XOAY CHIỀU (Dành cho Hunter/Spy) ---
        grp_proxy = QGroupBox("🌐 CẤU HÌNH ROTATING PROXY (Cho YouTube/Google)")
        apply_accent(grp_proxy, "blue")  # PR-5e
        l_proxy = QFormLayout(grp_proxy)

        self.chk_use_proxy = QCheckBox("Kích hoạt Proxy (Bật/Tắt)")
        
        self.txt_http_proxy = QLineEdit()
        self.txt_http_proxy.setPlaceholderText("http://user:pass@ip:port")
        
        self.txt_https_proxy = QLineEdit()
        self.txt_https_proxy.setPlaceholderText("http://user:pass@ip:port")

        l_proxy.addRow(self.chk_use_proxy)
        l_proxy.addRow("HTTP Proxy:", self.txt_http_proxy)
        l_proxy.addRow("HTTPS Proxy:", self.txt_https_proxy)
        
        layout.addWidget(grp_proxy)

        # --- [CŨ] KHUNG 2: CÁC CÔNG CỤ ĐỔI IP HỆ THỐNG (System Level) ---
        # (Giữ nguyên code cũ nhưng đổi tên biến để không xung đột)
        grp_sys = QGroupBox("🛠️ CÔNG CỤ ĐỔI IP HỆ THỐNG (WARP / DCOM)")
        apply_accent(grp_sys, "slate")  # PR-5e
        v_sys = QVBoxLayout(grp_sys)
        
        h_type = QHBoxLayout()
        h_type.addWidget(QLabel("Loại đổi IP:"))
        self.cb_vpn_type = QComboBox()
        self.cb_vpn_type.addItems(["⛔ Không dùng", "☁️ Cloudflare WARP", "📶 Dcom 3G/4G"])
        self.vpn_map = {0: "none", 1: "warp", 2: "dcom"}
        self.cb_vpn_type.currentIndexChanged.connect(self.on_vpn_type_changed)
        h_type.addWidget(self.cb_vpn_type)
        v_sys.addLayout(h_type)

        self.stack_vpn = QStackedWidget()
        self.stack_vpn.addWidget(QLabel("  (Dùng mạng gốc hoặc Proxy ở trên)"))
        
        p_warp = QWidget(); l_warp = QVBoxLayout(p_warp)
        self.txt_warp_path = QLineEdit(r"C:\Program Files\Cloudflare\Cloudflare WARP\warp-cli.exe")
        l_warp.addWidget(QLabel("Đường dẫn warp-cli.exe:"))
        l_warp.addWidget(self.txt_warp_path)
        self.stack_vpn.addWidget(p_warp)
        
        p_dcom = QWidget(); l_dcom = QVBoxLayout(p_dcom)
        self.txt_dcom_name = QLineEdit("Viettel")
        l_dcom.addWidget(QLabel("Tên cấu hình Dcom:"))
        l_dcom.addWidget(self.txt_dcom_name)
        self.stack_vpn.addWidget(p_dcom)

        v_sys.addWidget(self.stack_vpn)
        layout.addWidget(grp_sys)

        # --- NÚT CHỨC NĂNG ---
        h_btn = QHBoxLayout()
        
        # Nút Lưu (Gọi hàm mới để lưu cả 2 loại config)
        btn_save = QPushButton("💾 LƯU CẤU HÌNH MẠNG")
        btn_save.clicked.connect(self.save_all_network_config) 
        btn_save.setMinimumHeight(45)
        apply_kind(btn_save, "success")  # PR-5e
        
        # Nút Hướng Dẫn (Mới)
        btn_guide = QPushButton("❓ Hướng Dẫn & Nguồn Mua")
        btn_guide.setMinimumHeight(45)
        apply_kind(btn_guide, "info")  # PR-5e
        btn_guide.clicked.connect(self.show_proxy_guide)

        # Nút Test Proxy (Mới)
        btn_test_proxy = QPushButton("🔄 Test Proxy")
        btn_test_proxy.setMinimumHeight(45)
        apply_kind(btn_test_proxy, "warning")  # PR-5e
        btn_test_proxy.clicked.connect(self.test_proxy_connection)

        # Nút Test VPN Hệ thống (Cũ - Giữ lại nếu cần)
        btn_test_vpn = QPushButton("🛠️ Test Dcom/WARP")
        btn_test_vpn.setMinimumHeight(45)
        apply_kind(btn_test_vpn, "muted")  # PR-5e
        btn_test_vpn.clicked.connect(self.test_vpn_rotate)

        h_btn.addWidget(btn_save)
        h_btn.addWidget(btn_guide)
        h_btn.addWidget(btn_test_proxy)
        h_btn.addWidget(btn_test_vpn)
        
        layout.addLayout(h_btn)
        layout.addStretch()

        # Load Config
        self.load_all_network_config()
    
    def load_proxy_config(self):
        """Đọc file proxy_config.json lên giao diện"""
        if os.path.exists(PROXY_CONFIG_FILE):
            try:
                with open(PROXY_CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                # Load Proxy Settings
                self.chk_use_proxy.setChecked(data.get("use_proxy", False))
                self.txt_http_proxy.setText(data.get("http_proxy", ""))
                self.txt_https_proxy.setText(data.get("https_proxy", ""))

                # Load System VPN (Code cũ - giữ lại để không mất setting cũ)
                self.txt_warp_path.setText(data.get("warp_path", ""))
                self.txt_dcom_name.setText(data.get("dcom_profile", ""))
                # self.txt_proxy_list.setText(data.get("proxy_list", "")) # Nếu bạn muốn giữ cả list cũ

            except Exception as e:
                print(f"Lỗi load proxy config: {e}")
    
    def save_proxy_config(self):
        """Lưu cấu hình xuống file JSON dùng chung"""
        config = {
            # Phần Proxy mới
            "use_proxy": self.chk_use_proxy.isChecked(),
            "http_proxy": self.txt_http_proxy.text().strip(),
            "https_proxy": self.txt_https_proxy.text().strip(),
            
            # Phần System cũ (Lưu kèm vào đây luôn cho gọn)
            "warp_path": self.txt_warp_path.text().strip().replace('"', ''),
            "dcom_profile": self.txt_dcom_name.text().strip(),
             # "proxy_list": self.txt_proxy_list.toPlainText() # Nếu muốn lưu list cũ
        }

        try:
            if not os.path.exists("VEO_DB"): os.makedirs("VEO_DB")
            with open(PROXY_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4)
            QMessageBox.information(self, "Thành công", "✅ Đã lưu cấu hình Proxy & Mạng!\n(Radar Tab sẽ tự động dùng thông số này).")
            self.log_signal.emit("🌐 Đã cập nhật cấu hình Proxy & VPN.")
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", f"Không lưu được file: {e}")
            self.log_signal.emit(f"❌ Lỗi lưu cấu hình mạng: {e}")

    def test_proxy_connection(self):
        """Test kết nối Internet qua Proxy"""
        use_proxy = self.chk_use_proxy.isChecked()
        http = self.txt_http_proxy.text().strip()
        https = self.txt_https_proxy.text().strip()

        if use_proxy and (not http or not https):
            QMessageBox.warning(self, "Thiếu thông tin", "Vui lòng nhập đủ HTTP và HTTPS Proxy!")
            return

        import requests
        proxies = {}
        msg = "Đang test kết nối Mạng gốc..."
        
        if use_proxy:
            proxies = {"http": http, "https": https}
            msg = f"Đang test kết nối qua Proxy:\n{http}"
        
        try:
            QMessageBox.information(self, "Đang Test", msg)
            # Gọi thử Google để check
            resp = requests.get("https://www.google.com", proxies=proxies, timeout=10)
            
            if resp.status_code == 200:
                QMessageBox.information(self, "OK", f"✅ Kết nối thành công!\nStatus Code: {resp.status_code}\nProxy hoạt động tốt.")
            else:
                QMessageBox.warning(self, "Fail", f"❌ Kết nối thất bại. Status Code: {resp.status_code}")

        except Exception as e:
            QMessageBox.critical(self, "Lỗi Kết Nối", f"❌ Không thể kết nối Internet:\n{str(e)}\n\n(Kiểm tra lại IP:Port hoặc User:Pass của Proxy)")

    def show_proxy_guide(self):
        """Hiển thị hướng dẫn sử dụng Proxy chi tiết cho CEO"""
        msg = """
        <style>
            h3 { color: #f1c40f; margin-bottom: 5px; }
            b { color: #00ffea; }
            li { margin-bottom: 5px; }
            .code { background: #333; padding: 3px; color: #fff; font-family: Consolas; }
        </style>
        
        <h3>1. PROXY XOAY LÀ GÌ?</h3>
        <ul>
            <li>Là loại Proxy tự động đổi IP liên tục (sau mỗi request hoặc sau vài phút).</li>
            <li><b>Công dụng:</b> Giúp Tool "Veo Suite" quét dữ liệu (Tab 2, Tab 3) với tốc độ "Xe Tăng" mà không bị Google/YouTube chặn (Lỗi 429 Too Many Requests).</li>
        </ul>

        <h3>2. MUA Ở ĐÂU? (NGUỒN UY TÍN)</h3>
        <ul>
            <li><b>Webshare.io:</b> Rẻ, ổn định, có gói Rotating Proxy giá rẻ.</li>
            <li><b>Smartproxy / Bright Data:</b> Hàng cao cấp, IP sạch (đắt tiền).</li>
            <li><b>Tinsoft / TMProxy:</b> Hàng Việt Nam (thường là Proxy tĩnh hoặc xoay theo key, cần check kỹ định dạng).</li>
        </ul>

        <h3>3. ĐỊNH DẠNG CHUẨN (BẮT BUỘC)</h3>
        Tool chỉ nhận định dạng HTTP/HTTPS có xác thực (User:Pass):
        <br><br>
        <span class="code">http://username:password@ip_address:port</span>
        <br><br>
        <i>Ví dụ thực tế:</i> <span class="code">http://user123:passabc@103.45.67.89:8000</span>

        <h3>4. QUY TRÌNH SỬ DỤNG (3 BƯỚC)</h3>
        <ol>
            <li>Mua Proxy, copy chuỗi IP như định dạng trên.</li>
            <li>Paste vào 2 ô <b>HTTP Proxy</b> và <b>HTTPS Proxy</b> (thường giống hệt nhau).</li>
            <li>Tích vào <b>"Kích hoạt Proxy"</b> -> Bấm <b>LƯU</b>.</li>
            <li>(Quan trọng) Bấm <b>"Test Kết Nối"</b>. Nếu báo <b style="color:#2ecc71;">✅ OK</b> thì hãy sang Tab 2 quét.</li>
        </ol>

        <h3>5. KHI NÀO DÙNG?</h3>
        <ul>
            <li><b>BẬT:</b> Khi cần quét số lượng lớn (Hàng trăm từ khóa/video) ở Tab 2 & 3.</li>
            <li><b>TẮT:</b> Khi chỉ test vài cái hoặc mạng Proxy bị lag/hết dung lượng.</li>
        </ul>
        """
        QMessageBox.about(self, "Cẩm Nang Proxy Xoay Chiều", msg)

    def on_vpn_type_changed(self, index):
        self.stack_vpn.setCurrentIndex(index)

    def load_vpn_config_ui(self):
        """Đọc file config.json lên giao diện"""
        if os.path.exists("VEO_DB/config.json"):
            try:
                with open("VEO_DB/config.json", "r", encoding="utf-8") as f:
                    data = json.load(f)
                    
                # Set Combo box
                provider = data.get("vpn_provider", "none")
                idx = 0
                for k, v in self.vpn_map.items():
                    if v == provider: idx = k; break
                self.cb_vpn_type.setCurrentIndex(idx)
                
                # Set details
                self.txt_warp_path.setText(data.get("warp_path", r"C:\Program Files\Cloudflare\Cloudflare WARP\warp-cli.exe"))
                self.txt_dcom_name.setText(data.get("dcom_profile", "Viettel"))
                self.txt_proxy_list.setText(data.get("proxy_list", ""))
                
            except Exception as e:
                print(f"Lỗi load config VPN: {e}")

    # [HÀM SỬA LỖI] Lưu cấu hình (Tương thích với giao diện mới)
    def save_vpn_config(self):
        """Lưu cấu hình xuống file (Phiên bản fix lỗi txt_proxy_list)"""
        
        # 1. Lấy thông tin từ giao diện
        idx = self.cb_vpn_type.currentIndex()
        provider = self.vpn_map.get(idx, "none")
        
        config = {}
        # Đọc file cũ để giữ lại các setting khác nếu có
        if os.path.exists("VEO_DB/config.json"):
            try:
                with open("VEO_DB/config.json", "r", encoding="utf-8") as f:
                    config = json.load(f)
            except: pass
            
        # 2. Cập nhật thông tin mới
        config["vpn_provider"] = provider
        # Lấy từ ô nhập liệu hiện có (txt_warp_path, txt_dcom_name)
        if hasattr(self, 'txt_warp_path'):
            config["warp_path"] = self.txt_warp_path.text().strip().replace('"', '')
        
        if hasattr(self, 'txt_dcom_name'):
            config["dcom_profile"] = self.txt_dcom_name.text().strip()
            
        # [QUAN TRỌNG] Đã xóa dòng lấy 'proxy_list' cũ gây lỗi
        # Vì giao diện mới không còn ô txt_proxy_list nữa.
        
        # 3. Ghi file
        try:
            if not os.path.exists("VEO_DB"): os.makedirs("VEO_DB")
            with open("VEO_DB/config.json", "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            
            # Chỉ hiện thông báo nếu không phải do hàm Test gọi (để đỡ phiền)
            # Nhưng ở đây cứ để nó chạy ngầm, không popup cũng được, hoặc in ra console
            print("✅ Đã lưu config VPN hệ thống.")
            
        except Exception as e:
            print(f"⚠️ Lỗi lưu file config: {e}")
            # QMessageBox.warning(self, "Lỗi", f"Không lưu được file: {e}")

    def test_vpn_rotate(self):
        """Gọi VPNManager để test thử"""
        # Lưu config trước khi test để đảm bảo manager đọc đúng cái mới nhất
        self.save_vpn_config()
        
        try:
            from services.vpn_manager import VPNManager
            vpn = VPNManager()
            
            QMessageBox.information(self, "Bắt đầu Test", f"Đang thử đổi IP bằng chế độ: {vpn.provider.upper()}...\nVui lòng đợi 5-10s và quan sát mạng của bạn.")
            
            success = vpn.rotate_ip()
            
            if success:
                QMessageBox.information(self, "Kết quả", "✅ Đổi IP thành công (Theo log hệ thống)!")
            else:
                QMessageBox.warning(self, "Kết quả", "❌ Đổi IP thất bại. Vui lòng kiểm tra lại đường dẫn/cấu hình.")
        except ImportError:
             QMessageBox.critical(self, "Lỗi", "Chưa tìm thấy module services.vpn_manager!")

    # =========================================================================
    # TAB 1: QUẢN LÝ TÀI NGUYÊN (GIỮ NGUYÊN CODE CŨ CỦA BẠN)
    # =========================================================================
    def setup_resources_tab(self):
        layout = QVBoxLayout(self.tab_resources)
        
        h_head = QHBoxLayout()
        btn_new_ai = QPushButton("➕ THÊM AI TÙY CHỈNH (Kho Mẫu Đỉnh Cao)")
        apply_kind(btn_new_ai, "ai_magic")  # PR-5e
        btn_new_ai.clicked.connect(self.add_new_ai_dialog)

        btn_refresh = QPushButton("🔄 Làm tươi")
        btn_refresh.setToolTip("Đọc lại file cấu hình từ ổ cứng và cập nhật giao diện")
        apply_kind(btn_refresh, "success")  # PR-5e
        btn_refresh.clicked.connect(self.on_refresh_resources_clicked)

        h_head.addWidget(btn_new_ai)
        h_head.addWidget(btn_refresh)
        h_head.addStretch()
        layout.addLayout(h_head)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("transparentScroll")  # PR-5e: borderless scroll via global QSS

        container = QWidget()
        self.res_layout = QVBoxLayout(container)
        self.res_layout.setSpacing(20)
        self.res_layout.addStretch()
        
        self.refresh_resource_list()
        
        scroll.setWidget(container)
        layout.addWidget(scroll)

    def refresh_resource_list(self):
        while self.res_layout.count() > 1:
            item = self.res_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
            
        for p_id, p_data in self.ai.registry["providers"].items():
            grp = QGroupBox(f"{p_data['name']} (ID: {p_id})")
            apply_accent(grp, "cyan")  # PR-5e
            l_grp = QFormLayout(grp)

            txt_key = QTextEdit()
            txt_key.setPlainText(p_data.get("api_key", ""))
            txt_key.setPlaceholderText("Nhập API Key (Mỗi Key một dòng hoặc cách nhau dấu phẩy).\nHệ thống sẽ tự động xoay vòng nếu Key bị lỗi.")
            txt_key.setFixedHeight(60)
            # PR-5e: rely on global QLineEdit/QTextEdit selectors instead of an inline override.
            
            v_key_btn = QVBoxLayout()
            
            btn_save_key = QPushButton("💾 Lưu Key")
            apply_kind(btn_save_key, "success")  # PR-5e
            btn_save_key.clicked.connect(lambda _, pid=p_id, t=txt_key: self.save_key_manual(pid, t.toPlainText()))

            reg_url = p_data.get("reg_url", "")
            btn_link = QPushButton("🔗 Lấy Key (Web)")
            btn_link.setToolTip(f"Mở trang đăng ký: {reg_url}")
            btn_link.setObjectName("externalLinkButton")  # PR-5e: dashed link-style via global QSS
            if reg_url:
                btn_link.clicked.connect(lambda _, url=reg_url: QDesktopServices.openUrl(QUrl(url)))
            else:
                btn_link.setEnabled(False)

            v_key_btn.addWidget(btn_save_key)
            v_key_btn.addWidget(btn_link)
            
            h_key_area = QHBoxLayout()
            h_key_area.addWidget(txt_key)
            h_key_area.addLayout(v_key_btn)
            
            cb_models = QComboBox()
            cb_models.setEditable(True)
            cb_models.addItems(p_data.get("models", []))
            cb_models.currentTextChanged.connect(lambda val, pid=p_id: self.ai.add_custom_model(pid, val))
            
            h_action = QHBoxLayout()
            
            is_scannable = (p_id in ["google", "openai"]) or (p_data.get("type") == "standard")
            
            if is_scannable:
                btn_scan = QPushButton("🔄 Quét Model Online")
                apply_kind(btn_scan, "info")  # PR-5e
                btn_scan.setToolTip("Cập nhật danh sách Model mới nhất từ hãng")
                btn_scan.clicked.connect(lambda _, pid=p_id, cb=cb_models: self.scan_models(pid, cb))
                h_action.addWidget(btn_scan)
            
            h_action.addStretch()
            
            l_grp.addRow("API Keys:", h_key_area)
            l_grp.addRow("Models:", cb_models)
            
            if h_action.count() > 1: 
                l_grp.addRow("", h_action)
            
            self.res_layout.insertWidget(self.res_layout.count()-1, grp)

    def on_refresh_resources_clicked(self):
        self.ai.reload_config()
        self.refresh_resource_list()
        QMessageBox.information(self, "Đã làm tươi", "✅ Đã tải lại toàn bộ cấu hình Key & Model từ ổ cứng!")            

    def save_key_manual(self, pid, key_text):
        clean_keys = [k.strip() for k in key_text.replace(",", "\n").split("\n") if k.strip()]
        final_key_str = "\n".join(clean_keys)
        self.ai.update_api_key(pid, final_key_str)
        QMessageBox.information(self, "Đã Lưu", f"✅ Đã cập nhật {len(clean_keys)} Key cho {pid}!\nHệ thống sẽ tự động xoay vòng.")
        self.log_signal.emit(f"🔑 Đã cập nhật API Key cho: {pid}")

    def scan_models(self, p_id, cb_widget):
        btn = self.sender()
        btn.setEnabled(False); btn.setText("Đang kết nối...")
        QApplication.processEvents()
        
        success, msg = self.ai.fetch_latest_models(p_id)
        
        btn.setEnabled(True); btn.setText("🔄 Quét Model Online")
        if success:
            QMessageBox.information(self, "Thành công", msg)
            cb_widget.clear()
            cb_widget.addItems(self.ai.get_models(p_id))
        else:
            QMessageBox.warning(self, "Lỗi kết nối", msg)

    # --- HỘP THOẠI THÊM AI (AUTO-FILL) ---
    def add_new_ai_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Thêm AI Mới (Hỗ trợ cấu hình tự động)")
        dialog.setMinimumWidth(800)
        l = QFormLayout(dialog)
        
        cb_template = QComboBox()
        cb_template.addItems(AI_TEMPLATES.keys())
        l.addRow("📂 CHỌN MẪU CÓ SẴN:", cb_template)
        l.addRow(QLabel("--- Hoặc tự nhập thông số ---"))

        txt_id = QLineEdit(); txt_id.setPlaceholderText("ID (VD: deepseek)")
        txt_name = QLineEdit(); txt_name.setPlaceholderText("Tên hiển thị")
        txt_url = QLineEdit(); txt_url.setPlaceholderText("Endpoint URL")
        txt_reg = QLineEdit(); txt_reg.setPlaceholderText("Link lấy Key")
        
        txt_headers = QTextEdit(); txt_headers.setFixedHeight(60); txt_headers.setPlaceholderText("JSON Headers")
        txt_body = QTextEdit(); txt_body.setFixedHeight(80); txt_body.setPlaceholderText("JSON Body")
        txt_output = QLineEdit(); txt_output.setPlaceholderText("Output Path")
        
        def apply_template(text):
            data = AI_TEMPLATES.get(text, {})
            if not data: return
            txt_id.setText(data.get("id", ""))
            txt_name.setText(data.get("name", ""))
            txt_url.setText(data.get("url", ""))
            txt_headers.setText(data.get("headers", ""))
            txt_body.setText(data.get("body", ""))
            txt_output.setText(data.get("output", ""))
            txt_reg.setText(data.get("reg_url", ""))
            
        cb_template.currentTextChanged.connect(apply_template)

        l.addRow("Mã ID:", txt_id)
        l.addRow("Tên:", txt_name)
        l.addRow("API URL:", txt_url)
        l.addRow("Link Web:", txt_reg)
        l.addRow("Headers:", txt_headers)
        l.addRow("Body:", txt_body)
        l.addRow("Output Path:", txt_output)
        
        btn_ok = QPushButton("LƯU CẤU HÌNH")
        apply_kind(btn_ok, "success")  # PR-5e
        btn_ok.clicked.connect(lambda: self.save_custom_ai(dialog, txt_id, txt_name, txt_url, txt_headers, txt_body, txt_output, txt_reg))
        l.addRow("", btn_ok)
        dialog.exec()

    def save_custom_ai(self, dialog, *args):
        try:
            t_id, t_name, t_url, t_head, t_body, t_out, t_reg = args
            json.loads(t_head.toPlainText()); json.loads(t_body.toPlainText())
            
            self.ai.add_custom_ai(
                t_id.text().strip(), t_name.text().strip(), t_url.text().strip(),
                t_head.toPlainText(), t_body.toPlainText(), t_out.text().strip(),
                t_reg.text().strip()
            )
            QMessageBox.information(self, "Xong", "✅ Đã thêm AI mới thành công!"); self.refresh_resource_list(); self.refresh_routing_table(); dialog.accept()
        except Exception as e: QMessageBox.warning(self, "Lỗi", str(e))

    # =========================================================================
    # TAB 2: PHÂN CÔNG NHIỆM VỤ (GIAO DIỆN MỚI - GROUPING)
    # =========================================================================
    def setup_routing_tab(self):
        # 1. Reset Layout nếu đã có (Fix lỗi đè giao diện)
        if self.tab_routing.layout():
            QWidget().setLayout(self.tab_routing.layout()) 
            
        layout = QVBoxLayout(self.tab_routing)
        
        # 2. Header Hướng dẫn
        lbl_info = QLabel("<i>Tại đây bạn chỉ định AI nào sẽ phụ trách việc gì (Ví dụ: GPT-4 viết kịch bản, Gemini quét trend).</i>")
        lbl_info.setObjectName("hintLabel")  # PR-5e: italic hint via global QSS
        layout.addWidget(lbl_info)

        # 3. Vùng cuộn (Scroll Area) - Chứa các GroupBox
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("transparentScroll")  # PR-5e: borderless scroll via global QSS
        
        self.routing_container = QWidget()
        self.routing_layout = QVBoxLayout(self.routing_container)
        self.routing_layout.setSpacing(15) 
        self.routing_layout.addStretch() # Đẩy nội dung lên trên
        
        scroll.setWidget(self.routing_container)
        layout.addWidget(scroll)
        
        # 4. Footer Buttons (Nút Lưu & Hướng dẫn)
        h_btn = QHBoxLayout()
        
        btn_auto = QPushButton("⚡ TỰ ĐỘNG PHÂN CÔNG (Khuyến nghị)")
        apply_kind(btn_auto, "warning")  # PR-5e
        btn_auto.clicked.connect(self._auto_assign_routing)

        btn_refresh = QPushButton("💾 Lưu & Làm mới Cấu hình")
        apply_kind(btn_refresh, "success")  # PR-5e
        btn_refresh.clicked.connect(self.refresh_routing_table_manual)

        btn_guide = QPushButton("❓ Xem Hướng dẫn Mapping")
        apply_kind(btn_guide, "info")  # PR-5e
        btn_guide.clicked.connect(self.show_mapping_guide) 

        h_btn.addWidget(btn_auto)
        h_btn.addWidget(btn_refresh)
        h_btn.addWidget(btn_guide)
        layout.addLayout(h_btn)
        
        # 5. Khởi tạo dữ liệu
        self.refresh_routing_table()

    def _auto_assign_routing(self):
        """Tự động phân công AI và refresh giao diện."""
        results = self.ai.auto_assign_routing()
        self.refresh_routing_table()
        
        report_lines = []
        for role, info in results.items():
            status = info.get("status", "—")
            reason = info.get("reason", "")
            provider = info.get("provider", "")
            model = info.get("model", "")
            report_lines.append(f"{status} {role}: {provider}/{model}\n   → {reason}")
            
        QMessageBox.information(
            self, "⚡ Phân Công Tự Động Hoàn Tất",
            "Hệ thống đã quét API Key và phân công AI tối ưu!\n\n" + "\n\n".join(report_lines)
        )

    def refresh_routing_table(self):
        """Hàm vẽ lại giao diện phân công (Đã Fix giao diện đẹp + Nút Dropdown)"""
        # Xóa hết widget cũ trong layout
        while self.routing_layout.count() > 1: 
            item = self.routing_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        
        # Lấy config
        routing_config = self.ai.registry.get("routing", {})
        providers = self.ai.registry.get("providers", {})
        
        # Style cho ComboBox (Fix lỗi mất nút tam giác & co chữ)
        # Style cho ComboBox và Table trong Admin Tab
        COMBO_STYLE = """
            QComboBox {
                border: 1px solid #555;
                border-radius: 4px;
                padding: 5px 10px; /* Tăng padding ngang cho thoáng */
                background: #2d2d30;
                color: #f1f1f1;
                font-size: 13px;
                min-height: 30px; /* Cao hơn, dễ bấm */
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 30px;
                border-left-width: 0px;
                background: #3e3e42;
                border-top-right-radius: 4px;
                border-bottom-right-radius: 4px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid #f1c40f; /* Mũi tên vàng to hơn */
                margin-top: 1px;
            }
            QComboBox:hover {
                border: 1px solid #f1c40f; /* Viền vàng khi rê chuột vào */
            }
        """
        
        # ĐỊNH NGHĨA CÁC NHÓM NHIỆM VỤ (Đã thêm branding_expert)
        GROUPS = {
            "📡 PHÒNG TÌNH BÁO (RADAR TAB 1-3)": [
                ("keyword_researcher", "🔍 Gợi ý Từ Khóa (Tab 1)", "Gemini Flash"),
                ("viral_analyst",      "🕵️ Giải Mã Video/Spy (Tab 3)", "Gemini Pro"),
                ("branding_expert",    "✨ Lên Kế Hoạch/Đặt Tên Kênh (Tab 3)", "Gemini Flash") 
            ],
            "🏭 PHÒNG BIÊN TẬP (CONTENT TAB 4)": [
                ("script_writer",      "📝 Viết Kịch Bản (Writer)", "GPT-4o / Claude"),
                ("visual_artist",      "🖼️ Vẽ Minh Họa (Visual Prompt)", "GPT-4o / Flux"),                
            ],
            "🎧 XƯỞNG MEDIA (TAB 5) & HỖ TRỢ": [
                ("brand_artist",       "🎨 Thiết kế Logo/Banner/Thumbnail (Designer)", "GPT-4o"),
                ("voice_actor",        "🎙️ Đọc Voice (TTS)", "(Cấu hình bên Tab Voice)"),
                ("music_composer",     "🎵 Soạn Nhạc (Music)", "Suno/Udio (Future)"),
                ("researcher",         "📚 Tra Cứu Chung (Research)", "Perplexity")
            ]
        }
        
        # VẼ GIAO DIỆN TỪNG NHÓM
        for group_name, tasks in GROUPS.items():
            # GroupBox
            grp = QGroupBox(group_name)
            grp.setStyleSheet("QGroupBox {font-weight: bold; border: 1px solid #555; margin-top: 10px; background: #252526;} QGroupBox::title {color: #00e6e6;}")
            
            # Table nhỏ trong Group
            table = QTableWidget()
            table.setRowCount(len(tasks))
            table.setColumnCount(3)
            table.setHorizontalHeaderLabels(["Nhiệm vụ", "AI Phụ Trách", "Model"])
            
            # [CTO FIX] Cấu hình cột rộng rãi hơn
            header = table.horizontalHeader()
            # Cột 0 (Tên): Giãn vừa phải
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents) 
            # Cột 1 (AI) & 2 (Model): Chia đều phần còn lại (Stretch) để không bị co chữ
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
            
            table.verticalHeader().setVisible(False)
            table.verticalHeader().setDefaultSectionSize(50) # Dòng cao hơn chút cho thoáng
            table.setFixedHeight(45 + len(tasks) * 50) 
            table.setStyleSheet("border: none; background: #1e1e1e;")
            
            for row, (task_key, task_label, hint) in enumerate(tasks):
                # Cột 0: Tên
                item_name = QTableWidgetItem(f"{task_label}")
                item_name.setToolTip(f"Khuyên dùng: {hint}")
                item_name.setFlags(Qt.ItemFlag.ItemIsEnabled) # Chỉ đọc
                table.setItem(row, 0, item_name)
                
                # Config hiện tại
                curr_pid = routing_config.get(task_key, {}).get("provider", "google")
                curr_mod = routing_config.get(task_key, {}).get("model", "default")
                
                if task_key not in routing_config:
                    self.ai.set_task_route(task_key, curr_pid, curr_mod)
                
                # Cột 1: Provider Combo
                cb_prov = QComboBox()
                cb_prov.setStyleSheet(COMBO_STYLE) # Áp dụng Style xịn
                cb_prov.setCursor(Qt.CursorShape.PointingHandCursor)
                
                for pid, pdata in providers.items():
                    cb_prov.addItem(pdata["name"], pid)
                
                idx = cb_prov.findData(curr_pid)
                if idx >= 0: cb_prov.setCurrentIndex(idx)
                
                # Event change Provider
                cb_prov.currentIndexChanged.connect(lambda idx, r=row, tk=task_key, tb=table: self.on_group_provider_change(tb, r, tk))
                table.setCellWidget(row, 1, cb_prov)
                
                # Cột 2: Model Combo
                # Gọi hàm helper nhưng truyền thêm style vào để nó đẹp đồng bộ
                self.update_group_model_combo(table, row, task_key, curr_pid, curr_mod, style=COMBO_STYLE)

            l_grp = QVBoxLayout(grp)
            l_grp.addWidget(table)
            self.routing_layout.insertWidget(self.routing_layout.count()-1, grp)

    def refresh_routing_table_manual(self):
        self.ai.reload_config()
        self.refresh_routing_table()
        QMessageBox.information(self, "Xong", "✅ Đã làm mới dữ liệu!")

    # --- CÁC HÀM HỖ TRỢ MỚI (KHÔNG DÙNG self.table_route NỮA) ---
    # Sửa dòng định nghĩa hàm để nhận thêm tham số style
    def update_group_model_combo(self, table, row, task_key, provider_id, current_model, style=""):
        cb_mod = QComboBox()
        if style: cb_mod.setStyleSheet(style) # Áp dụng style nếu có
        else: 
            # Style mặc định phòng hờ
            cb_mod.setStyleSheet("QComboBox {border: 1px solid #555; padding: 5px; background: #333; color: white;}")
            
        models = self.ai.get_models(provider_id)
        cb_mod.addItems(models)
        cb_mod.setEditable(True) # Cho phép gõ tay
        
        idx = cb_mod.findText(current_model)
        if idx >= 0: cb_mod.setCurrentIndex(idx)
        else: cb_mod.setCurrentText(current_model)
        
        # Khi đổi model -> Lưu ngay
        cb_mod.currentTextChanged.connect(lambda text, tk=task_key, pid=provider_id: self.ai.set_task_route(tk, pid, text))
        table.setCellWidget(row, 2, cb_mod)

    def on_group_provider_change(self, table, row, task_key):
        # Lấy Provider mới từ combobox trong ô (row, 1)
        cb_prov = table.cellWidget(row, 1)
        new_pid = cb_prov.currentData()
        
        # Lấy danh sách model mới
        models = self.ai.get_models(new_pid)
        first_model = models[0] if models else "default"
        
        # Lưu config
        self.ai.set_task_route(task_key, new_pid, first_model)
        
        # Vẽ lại ô Model (row, 2)
        self.update_group_model_combo(table, row, task_key, new_pid, first_model)

    def show_mapping_guide(self):
        """Hiển thị bảng hướng dẫn cấu hình AI"""
        msg = """
        <style>
            table { border-collapse: collapse; width: 100%; }
            th, td { border: 1px solid #555; padding: 8px; text-align: left; }
            th { background-color: #333; color: #f1c40f; }
            td { color: #ddd; }
            .highlight { color: #00ffea; font-weight: bold; }
        </style>
        <h3>📊 BẢNG ĐỐI CHIẾU NHIỆM VỤ & AI KHUYÊN DÙNG</h3>
        <table>
            <tr>
                <th>Nút Bấm (Radar/Content)</th>
                <th>Mã Code (Task Role)</th>
                <th>Gợi ý Model Tối Ưu</th>
            </tr>
            <tr>
                <td><b>Tab 1:</b> Quét Từ Khóa</td>
                <td class="highlight">keyword_researcher</td>
                <td>Gemini Flash (Rẻ, nhanh, list tốt)</td>
            </tr>
            <tr>
                <td><b>Tab 3:</b> Giải Mã Video (Spy)</td>
                <td class="highlight">viral_analyst</td>
                <td>Gemini Pro / Claude Sonnet (Đọc hiểu sâu)</td>
            </tr>
            <tr>
                <td><b>Tab 3:</b> Lên Kế Hoạch/Tên Kênh</td>
                <td class="highlight">branding_expert</td>
                <td>Gemini Flash (Sáng tạo tốt, Free)</td>
            </tr>
            <tr>
                <td><b>Tab 4:</b> Viết Kịch Bản</td>
                <td class="highlight">script_writer</td>
                <td>GPT-4o / Claude Sonnet (Văn phong hay nhất)</td>
            </tr>
            <tr>
                <td><b>Tab 4:</b> Vẽ Ảnh/Thumb</td>
                <td class="highlight">visual_artist</td>
                <td>Flux / Stability / Dall-E 3</td>
            </tr>
            <tr>
                <td><b>Tab 4:</b> Thiết kế Kênh (Logo)</td>
                <td class="highlight">brand_artist</td>
                <td>GPT-4o (Tư duy trừu tượng tốt)</td>
            </tr>
             <tr>
                <td>Audio/Voice</td>
                <td class="highlight">voice_actor</td>
                <td>(Cấu hình riêng bên Tab Voice Engine)</td>
            </tr>
        </table>
        <p><i>* Hãy chọn Provider và Model tương ứng trong bảng bên dưới để đạt hiệu suất cao nhất!</i></p>
        """
        QMessageBox.about(self, "Hướng dẫn Phân Công AI", msg)
    
    # --- HÀM TẢI CẤU HÌNH (GỘP CẢ PROXY & VPN CŨ) ---
    def load_all_network_config(self):
        # 1. Load Proxy Config (File mới)
        if os.path.exists(PROXY_CONFIG_FILE):
            try:
                with open(PROXY_CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.chk_use_proxy.setChecked(data.get("use_proxy", False))
                self.txt_http_proxy.setText(data.get("http_proxy", ""))
                self.txt_https_proxy.setText(data.get("https_proxy", ""))
            except: pass

        # 2. Load System VPN Config (File cũ: VEO_DB/config.json)
        # Giữ lại logic cũ để không mất setting Dcom/WARP
        if os.path.exists("VEO_DB/config.json"):
            try:
                with open("VEO_DB/config.json", "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                provider = data.get("vpn_provider", "none")
                idx = 0
                for k, v in self.vpn_map.items():
                    if v == provider: idx = k; break
                self.cb_vpn_type.setCurrentIndex(idx)
                
                self.txt_warp_path.setText(data.get("warp_path", ""))
                self.txt_dcom_name.setText(data.get("dcom_profile", ""))
            except: pass

    # --- HÀM LƯU CẤU HÌNH (LƯU RA 2 FILE RIÊNG BIỆT) ---
    def save_all_network_config(self):
        # 1. Lưu Proxy Config (File mới cho Radar Tab dùng)
        proxy_conf = {
            "use_proxy": self.chk_use_proxy.isChecked(),
            "http_proxy": self.txt_http_proxy.text().strip(),
            "https_proxy": self.txt_https_proxy.text().strip()
        }
        try:
            if not os.path.exists("VEO_DB"): os.makedirs("VEO_DB")
            with open(PROXY_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(proxy_conf, f, indent=4)
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", f"Không lưu được Proxy config: {e}")
            return

        # 2. Lưu System VPN Config (File cũ cho Render dùng)
        idx = self.cb_vpn_type.currentIndex()
        provider = self.vpn_map.get(idx, "none")
        
        sys_conf = {}
        # Đọc file cũ để giữ lại setting khác (nếu có)
        if os.path.exists("VEO_DB/config.json"):
            try:
                with open("VEO_DB/config.json", "r") as f: sys_conf = json.load(f)
            except: pass
            
        sys_conf["vpn_provider"] = provider
        sys_conf["warp_path"] = self.txt_warp_path.text().strip().replace('"', '')
        sys_conf["dcom_profile"] = self.txt_dcom_name.text().strip()
        
        try:
            with open("VEO_DB/config.json", "w", encoding="utf-8") as f:
                json.dump(sys_conf, f, indent=4, ensure_ascii=False)
            
            QMessageBox.information(self, "Thành công", "✅ Đã lưu TOÀN BỘ cấu hình mạng (Proxy & System VPN)!")
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", f"Không lưu được System config: {e}")
