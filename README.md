# CoderX 🤖

> Autonomous AI Developer Bot — Nhận lệnh từ Telegram, lên kế hoạch bằng ChatGPT, thực thi bằng Antigravity Agent.

## Kiến trúc

```
Telegram
  │ /code <task>
  ▼
ChatGPT Planner (gpt-4o)
  │ Phân tích → chia nhỏ thành steps [code→test→fix→review]
  ▼
Step Runner (Pipeline)
  ├── [code/modify/test/fix] → antigravity chat --mode agent "<prompt>"
  │                              └── Antigravity Agent tự code trong IDE
  └── [shell] → npm install / pip install / git...
  ▼
File Monitor (watchdog)
  │ Detect .coderx/step_N_done.json → step hoàn thành
  ▼
Telegram Report
```

## Setup

### 1. Cài dependencies
```bash
cd CoderX
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Tạo .env
```bash
cp .env.example .env
# Điền các API keys vào .env
```

### 3. Lấy Telegram User ID
Gửi tin nhắn cho [@userinfobot](https://t.me/userinfobot) trên Telegram để lấy User ID của bạn.

### 4. Chạy bot
```bash
python main.py
```

## Commands Telegram

| Command | Mô tả |
|---------|--------|
| `/code <task>` | 🚀 Giao task coding cho Antigravity Agent |
| `/ask <question>` | 💡 Hỏi ChatGPT một câu hỏi kỹ thuật |
| `/workspace <path>` | 📁 Xem hoặc đổi workspace |
| `/status` | 📊 Xem trạng thái task hiện tại |
| `/ls` | 📂 List files trong workspace |
| `/stop` | 🛑 Dừng task đang chạy |
| `/help` | ❓ Trợ giúp |

## Cách hoạt động

Khi bạn gửi `/code Tạo REST API users với Flask`:

1. **ChatGPT** phân tích và tạo plan:
   - Step 1 [CODE]: Tạo cấu trúc project
   - Step 2 [CODE]: Implement User model + routes
   - Step 3 [SHELL]: `pip install flask`
   - Step 4 [TEST]: Viết unit tests
   - Step 5 [REVIEW]: Review & optimize

2. Bot gọi `antigravity chat --mode agent "<prompt>"` cho từng step

3. Antigravity Agent tự code trong IDE như người dùng thật

4. File monitor detect `.coderx/step_N_done.json` → step xong → next step

5. Bot báo cáo kết quả về Telegram

## Completion Detection

Antigravity được yêu cầu tạo file `.coderx/step_{id}_done.json` khi hoàn thành:
```json
{
  "status": "done",
  "summary": "Created Flask app with User model and CRUD endpoints",
  "files_changed": ["app.py", "models/user.py", "routes/users.py"]
}
```

Bot đọc file này để biết step đã xong và chuyển sang step tiếp theo.
