# AWS Secrets Manager compatible server, Node.js (no npm dependencies).
# Build from aws/secretsmanager so the console page is included:
#   docker build -f nodejs/Dockerfile -t pskit/secretsmanager:nodejs .
FROM node:22-alpine

RUN addgroup -S -g 10001 app && adduser -S -u 10001 -G app -h /app app \
    && mkdir -p /data && chown app:app /data
WORKDIR /app
COPY nodejs/server.js nodejs/package.json ui/index.html /app/

ENV SM_PORT=4584 SM_BIND=0.0.0.0 SM_DATA_DIR=/data NODE_ENV=production
USER app
VOLUME ["/data"]
EXPOSE 4584
HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 CMD ["node", "/app/server.js", "--check"]
CMD ["node", "/app/server.js"]
