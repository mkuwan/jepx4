FROM python:3.9-slim

WORKDIR /app

COPY src/ .

# Generate self-signed certificate for TLS support
RUN apt-get update && apt-get install -y openssl && \
    openssl req -new -newkey rsa:2048 -days 365 -nodes -x509 -keyout key.pem -out cert.pem -subj "/CN=mockserver"

# Expose the TCP port
EXPOSE 8888

CMD ["python", "main.py"]
