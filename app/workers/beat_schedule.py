from celery.schedules import crontab

# Celery Beat schedules configuration
BEAT_SCHEDULE = {
    "periodic-document-snapshots": {
        "task": "app.workers.tasks.periodic_snapshot_task",
        "schedule": 60.0,  # Runs every minute to backup outstanding modifications to MinIO/S3
    }
}
