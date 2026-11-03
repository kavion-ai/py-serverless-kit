# Amazon S3 compatible server, Python (standard library only).
# Build from aws/s3 so the console page is included:
#   docker build -f python/Dockerfile -t pskit/s3:python .
FROM python:3.12-alpine

RUN addgroup -S -g 10001 app && adduser -S -u 10001 -G app -h /app app \
    && mkdir -p /data && chown app:app /data
WORKDIR /app
COPY python/server.py ui/index.html /app/

ENV S3_PORT=9000 S3_BIND=0.0.0.0 S3_DATA_DIR=/data PYTHONUNBUFFERED=1
USER app
VOLUME ["/data"]
EXPOSE 9000
HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 CMD ["python", "/app/server.py", "--check"]
CMD ["python", "/app/server.py"]
