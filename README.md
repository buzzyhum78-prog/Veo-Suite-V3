# VEO SUITE V3.2 — Enterprise Edition

Bộ công cụ desktop giúp dựng video tự động (script → voice → visuals → render → publish) cho YouTube/TikTok, viết bằng **PyQt6 + SQLite + FFmpeg**.

> Trạng thái: đang trong giai đoạn dọn dẹp/refactor. PR-1 (bảo mật) và PR-2 (ổn định) đã hoàn thành. Xem `docs/veo_suite_v3_evaluation.md` cho roadmap đầy đủ.

---

## 1. Tính năng chính

| Module | Mô tả ngắn |
|---|---|
| **Phòng Nội Dung** (`modules/content`) | Sinh kịch bản, dịch, TTS edge-tts, lưu project |
| **Phòng Media / Asset Factory** (`modules/assets_factory`) | Sinh ảnh/video stock (Pixabay…) + AI image-gen, ghép Ken-Burns |
| **Phòng Radar** (`modules/radar`) | Spy YouTube, gợi ý ý tưởng từ trending |
| **Phòng Publisher** (`modules/publisher`) | Quản lý account + lịch đăng (đang refactor) |
| **Render service** (`services/render_service.py`) | FFmpeg slideshow / concat / subtitle / branding |
| **Database** (`database/db_manager.py`) | SQLite thread-safe, schema chuẩn hoá projects/scenes/settings/accounts |

---

## 2. Yêu cầu hệ thống

* Python **3.11** hoặc **3.12** (Windows 10/11, macOS 13+, Ubuntu 22.04+)
* **FFmpeg ≥ 4.4** trong PATH (hoặc cấu hình `FFMPEG_PATH` trong `.env`)
* (Tuỳ chọn) GPU NVIDIA + driver mới nhất nếu muốn tăng tốc encode

---

## 3. Cài đặt

```bash
# 1. Clone
git clone https://github.com/<your-org>/Veo-Suite-V3.git
cd Veo-Suite-V3

# 2. Tạo venv
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# 3. Cài dependencies
pip install -r requirements.txt

# 4. Cấu hình môi trường
cp .env.example .env
# rồi mở .env và điền các API key thật (Gemini, Pixabay, ...)
```

---

## 4. Chạy ứng dụng

```bash
python VeoSuite_V3/main.py
```

Lần đầu chạy, app sẽ:

1. Tạo thư mục `VeoSuite_V3/logs/`, `VeoSuite_V3/output/`, `VeoSuite_V3/database/`.
2. Khởi tạo SQLite ở `VeoSuite_V3/database/veo_suite.db`.
3. Kiểm tra dependency cốt lõi (PyQt6, sqlite3) trước khi mở UI.

Log được ghi luân chuyển (rotating) tại `VeoSuite_V3/logs/veo_suite.log` — 10 MB × 5 file.

---

## 5. Cấu hình

* **`.env`** — chỉ chứa secret/API key (không commit).
* **`VeoSuite_V3/config/ai_registry.json`** — cấu hình các provider AI (Gemini, OpenAI…). Có thể tham chiếu env-var bằng cú pháp `${VAR_NAME}`.
* **Settings runtime** — lưu trong bảng `settings` của SQLite, sửa qua tab Cài đặt trong UI.

Biến môi trường quan trọng:

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `GEMINI_API_KEY` | (bắt buộc) | Key cho Google Gemini |
| `PIXABAY_API_KEY` | (bắt buộc nếu dùng stock) | Key cho Pixabay |
| `FFMPEG_PATH` | `ffmpeg` | Đường dẫn binary |
| `FFPROBE_PATH` | `ffprobe` | Đường dẫn binary |
| `VEO_FFMPEG_TIMEOUT` | `1800` | Timeout (giây) cho mỗi lần gọi FFmpeg |

---

## 6. Phát triển

### 6.1 Setup môi trường dev

```bash
pip install -r requirements.txt
pip install ruff pytest pre-commit
pre-commit install   # cài git hook
```

### 6.2 Lint / format

```bash
ruff check .          # tìm lỗi
ruff check --fix .    # auto-fix
ruff format .         # format
```

### 6.3 Test

```bash
QT_QPA_PLATFORM=offscreen pytest -q
```

Smoke tests ở `tests/test_smoke.py` kiểm tra:

* Mọi module backend trọng yếu import được (không lỗi cú pháp/missing dep).
* `DatabaseManager` thread-safe (100 thread đồng thời insert/select).
* PR-1 (Pixabay key) và PR-2 (bare except) không bị regression.

### 6.4 CI

GitHub Actions ở `.github/workflows/ci.yml` chạy ruff + pytest trên Python 3.11 và 3.12 cho mọi push/PR vào `main`/`master`.

---

## 7. Cấu trúc thư mục

```
Veo-Suite-V3/
├── .github/workflows/ci.yml       # CI pipeline
├── pyproject.toml                  # ruff/pytest/pyright config
├── .pre-commit-config.yaml         # git hooks
├── .env.example                    # template biến môi trường
├── requirements.txt                # deps (single source of truth)
├── tests/                          # pytest smoke tests
└── VeoSuite_V3/
    ├── main.py                     # entry point
    ├── config/                     # ai_registry.json, font, ...
    ├── database/                   # db_manager.py, veo_suite.db
    ├── modules/
    │   ├── content/                # Phòng Nội Dung
    │   ├── assets_factory/         # Phòng Media
    │   ├── radar/                  # Phòng Radar
    │   └── publisher/              # Phòng Publisher
    ├── services/                   # render, audio, stock, thumbnail, ...
    └── ui/                         # main_window, styles, tabs
```

---

## 8. Lộ trình refactor

| Giai đoạn | Trạng thái | Nội dung |
|---|---|---|
| **PR-1** | ✓ Done | Bảo mật: gỡ cookie/key cứng, `.env`, `.gitignore` |
| **PR-2** | ✓ Done | Ổn định: SQLite thread-safety, logger, FFmpeg timeout, log rotation |
| **PR-3** | ✓ Done | DevOps: pyproject, ruff, pre-commit, CI, smoke tests, README |
| PR-4 | Đang làm | DB: migrate `projects.json` → SQLite, hoàn thiện YouTubeUploader/Scheduler |
| PR-5 | Pending | Refactor god-class các tab UI (content/media/radar) |
| PR-6 | Pending | Tính năng mới: plugin AI provider, telemetry, i18n, dashboard |

---

## 9. Giấy phép

(Bạn tự chọn license — đề xuất MIT cho desktop app nội bộ. Đặt nội dung vào `LICENSE`.)
