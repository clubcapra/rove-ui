FROM python:3.12-slim

WORKDIR /app

ENV PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .
COPY proto_gen/ proto_gen/

EXPOSE 8080

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
