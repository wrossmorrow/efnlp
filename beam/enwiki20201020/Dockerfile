FROM apache/beam_python3.10_sdk

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates curl cmake g++ nlohmann-json3-dev \
        python3-dev python3-distutils \
    && rm -rf /var/lib/apt/lists/* \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3 10

COPY charcount.py 
COPY path/to/myfile ./
