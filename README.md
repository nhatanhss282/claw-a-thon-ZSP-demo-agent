# Fintech SEA Weekly Scan Agent (BD Zalopay)

Agent tự động quét tin tức Fintech Đông Nam Á mỗi tuần và tổng hợp báo cáo theo segment merchant (soundbox, SMB, key merchant...), bao gồm xu hướng thị trường, sản phẩm mới, động thái đối thủ, chính sách/quy định, và gợi ý talking points cho đội BD. Triển khai trên GreenNode AgentBase với async job API.

Logic chi tiết và quy tắc nội dung nằm trong [`CLAUDE.md`](./CLAUDE.md).

## 1. Yêu cầu

- Python 3.10+
- API key Anthropic (biến môi trường `ANTHROPIC_API_KEY`)

## 2. Cài đặt & chạy local

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -r requirements.txt

export ANTHROPIC_API_KEY="sk-ant-..."   # Windows (PowerShell): $env:ANTHROPIC_API_KEY="sk-ant-..."

# In ra stdout
python agent.py

# Lưu thành file markdown
python agent.py --output output/fintech_sea_weekly.md
```

### Tuỳ chọn

| Flag / Env | Mô tả | Mặc định |
|---|---|---|
| `--output`, `-o` | Đường dẫn file `.md` để lưu báo cáo | không lưu, chỉ in stdout |
| `--model` | Model Claude sử dụng | `claude-sonnet-4-6` |
| `AGENT_MODEL` (env) | Tương đương `--model` nếu không truyền flag | `claude-sonnet-4-6` |
| `ANTHROPIC_API_KEY` (env) | **Bắt buộc** — API key Anthropic | — |

## 3. Chạy bằng Docker

```bash
docker build -t fintech-sea-bd-agent .

docker run --rm \
  -e ANTHROPIC_API_KEY="sk-ant-..." \
  -v "$(pwd)/output:/app/output" \
  fintech-sea-bd-agent
```

Báo cáo sẽ được lưu vào `./output/fintech_sea_weekly.md` trên máy host.

## 4. Chạy định kỳ hàng tuần

Có thể dùng `cron` (Linux/macOS) hoặc Task Scheduler (Windows) để chạy container/script
mỗi sáng thứ Hai, ví dụ với cron:

```cron
0 8 * * 1 cd /path/to/fintech-sea-bd-agent && docker run --rm -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY -v $(pwd)/output:/app/output fintech-sea-bd-agent
```

## 5. Tuỳ chỉnh nội dung

- Sửa `SYSTEM_PROMPT` / `USER_PROMPT_TEMPLATE` trong `agent.py` để thay đổi cấu trúc,
  từ khoá tìm kiếm, hoặc số lượng bullet mỗi trục.
- Sửa `CLAUDE.md` để cập nhật quy tắc nội dung — đây là "nguồn sự thật" mô tả process,
  nên giữ đồng bộ với `agent.py` khi thay đổi.
- `MAX_SEARCH_USES` trong `agent.py` giới hạn số lần agent được gọi web search trong
  một lần chạy (mặc định 8) — tăng nếu cần bao quát nhiều chủ đề hơn.

## 6. Cấu trúc thư mục

```
fintech-sea-bd-agent/
├── CLAUDE.md        # Mô tả process, quy tắc nội dung, vai trò agent
├── agent.py         # Script chính: gọi Claude API + web search, in/lưu báo cáo
├── requirements.txt # Python dependencies
├── Dockerfile       # Đóng gói agent để chạy trong container
└── README.md        # Tài liệu này
```
