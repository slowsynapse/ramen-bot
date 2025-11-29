FROM bitnami/python:3.6-prod



RUN apt-get update -y
RUN apt-get -y install build-essential sudo postgresql libpq-dev postgresql-client curl \
    postgresql-client-common libncurses5-dev libjpeg-dev zlib1g-dev git wget redis-server && \
    wget -O /usr/local/bin/wait-for-it.sh https://raw.githubusercontent.com/vishnubob/wait-for-it/8ed92e8cab83cfed76ff012ed4a36cef74b28096/wait-for-it.sh && \
    chmod +x /usr/local/bin/wait-for-it.sh

RUN pip install --upgrade pip
COPY ./requirements.txt requirements.txt

RUN rm -r /opt/bitnami/python/lib/python3.6/site-packages/setuptools*
RUN pip install --no-cache-dir -U setuptools
RUN pip install --no-cache-dir -r requirements.txt

RUN mkdir /temp && cd /temp
RUN curl -sL https://deb.nodesource.com/setup_10.x | sudo -E bash -
RUN apt-get install -y nodejs npm

RUN git clone https://github.com/Bitcoin-com/slp-sdk /temp/slp-sdk
RUN cd /temp/slp-sdk && git checkout 03b67413e4eedc26d01441c26f6ca7c3d0fbe89a
RUN cd /temp/slp-sdk && npm install && npm install slpjs

COPY . /code
WORKDIR /code

ENTRYPOINT [ "wait-for-it.sh", "postgres:5432", "--", "sh", "entrypoint.sh" ]
CMD [ "wait-for-it.sh", "postgres:5432", "--", "supervisord", "-c", "/code/supervisord.conf", "--nodaemon" ]
