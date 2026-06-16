FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent.py .
COPY CLAUDE.md .

# Thu muc luu bao cao dau ra (dung khi chay CLI, mount volume de lay file ve)
RUN mkdir -p /app/output

ENV LLM_MODEL=google/gemma-4-31b-it
ENV LLM_BASE_URL=https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1
ENV PORT=8080

EXPOSE 8080

ENTRYPOINT ["python", "agent.py"]

# Mac dinh: chay nhu web service tuan thu Service Contract cua GreenNode AgentBase
# (GET /health, POST /invoke, lang nghe port 8080).
# Can truyen env LLM_API_KEY (GreenNode MaaS) va TAVILY_API_KEY (web search) khi chay.
# De chay CLI mot lan thay vi server, override CMD luc docker run, vi du:
#   docker run --rm -e LLM_API_KEY=... -e TAVILY_API_KEY=... <image> --output /app/output/report.md
CMD ["--serve"]
