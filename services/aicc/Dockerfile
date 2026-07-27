FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY aicc ./aicc
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN useradd --create-home --uid 10001 appuser \
    && chmod 755 /usr/local/bin/docker-entrypoint.sh

EXPOSE 8100

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "aicc.api:app", "--host", "0.0.0.0", "--port", "8100"]
