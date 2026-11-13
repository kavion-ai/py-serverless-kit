# Amazon SES compatible server, Python (standard library only).
# Build from aws/ses so the console (ui/) is included:
#   docker build -f python/Dockerfile -t pskit/ses:python .
FROM python:3.12-alpine

RUN addgroup -S -g 10001 app && adduser -S -u 10001 -G app -h /app app \
    && mkdir -p /data && chown app:app /data
WORKDIR /app
COPY python/server.py /app/
COPY python/sesserver /app/sesserver/
COPY ui /app/ui/

ENV SES_PORT=4579 SES_SMTP_PORT=2587 SES_BIND=0.0.0.0 SES_DATA_DIR=/data PYTHONUNBUFFERED=1
USER app
VOLUME ["/data"]
EXPOSE 4579 2587
HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 CMD ["python", "/app/server.py", "--check"]
CMD ["python", "/app/server.py"]
