# Fija la version exacta (ej. 3.14.9) cuando verifiquen que el tag existe en Docker Hub
ARG PYTHON_VERSION=3.14
FROM python:${PYTHON_VERSION}-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
RUN useradd --create-home --uid 10001 appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY rutina_ml.py .

USER appuser
CMD ["python", "rutina_ml.py"]
