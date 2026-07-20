FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/models/huggingface

WORKDIR /app

COPY evaluation/requirements.txt /tmp/evaluation-requirements.txt
RUN pip install --no-cache-dir -r /tmp/evaluation-requirements.txt

COPY evaluation /app/evaluation

CMD ["bash", "-lc", "python -m evaluation.prepare_dataset --questions 60 && python -m evaluation.run_benchmark --device cpu"]
