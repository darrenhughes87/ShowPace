FROM python:3.12-alpine
WORKDIR /app
COPY server.py index.html template.csv qrcode.min.js ./
# Shows and logins live in /data, owned by the user ShowPace runs as, so it can always save
RUN mkdir /data && chown 65534:65534 /data
USER 65534
ENV SHOWPACE_DATA=/data
VOLUME /data
EXPOSE 4320
CMD ["python3", "-u", "server.py"]
