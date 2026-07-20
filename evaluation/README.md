# Retrieval benchmark

Этот каталог запускает воспроизводимое сравнение трёх конфигураций поиска:

1. **BM25** — `Best Matching 25`, классическая лексическая модель ранжирования.
2. **Dense retrieval** — поиск по нормализованным embeddings модели `intfloat/multilingual-e5-large`.
3. **Dense retrieval + cross-encoder reranker** — dense-поиск формирует кандидатов, затем `BAAI/bge-reranker-v2-m3` переупорядочивает пары «вопрос — фрагмент».

Модели совпадают с текущей конфигурацией основного приложения.

## Тестовый набор

`prepare_dataset.py` детерминированно строит набор из **3 медицинских материалов и 60 вопросов** на основе MedQuAD:

- NIDDK: Acromegaly;
- NIDDK: Celiac Disease;
- NIDDK: Crohn's Disease.

Исходные XML-файлы закреплены на конкретном commit MedQuAD. Каждый `Answer` из MedQuAD считается размеченным фрагментом. Для исходных вопросов создаются шаблонные переформулировки; у каждой записи остаётся тот же `gold_chunk_ids`. Поле `provenance` показывает, является вопрос исходным или шаблонной переформулировкой.

MedQuAD распространяется по лицензии CC BY 4.0. Атрибуция и pinned URLs сохраняются в `evaluation/data/sources.json`.

## Метрики

- `Recall@5`: хотя бы один gold-фрагмент найден среди первых пяти результатов.
- `MRR`: `Mean Reciprocal Rank`, среднее обратное место первого gold-фрагмента.
- `citation_accuracy`: top-1 фрагмент, который система использовала бы как основную цитату, входит в размеченный gold-набор.
- `latency`: время одного прогретого поискового запроса. Загрузка моделей и построение индекса не входят в latency. В итоговой Markdown-таблице показывается p50, в CSV также записываются p95 и среднее.

`top_k` означает количество возвращаемых результатов: `top` — верхние результаты, `k` — их число. `candidate_k` означает число кандидатов, передаваемых reranker-модели.

## Рекомендуемый запуск через Docker

Это наиболее надёжный вариант для Intel macOS, где современные версии PyTorch могут не иметь нативных wheel-пакетов.

```bash
docker compose -f evaluation/docker-compose.yml run --rm benchmark
```

Первый запуск скачивает модели в Docker volume `benchmark_huggingface_cache`. Результаты сохраняются на хосте в `evaluation/results/`.

## Локальный запуск без Docker

Нужен Python 3.11 и доступная для вашей платформы версия PyTorch 2.4 или новее.

```bash
python3.11 -m venv .venv-benchmark
source .venv-benchmark/bin/activate
pip install -r evaluation/requirements.txt

python -m evaluation.prepare_dataset --questions 60
python -m evaluation.run_benchmark --device cpu
```

На Apple Silicon можно отдельно проверить `--device mps`. Для честного сравнения все три конфигурации в одном отчёте должны запускаться на одном устройстве.

## Выходные файлы

После успешного запуска появляются:

- `evaluation/results/benchmark_results.md` — итоговая таблица;
- `evaluation/results/benchmark_results.csv` — те же метрики плюс p95 и средняя latency;
- `evaluation/results/per_question.jsonl` — место gold-фрагмента и задержка для каждого вопроса;
- `evaluation/results/run_metadata.json` — модели, параметры, Python, PyTorch и сведения об устройстве.

В репозитории нет заранее заполненных чисел. Таблица создаётся только фактическим запуском моделей.

## Проверка кода без скачивания моделей

```bash
python -m unittest discover -s evaluation/tests -v
```

## Ограничения

Набор небольшой, англоязычный и содержит шаблонные переформулировки. Он подходит для контролируемого инженерного сравнения retriever-конфигураций, но не является клинической валидацией качества медицинских ответов. `citation_accuracy` здесь — строгая проверка попадания top-1 цитаты в gold-разметку, а не экспертная оценка полного сгенерированного ответа.
