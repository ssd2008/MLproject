from __future__ import annotations

import argparse
import asyncio

import httpx


async def main(base_url: str) -> None:
    async with httpx.AsyncClient(base_url=base_url, timeout=120) as client:
        health = await client.get("/health")
        health.raise_for_status()
        print("health:", health.json())

        created = await client.post(
            "/documents",
            json={
                "title": "Smoke test: hypertension",
                "source_type": "text",
                "raw_text": (
                    "Артериальная гипертензия — стойкое повышение артериального давления. "
                    "Для лечения применяют ингибиторы АПФ, БРА, диуретики, блокаторы "
                    "кальциевых каналов и бета-блокаторы."
                ),
                "specialty": "cardiology",
                "language": "ru",
            },
        )
        created.raise_for_status()
        document = created.json()
        print("document:", document)

        index = await client.post(f"/documents/{document['id']}/index", json={})
        index.raise_for_status()
        job_id = index.json()["job_id"]
        print("job:", index.json())

        for _ in range(120):
            job = (await client.get(f"/jobs/{job_id}")).json()
            if job["status"] in {"completed", "failed"}:
                print("job result:", job)
                break
            await asyncio.sleep(0.5)
        else:
            raise RuntimeError("Indexing job timed out")

        answer = await client.post(
            "/answer",
            json={
                "query": "Какие препараты применяют при артериальной гипертензии?",
                "top_k": 5,
                "candidate_k": 10,
                "max_context_chunks": 3,
            },
        )
        answer.raise_for_status()
        print("answer:", answer.json())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1")
    args = parser.parse_args()
    asyncio.run(main(args.base_url))
