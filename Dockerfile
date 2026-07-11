FROM nanthakps/kpsmlx:heroku_v2

WORKDIR /usr/src/app

RUN chmod 777 /usr/src/app

RUN apt-get update && apt-get install -y nodejs npm

RUN pip3 install --upgrade setuptools pip
RUN pip3 install --use-pep517 pymediainfo pyaes

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

RUN pip3 install -U yt-dlp yt-dlp-ejs

COPY . .

CMD ["bash", "start.sh"]
