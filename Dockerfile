FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent.py .
COPY CLAUDE.md .

# Thu muc luu bao cao dau ra (mount volume khi chay de lay file ve)
RUN mkdir -p /app/output

ENV AGENT_MODEL=claude-sonnet-4-6

ENTRYPOINT ["python", "agent.py"]
CMD ["--output", "/app/output/fintech_sea_weekly.md"]
