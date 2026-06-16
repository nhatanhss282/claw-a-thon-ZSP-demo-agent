Fintech News Weekly Scan Agent là một AI research agent phục vụ team Business Development (BD) và Product của Zalopay.

Mỗi lần chạy, agent tự động tìm kiếm tin tức Fintech công khai trong 7 ngày gần nhất (Việt Nam + Đông Nam Á) qua Tavily Search, sau đó dùng LLM (GreenNode MaaS — OpenAI-compatible endpoint) để tổng hợp thành bản tin Markdown có cấu trúc, actionable.

**Dành cho BD team — 5 trục nội dung:**
1. Xu hướng Fintech SEA trong tuần
2. Sản phẩm mới đáng chú ý
3. Chuyển dịch thị trường & động thái đối thủ (theo segment)
4. Chính sách / quy định mới ảnh hưởng đến BD
5. Gợi ý trao đổi với đối tác (talking points)

**Dành cho Product team — 5 trục nội dung:**
1. Xu hướng UX & Product Fintech SEA
2. Tính năng / sản phẩm mới của đối thủ
3. Benchmark & so sánh tính năng
4. Insight hành vi người dùng & adoption
5. Cơ hội sản phẩm (Product Opportunities)

**Tính năng nổi bật:**
- Hỗ trợ 10+ BD segment (Key Merchant, SMB, Global Merchant, Ngân hàng, Viễn thông, Du lịch, Y tế, Dịch vụ công, PSP quốc tế...)
- So sánh "điểm mới so với tuần trước" tự động từ lịch sử lưu trữ
- 2 chế độ: CLI (`python agent.py --output report.md`) và web service (`--serve`) với Web UI tích hợp
- Tuân thủ Service Contract của GreenNode AgentBase (GET /health, POST /invoke async + GET /result/{job_id})

**Tech stack:** Python · FastAPI · Uvicorn · Tavily Search API · GreenNode AI Platform (MaaS, OpenAI-compatible)
