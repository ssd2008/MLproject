# Retrieval benchmark

Этот каталог содержит воспроизводимый retrieval-эксперимент и зафиксированное инженерное решение по основной поисковой конфигурации проекта.

**Основной режим Асси — Dense retrieval на `intfloat/multilingual-e5-large`.**

BM25 сохранён только как лексический baseline для сравнения. `BAAI/bge-reranker-v2-m3` сохранён как экспериментальная опция, но отключён по умолчанию, поскольку в проведённом эксперименте он ухудшил MRR и точность первого результата и резко увеличил задержку.

Подробная интерпретация: [RESULTS.md](RESULTS.md).

## Что сравнивалось

1. **BM25** — классическая лексическая модель ранжирования.
2. **Dense retrieval** — поиск по нормализованным embedding-векторам.
3. **Dense retrieval + cross-encoder reranker** — dense retrieval формирует кандидатов, после чего cross-encoder переупорядочивает их.

Полное сравнение было выполнено на одном наборе данных и одном CPU-окружении. Фактические результаты сохранены в `evaluation/results/`.

## Тестовый набор

`prepare_dataset.py` детерминированно строит набор из **3 медицинских материалов, 18 gold-фрагментов и 60 вопросов** на основе MedQuAD/NIDDK:

- Acromegaly;
- Celiac Disease;
- Crohn's Disease.

В репозитории лежат компактные XML-fixtures, поэтому стандартная подготовка набора не зависит от доступности GitHub. Из 60 вопросов 15 являются исходными MedQuAD-вопросами, а 45 — детерминированными шаблонными переформулировками. Для каждого вопроса сохраняется `gold_chunk_ids`.

MedQuAD распространяется по лицензии CC BY 4.0. Исходные URL, закреплённый commit и путь fixture записываются в `evaluation/data/sources.json`.

Полные закреплённые XML можно повторно скачать командой:

```bash
python -m evaluation.prepare_dataset --questions 60 --refresh
```

В режиме `--refresh` используются повторные попытки, экспоненциальная задержка, fallback на GitHub Contents API, проверка XML и атомарная запись cache-файла.

## Метрики

- `Recall@5` — найден ли хотя бы один gold-фрагмент среди первых пяти результатов.
- `MRR` — среднее обратное место первого gold-фрагмента.
- `citation_accuracy` — входит ли первый найденный фрагмент в размеченный gold-набор. В документации эта метрика называется `Top-1 gold accuracy`, поскольку генеративная проверка цитаты здесь не выполняется.
- `latency` — время одного прогретого поискового запроса без загрузки моделей и построения индекса.

При `top_k=20` gold-фрагмент вне первых 20 результатов даёт нулевой вклад в MRR.

## Результат и выбранная конфигурация

| Конфигурация | Recall@5 | MRR | Top-1 gold accuracy | Latency p50 |
|---|---:|---:|---:|---:|
| BM25 | 0.733 | 0.410 | 18.3% | 0.0001 сек. |
| **Dense** | **0.983** | **0.865** | **78.3%** | **0.297 сек.** |
| Dense + reranker | 1.000 | 0.715 | 58.3% | 5.525 сек. |

Dense выбран как основной режим, потому что он дал лучший MRR и лучший первый результат при интерактивной задержке. Reranker добавил только одно попадание в top-5, но потерял 12 правильных первых результатов из 60 и увеличил медианную задержку примерно в 18.6 раза.

Это вывод только для текущего набора, chunking и CPU-окружения. Он не означает, что reranker-модель принципиально непригодна для других корпусов.

## Запуск Dense benchmark через Docker

```bash
docker compose -f evaluation/docker-compose.yml run --rm benchmark
```

Стандартная команда запускает только Dense retrieval. Она не загружает reranker-модель.

Результаты сохраняются в `evaluation/results/`.

## Повтор полного сравнения

Чтобы заново сравнить все три конфигурации:

```bash
docker compose -f evaluation/docker-compose.yml run --rm benchmark \
  bash -lc "python -m evaluation.prepare_dataset --questions 60 && \
  python -m evaluation.run_benchmark --device cpu --include-bm25 --with-reranker"
```

При таком запуске будет загружен optional reranker и текущие файлы в `evaluation/results/` будут перезаписаны.

## Локальный запуск без Docker

Нужен Python 3.11 и доступная для платформы версия PyTorch 2.4 или новее.

```bash
python3.11 -m venv .venv-benchmark
source .venv-benchmark/bin/activate
pip install -r evaluation/requirements.txt

python -m evaluation.prepare_dataset --questions 60
python -m evaluation.run_benchmark --device cpu
```

Полное сравнение локально:

```bash
python -m evaluation.run_benchmark \
  --device cpu \
  --include-bm25 \
  --with-reranker
```

На Apple Silicon можно отдельно проверить `--device mps`. Все сравниваемые конфигурации должны выполняться на одном устройстве.

## Выходные файлы

- `results/benchmark_results.md` — сгенерированная итоговая таблица;
- `results/benchmark_results.csv` — полные численные метрики;
- `results/per_question.jsonl` — rank, top-1 и latency для каждого вопроса;
- `results/run_metadata.json` — модели, параметры и сведения об окружении;
- [RESULTS.md](RESULTS.md) — человеческая интерпретация и принятое решение.

## Reranker в основном приложении

По умолчанию:

```dotenv
RERANKER_ENABLED=false
```

Чтобы разрешить экспериментальный reranking, установи:

```dotenv
RERANKER_ENABLED=true
```

и передай в запросе `/search` или `/answer`:

```json
{
  "use_reranker": true
}
```

Оба условия обязательны. При выключенном глобальном флаге приложение использует Dense retrieval и возвращает `rerank_score=null`.

## Проверка кода без скачивания моделей

```bash
python -m unittest discover -s evaluation/tests -v
python -m compileall -q evaluation
```

## Ограничения

Набор небольшой, англоязычный и содержит шаблонные переформулировки. Bundled fixtures являются компактной производной от исходных MedQuAD/NIDDK материалов. Один MedQuAD `Answer` используется как один gold-фрагмент, поэтому некоторые фрагменты длиннее production-чанков. Эксперимент оценивает retrieval и не является клинической валидацией медицинских ответов.
