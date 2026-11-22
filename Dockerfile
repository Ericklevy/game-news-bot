FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY gamebot ./gamebot
COPY config.yaml .
COPY docker-entrypoint.sh /usr/local/bin/
RUN useradd --create-home bot && mkdir -p data && chown bot data
# Começa como root só para ajustar a permissão de /app/data; o bot roda como "bot"
ENTRYPOINT ["docker-entrypoint.sh"]
