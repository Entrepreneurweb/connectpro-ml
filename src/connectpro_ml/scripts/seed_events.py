"""
Seed — lit test_events.json et publie chaque event sur RabbitMQ.
Usage : python -m connectpro_ml.scripts.seed_events
"""

import asyncio
import json
import logging
import os

import aio_pika

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
logger = logging.getLogger(__name__)

RABBITMQ_URL = "amqp://guest:guest@localhost:5672/"
EXCHANGE_NAME = "marketplace.events"

# Chemin vers le fichier JSON (relatif à ce fichier)
JSON_FILE = os.path.join(os.path.dirname(__file__), "test_events.json")


async def main():
    # Lire le JSON
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    events = data["events"]
    logger.info("📂 %d events chargés depuis %s", len(events), JSON_FILE)

    # Connexion RabbitMQ
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    async with connection:
        channel = await connection.channel()
        exchange = await channel.declare_exchange(
            EXCHANGE_NAME, aio_pika.ExchangeType.TOPIC, durable=True
        )

        count = 0
        for event in events:
            # Ignorer les entrées qui sont juste des commentaires
            if "routing_key" not in event:
                continue

            routing_key = event["routing_key"]
            payload = json.dumps(event["payload"]).encode("utf-8")

            await exchange.publish(
                aio_pika.Message(body=payload, content_type="application/json"),
                routing_key=routing_key,
            )
            count += 1
            logger.info("✉️  [%d] %s", count, routing_key)
            await asyncio.sleep(2)

        logger.info("✅ Seed terminé — %d events envoyés", count)


if __name__ == "__main__":
    asyncio.run(main())