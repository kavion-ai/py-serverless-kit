# Amazon SES compatible server, C++17 + OpenSSL.
# Build from aws/ses so the console (ui/) is included:
#   docker build -f cpp/Dockerfile -t pskit/ses:cpp .
FROM alpine:3.20 AS build
RUN apk add --no-cache g++ make openssl-dev
WORKDIR /src
COPY cpp/Makefile /src/
COPY cpp/src /src/src/
RUN make -j"$(nproc)" BUILD=/out

FROM alpine:3.20
RUN apk add --no-cache libstdc++ openssl \
    && addgroup -S -g 10001 app && adduser -S -u 10001 -G app -h /app app \
    && mkdir -p /data && chown app:app /data
WORKDIR /app
COPY --from=build /out/ses-server /app/ses-server
COPY ui /app/ui/

ENV SES_PORT=4579 SES_SMTP_PORT=2587 SES_BIND=0.0.0.0 SES_DATA_DIR=/data
USER app
VOLUME ["/data"]
EXPOSE 4579 2587
HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 CMD ["/app/ses-server", "--check"]
CMD ["/app/ses-server"]
