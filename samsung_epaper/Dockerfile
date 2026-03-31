ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base-python:3.12-alpine3.19
FROM ${BUILD_FROM}

RUN apk add --no-cache \
    jpeg-dev \
    zlib-dev \
    freetype-dev \
    lcms2-dev \
    libwebp-dev \
    tiff-dev \
    openjpeg-dev \
    gcc \
    musl-dev

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY epaper_service/ ./epaper_service/

COPY run.sh /
RUN chmod +x /run.sh

CMD ["/run.sh"]
