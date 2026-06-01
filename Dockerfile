FROM python:3.11-slim

# Non-root user for security
RUN groupadd -r vibetipp && useradd -r -g vibetipp vibetipp

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Data dir is a volume
RUN mkdir -p /data && chown vibetipp:vibetipp /data

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER vibetipp

ENV DATA_DIR=/data
ENV FLASK_APP=main.py
ENV PORT=8081

EXPOSE 8081

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://localhost:'+os.environ.get('PORT','8081')+'/health')"

CMD ["/entrypoint.sh"]
