FROM python:3.10-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV DEBIAN_FRONTEND=noninteractive
ENV DISABLE_MODEL_SOURCE_CHECK=True

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    libglib2.0-0 \
    libgl1 \
    libgomp1 \
    libxext6 \
    libsm6 \
    libxrender1 \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --upgrade pip setuptools wheel

RUN pip install --no-cache-dir \
    fastapi \
    uvicorn[standard] \
    python-multipart \
    paddlepaddle \
    "paddlex[ocr]==3.5.0" \
    "paddleocr==3.5.0" \
    safetensors \
    pillow \
    pymupdf \
    opencv-python-headless

COPY . /app

EXPOSE 8010

CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8010"]