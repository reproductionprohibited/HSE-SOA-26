import asyncio
import logging
import threading
from collections.abc import Callable

from confluent_kafka import KafkaError, KafkaException, Message, Producer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
from confluent_kafka.schema_registry.error import SchemaRegistryError
from confluent_kafka.serialization import MessageField, SerializationContext, SerializationError, StringSerializer
from tenacity import AsyncRetrying, RetryCallState, retry_if_exception_type, stop_after_attempt, wait_random_exponential

from app.config import Settings
from app.schemas import MovieEvent

log = logging.getLogger("producer")


class EventValidationError(Exception):
    """Событие не прошло сериализацию по Avro-схеме из Schema Registry."""


class PublishError(Exception):
    """Событие не удалось опубликовать после всех попыток."""


class EventPublisher:
    """Публикация MovieEvent в Kafka: Avro по схеме из Registry, ключ user_id, acks=all, retry, логирование.

    librdkafka работает в своём потоке; delivery report приходит в отдельный poll-поток и пробрасывается
    в asyncio через call_soon_threadsafe.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._topic = settings.topic
        registry = SchemaRegistryClient({"url": settings.schema_registry_url})
        # Схему регистрирует только kafka-init; продюсер берёт последнюю зарегистрированную версию.
        self._value_serializer = AvroSerializer(
            registry,
            schema_str=None,
            conf={"auto.register.schemas": False, "use.latest.version": True},
        )
        self._key_serializer = StringSerializer("utf_8")
        self._producer = Producer(
            {
                "bootstrap.servers": settings.kafka_bootstrap_servers,
                "client.id": "movie-service",
                "acks": "all",
                "enable.idempotence": True,
                # Встроенный retry librdkafka с экспоненциальным backoff между попытками
                "retries": 10,
                "retry.backoff.ms": 100,
                "retry.backoff.max.ms": 2000,
                "delivery.timeout.ms": settings.delivery_timeout_ms,
                "linger.ms": 5,
            }
        )
        self._stop = threading.Event()
        self._poller = threading.Thread(target=self._poll_loop, name="kafka-poll", daemon=True)
        self._poller.start()

    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            self._producer.poll(0.1)

    def close(self, timeout: float = 10.0) -> None:
        remaining = self._producer.flush(timeout)
        self._stop.set()
        self._poller.join(timeout=1)
        if remaining:
            log.error("producer closed with undelivered messages", extra={"undelivered": remaining})

    def check_connection(self, timeout: float = 3.0) -> None:
        self._producer.list_topics(self._topic, timeout=timeout)

    def serialize(self, event: MovieEvent) -> tuple[bytes, bytes]:
        """Второй слой валидации: сериализация по Avro-схеме. Возвращает (key, value)."""
        ctx = SerializationContext(self._topic, MessageField.VALUE)
        try:
            value = self._value_serializer(event.to_avro(), ctx)
        except SchemaRegistryError:
            raise
        except (SerializationError, ValueError, TypeError) as exc:
            raise EventValidationError(str(exc)) from exc
        key = self._key_serializer(event.user_id, SerializationContext(self._topic, MessageField.KEY))
        assert value is not None and key is not None
        return key, value

    def _produce(self, event: MovieEvent, key: bytes, value: bytes, on_delivery: Callable[[KafkaError | None, Message], None]) -> None:
        while True:
            try:
                self._producer.produce(self._topic, key=key, value=value, on_delivery=on_delivery)
                return
            except BufferError:
                # Локальная очередь librdkafka заполнена — ждём, пока часть сообщений уйдёт
                self._producer.poll(0.5)

    @staticmethod
    def _log_delivered(event: MovieEvent, msg: Message) -> None:
        log.info(
            "event published",
            extra={
                "event_id": str(event.event_id),
                "event_type": event.event_type.value,
                "timestamp": event.timestamp.isoformat(),
                "partition": msg.partition(),
                "offset": msg.offset(),
            },
        )

    async def _publish_once(self, event: MovieEvent, key: bytes, value: bytes) -> Message:
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[Message] = loop.create_future()

        def on_delivery(err: KafkaError | None, msg: Message) -> None:
            def resolve() -> None:
                if fut.done():
                    return
                if err is not None:
                    fut.set_exception(KafkaException(err))
                else:
                    fut.set_result(msg)

            loop.call_soon_threadsafe(resolve)

        self._produce(event, key, value, on_delivery)
        return await fut

    async def publish(self, event: MovieEvent) -> Message:
        """Публикует событие и ждёт подтверждения брокера (acks=all).

        Поверх ретраев librdkafka — прикладной retry с exponential backoff + jitter.
        """
        key, value = self.serialize(event)

        def before_sleep(state: RetryCallState) -> None:
            exc = state.outcome.exception() if state.outcome else None
            log.warning(
                "publish failed, retrying",
                extra={
                    "event_id": str(event.event_id),
                    "attempt": state.attempt_number,
                    "sleep_s": round(state.upcoming_sleep, 3),
                    "error": str(exc),
                },
            )

        try:
            async for attempt in AsyncRetrying(
                retry=retry_if_exception_type(KafkaException),
                stop=stop_after_attempt(self._settings.publish_max_attempts),
                wait=wait_random_exponential(
                    multiplier=self._settings.publish_backoff_initial_s, max=self._settings.publish_backoff_max_s
                ),
                before_sleep=before_sleep,
                reraise=True,
            ):
                with attempt:
                    msg = await self._publish_once(event, key, value)
        except KafkaException as exc:
            log.error(
                "publish failed, giving up",
                extra={"event_id": str(event.event_id), "attempts": self._settings.publish_max_attempts, "error": str(exc)},
            )
            raise PublishError(str(exc)) from exc

        self._log_delivered(event, msg)
        return msg

    def publish_nowait(self, event: MovieEvent) -> None:
        """Публикация без ожидания подтверждения — для массового backfill генератора.

        Доставку подтверждает тот же delivery report (acks=all), ретраи — встроенные в librdkafka.
        """
        key, value = self.serialize(event)

        def on_delivery(err: KafkaError | None, msg: Message) -> None:
            if err is not None:
                log.error("publish failed", extra={"event_id": str(event.event_id), "error": str(err)})
            else:
                self._log_delivered(event, msg)

        self._produce(event, key, value, on_delivery)

    def flush(self, timeout: float = 60.0) -> int:
        return self._producer.flush(timeout)
