FROM alpine:latest

RUN apk add python

WORKDIR /app

COPY sample.py .

EXPOSE 9001
CMD ["python", "/app/sample.py"]
