FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libgl1 libsm6 libxext6 libxrender1 ffmpeg tesseract-ocr && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Specialist weights are downloaded reproducibly at image build time. If the build
# environment intentionally has no network access, run scripts/bootstrap_models.py
# on the target server instead.
RUN python scripts/bootstrap_models.py --all
RUN rm -f traffic.db && find . -type d -name '__pycache__' -prune -exec rm -rf {} +
EXPOSE 8000
CMD ["uvicorn","api.server:app","--host","0.0.0.0","--port","8000","--workers","2"]
