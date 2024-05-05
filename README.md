# CollabStream: Real-Time Document Room API with Operational Transform & SSE AI Stream

**CollabStream** is a production-ready, horizontally scalable real-time collaborative document platform. It supports concurrent editing via a custom **Operational Transform (OT) conflict resolution engine**, tracks online users via a **Redis presence system**, streams debounced real-time document critique using **Celery & Server-Sent Events (SSE)**, backs up periodic versions to **S3-compatible storage**, and provides professional-grade observability with **Prometheus** metrics and **OpenTelemetry** trace exports.

---

## 1. System Architecture & Flow

```mermaid
graph TD
    ClientA[WS Collaborator A] ---|WS WebSocket| Nginx[Nginx Reverse Proxy]
    ClientB[WS Collaborator B] ---|WS WebSocket| Nginx

    Nginx ---|WS Load Balancer| FastAPI1[FastAPI Server Instance A]
    Nginx ---|WS Load Balancer| FastAPI2[FastAPI Server Instance B]

    FastAPI1 ---|PubSub Channel| RedisBroker[(Redis Broker and Presence)]
    FastAPI2 ---|PubSub Channel| RedisBroker

    FastAPI1 & FastAPI2 -->|DB Write| Postgres[(Postgres Database)]

    FastAPI1 & FastAPI2 -->|Trigger AI Task| CeleryWorker[Celery Tasks Worker]
    CeleryWorker -->|AI Stream Chunks| RedisStream[(Redis Stream)]

    ClientA -->|SSE Analysis| Nginx
    Nginx -->|SSE Proxy| FastAPI1
    FastAPI1 -->|Tail Stream| RedisStream

    CeleryBeat[Celery Scheduler] -->|Trigger Snapshot| CeleryWorker
    CeleryWorker -->|Document Snapshots| MinIO