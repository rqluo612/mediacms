# The base image is built by docker-compose-dev.yaml's migrations service.
ARG BASE_IMAGE=mediacms/mediacms-dev:latest
FROM ${BASE_IMAGE}
RUN /home/mediacms.io/bin/python -m pip install --no-cache-dir jieba==0.42.1
