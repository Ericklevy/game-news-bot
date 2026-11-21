FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY gamebot ./gamebot
COPY config.yaml .
RUN useradd --create-home bot && mkdir -p data && chown bot data
USER bot
ENTRYPOINT ["python", "-m", "gamebot"]
