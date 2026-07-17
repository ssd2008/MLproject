FROM python:3.12-slim

ARG REQUIREMENTS_FILE=requirements-ml.lock.txt
ARG TORCH_VERSION=2.7.1

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements*.txt ./
RUN architecture="$(dpkg --print-architecture)" \
    && if [ "$architecture" = "amd64" ]; then \
         pip install --no-cache-dir \
           --extra-index-url https://download.pytorch.org/whl/cpu \
           "torch==${TORCH_VERSION}+cpu"; \
       else \
         pip install --no-cache-dir "torch==${TORCH_VERSION}"; \
       fi \
    && pip install --no-cache-dir -r "${REQUIREMENTS_FILE}"

COPY . .
RUN mkdir -p /app/data/uploads

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
