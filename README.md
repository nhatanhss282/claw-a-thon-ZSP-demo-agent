# Fintech SEA Weekly Scan Agent (BD Zalopay)

Agent tự động quét tin tức Fintech Đông Nam Á / Việt Nam trong 7 ngày gần nhất và
tổng hợp bản tin theo 4 trục phục vụ Business Development:

1. Xu hướng Fintech Đông Nam Á trong tuần
2. Cập nhật sản phẩm mới đáng chú ý
3. Thị trường có chuyển dịch gì
4. Chính sách/quy định mới hỗ trợ công việc BD

Bản tin **không** bao gồm thông tin riêng về Zalopay — chỉ tập trung vào bối cảnh
ngành/đối thủ/thị trường xung quanh.

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
| `--output`, `-o` | Đường dẫn file `.md` để lưu báo cáo (chế độ CLI) | không lưu, chỉ in stdout |
| `--model` | Model Claude sử dụng | `claude-sonnet-4-6` |
| `--serve` | Chạy agent dưới dạng web service (`/health`, `/invoke`) | tắt (CLI mode) |
| `AGENT_MODEL` (env) | Tương đương `--model` nếu không truyền flag | `claude-sonnet-4-6` |
| `PORT` (env) | Port lắng nghe khi dùng `--serve` | `8080` |
| `ANTHROPIC_API_KEY` (env) | **Bắt buộc** — API key Anthropic | — |

## 3. Chạy bằng Docker

**Chế độ CLI (chạy 1 lần, xuất file markdown):**

```bash
docker build -t fintech-sea-bd-agent .

docker run --rm \
  -e ANTHROPIC_API_KEY="sk-ant-..." \
  -v "$(pwd)/output:/app/output" \
  fintech-sea-bd-agent --output /app/output/fintech_sea_weekly.md
```

Báo cáo sẽ được lưu vào `./output/fintech_sea_weekly.md` trên máy host.

**Chế độ web service (mặc định của image — dùng để deploy lên AgentBase):**

```bash
docker run --rm -p 8080:8080 \
  -e ANTHROPIC_API_KEY="sk-ant-..." \
  fintech-sea-bd-agent

# Test:
curl http://localhost:8080/health
curl -X POST http://localhost:8080/invoke -H "Content-Type: application/json" -d '{}'
```

## 4. Chạy định kỳ hàng tuần

Có thể dùng `cron` (Linux/macOS) hoặc Task Scheduler (Windows) để chạy container/script
mỗi sáng thứ Hai, ví dụ với cron (chế độ CLI):

```cron
0 8 * * 1 cd /path/to/fintech-sea-bd-agent && docker run --rm -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY -v $(pwd)/output:/app/output fintech-sea-bd-agent --output /app/output/fintech_sea_weekly.md
```

Nếu deploy lên GreenNode AgentBase (xem mục 6), có thể gọi `POST /invoke` theo lịch
qua một scheduler/cron service bên ngoài.

## 5. Tuỳ chỉnh nội dung

- Sửa `SYSTEM_PROMPT` / `USER_PROMPT_TEMPLATE` trong `agent.py` để thay đổi cấu trúc,
  từ khoá tìm kiếm, hoặc số lượng bullet mỗi trục.
- Sửa `CLAUDE.md` để cập nhật quy tắc nội dung — đây là "nguồn sự thật" mô tả process,
  nên giữ đồng bộ với `agent.py` khi thay đổi.
- `MAX_SEARCH_USES` trong `agent.py` giới hạn số lần agent được gọi web search trong
  một lần chạy (mặc định 8) — tăng nếu cần bao quát nhiều chủ đề hơn.

## 6. Deploy lên GreenNode AgentBase (VNG Cloud)

Agent đã đáp ứng Service Contract của AgentBase: lắng nghe port `8080`,
`GET /health` trả 200, `POST /invoke` trả `{"output": "<markdown báo cáo>"}`.

**Bước 1 — Tạo Container Registry (vCR) và push image:**

```bash
docker build -t vcr.vngcloud.vn/<your-repo>/fintech-sea-bd-agent:v1 .
docker push vcr.vngcloud.vn/<your-repo>/fintech-sea-bd-agent:v1
```

**Bước 2 — Tạo Identity (IAM) cho agent** theo mục Access Control trên AgentBase
(https://aiplatform.console.vngcloud.vn).

**Bước 3 — Tạo Runtime:**

- Qua Portal: https://aiplatform.console.vngcloud.vn/agent-runtime → **Deploy a new
  Agent** → **Custom Agent** → điền `Image URL`, flavor (vd `1x1-general`), biến
  môi trường `ANTHROPIC_API_KEY` (đánh dấu là secret) → **Create**.
- Hoặc qua API `POST https://agentbase.api.vngcloud.vn/runtime/agent-runtimes` với
  `imageUrl`, `environmentVariables: {"ANTHROPIC_API_KEY": "..."}`, `flavorId`,
  `autoscaling`.

**Bước 4 — Kiểm tra:** đợi Runtime chuyển từ `CREATING` → `ACTIVE`, sau đó gọi
`POST /invoke` trên endpoint được AgentBase cấp để nhận bản tin.

> Cách nhanh hơn: dùng [AgentBase Skills cho Claude
> Code/Cursor](https://github.com/vngcloud/greennode-agentbase-skills) — chạy
> `/agentbase-wizard` để tự động hoá toàn bộ flow build → push → deploy → verify.

## 7. Cấu trúc thư mục

```
fintech-sea-bd-agent/
├── CLAUDE.md        # Mô tả process, quy tắc nội dung, vai trò agent
├── agent.py         # Script chính: CLI hoặc web service (FastAPI) gọi Claude API + web search
├── requirements.txt # Python dependencies
├── Dockerfile       # Đóng gói agent để chạy trong container / deploy AgentBase
└── README.md        # Tài liệu này
```
