FROM nanthakps/kpsmlx:heroku_v2

WORKDIR /usr/src/app

# Koyeb routes HTTP traffic to the configured service port.
# The upstream bot starts Gunicorn using the PORT environment variable.
ENV PORT=8000
ENV PYTHONUNBUFFERED=1

RUN chmod 777 /usr/src/app \
    && apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --upgrade setuptools pip
RUN pip3 install --use-pep517 pymediainfo pyaes

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt
RUN pip3 install -U yt-dlp yt-dlp-ejs

COPY . .

# Mount a persistent Koyeb volume here if you need downloads to survive
# instance replacement/redeployment. Without a mounted volume this is ephemeral.
RUN mkdir -p /usr/src/app/downloads
VOLUME ["/usr/src/app/downloads"]

CMD ["bash", "start.sh"]
