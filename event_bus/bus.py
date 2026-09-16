import queue
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class BusEvent:
    topic: str
    payload: Dict


class InMemoryEventBus:
    """
    Small publish/subscribe bus used as a local stand-in for Redis Streams/Kafka.
    The interface keeps ingestion decoupled from downstream dashboard and alerting
    consumers, which is the production architecture V8 needs to demonstrate.
    """

    def __init__(self):
        self._topics: Dict[str, "queue.Queue[BusEvent]"] = {}

    def publish(self, topic: str, payload: Dict) -> None:
        self._topics.setdefault(topic, queue.Queue()).put(BusEvent(topic, payload))

    def drain(self, topic: str) -> List[BusEvent]:
        topic_queue = self._topics.setdefault(topic, queue.Queue())
        events: List[BusEvent] = []
        while True:
            try:
                events.append(topic_queue.get_nowait())
            except queue.Empty:
                break
        return events
