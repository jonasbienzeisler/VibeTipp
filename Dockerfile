FROM python:3.11-slim

# Non-root user for security
RUN groupadd -r vibetipp && useradd -r -g vibetipp vibetipp

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# gosu for clean privilege drop in entrypoint
RUN apt-get update && apt-get install -y --no-install-recommends gosu && rm -rf /var/lib/apt/lists/*

COPY . .

# Create data dir; entrypoint will chown it at runtime to handle existing volumes
RUN mkdir -p /data

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Stay as root so entrypoint can fix volume ownership, then drops to vibetipp via gosu

ENV DATA_DIR=/data
ENV FLASK_APP=main.py
ENV PORT=8081

EXPOSE 8081

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://localhost:'+os.environ.get('PORT','8081')+'/health')"

CMD ["/entrypoint.sh"]
