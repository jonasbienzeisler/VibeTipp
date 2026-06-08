FROM python:3.11-slim

# Pin UIDs so volume ownership is stable across base-image updates
RUN groupadd -r -g 1001 vibetipp && useradd -r -u 1001 -g vibetipp vibetipp

# gosu for clean privilege drop in entrypoint (works in both Docker and rootless Podman)
RUN apt-get update && apt-get install -y --no-install-recommends gosu && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV DATA_DIR=/data
ENV FLASK_APP=main.py
ENV PORT=8081

EXPOSE 8081

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://localhost:'+os.environ.get('PORT','8081')+'/health')"

CMD ["/entrypoint.sh"]
