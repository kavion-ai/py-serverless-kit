# AWS Secrets Manager compatible server, Python (standard library only).
# Build from aws/secretsmanager so the console page is included:
#   docker build -f python/Dockerfile -t pskit/secretsmanager:python .
FROM python:3.12-alpine

RUN addgroup -S -g 10001 app && adduser -S -u 10001 -G app -h /app app \
    && mkdir -p /data && chown app:app /data
WORKDIR /app
COPY python/server.py ui/index.html /app/

ENV SM_PORT=4584 SM_BIND=0.0.0.0 SM_DATA_DIR=/data PYTHONUNBUFFERED=1
USER app
VOLUME ["/data"]
EXPOSE 4584
HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 CMD ["python", "/app/server.py", "--check"]
CMD ["python", "/app/server.py"]
