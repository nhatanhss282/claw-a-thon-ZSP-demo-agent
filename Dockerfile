FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent.py .
COPY CLAUDE.md .

# Thu muc luu bao cao dau ra (dung khi chay CLI, mount volume de lay file ve)
RUN mkdir -p /app/output

ENV AGENT_MODEL=claude-sonnet-4-6
ENV PORT=8080

EXPOSE 8080

ENTRYPOINT ["python", "agent.py"]

# Mac dinh: chay nhu web service tuan thu Service Contract cua GreenNode AgentBase
# (GET /health, POST /invoke, lang nghe port 8080).
# De chay CLI mot lan thay vi server, override CMD luc docker run, vi du:
#   docker run --rm -e ANTHROPIC_API_KEY=... <image> --output /app/output/report.md
CMD ["--serve"]
