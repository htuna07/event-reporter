FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Europe/Istanbul

RUN apt-get update \
    && apt-get install -y --no-install-recommends cron tzdata \
    && ln -snf /usr/share/zoneinfo/Europe/Istanbul /etc/localtime \
    && echo Europe/Istanbul > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY activity_reporter/ ./activity_reporter/
COPY scripts/send_telegram_report.py scripts/run_daily_workflow.py scripts/container_entrypoint.py ./scripts/
COPY docker/daily-activity-report /etc/cron.d/daily-activity-report
RUN chmod 0644 /etc/cron.d/daily-activity-report

ENTRYPOINT ["python", "-m", "scripts.container_entrypoint"]
