FROM python:3.11-slim

WORKDIR /app

# Pythonの標準出力バッファリングを完全に無効化（Docker環境でログを即時表示するために必須）
ENV PYTHONUNBUFFERED=1

# No external pip dependencies are strictly required since we only use standard libraries (asyncio, ssl, zlib, json)
# If dependencies surface later, we can uncomment this:
# COPY requirements.txt .
# RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Expose the configured JEPX MockServer port
EXPOSE 8888

CMD ["python", "-u", "main.py"]
