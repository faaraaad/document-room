import logging
import time
import aioboto3
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.models.document import DocumentSnapshot

logger = logging.getLogger(__name__)


class SnapshotService:
    def __init__(self):
        self.session = aioboto3.Session()

    def _get_s3_client(self):
        """
        Creates an asynchronous aioboto3 S3 client using settings parameters.
        """
        return self.session.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name="us-east-1"  # Default region for compatibility
        )

    async def save_snapshot(self, db: AsyncSession, document_id: int, content: str, revision: int) -> str:
        """
        Saves a text document snapshot to S3/MinIO and records the metadata in the DB.
        """
        s3_key = f"snapshots/doc_{document_id}/rev_{revision}_{int(time.time())}.txt"
        
        async with self._get_s3_client() as s3:
            # 1. Ensure target bucket exists
            try:
                await s3.head_bucket(Bucket=settings.S3_BUCKET_NAME)
            except Exception:
                logger.info(f"S3 Bucket '{settings.S3_BUCKET_NAME}' not found. Creating bucket...")
                try:
                    await s3.create_bucket(Bucket=settings.S3_BUCKET_NAME)
                except Exception as e:
                    # Ignore bucket already exists error
                    logger.debug(f"Bucket creation info/warning: {e}")

            # 2. Upload snapshot content
            await s3.put_object(
                Bucket=settings.S3_BUCKET_NAME,
                Key=s3_key,
                Body=content.encode("utf-8"),
                ContentType="text/plain"
            )
            logger.info(f"Saved snapshot to S3: Bucket={settings.S3_BUCKET_NAME}, Key={s3_key}")

        # 3. Create DB metadata snapshot record
        snapshot = DocumentSnapshot(
            document_id=document_id,
            s3_key=s3_key,
            revision=revision
        )
        db.add(snapshot)
        await db.flush()  # Flushes change to database without committing yet (managed by caller session)
        
        return s3_key


snapshot_service = SnapshotService()

# PEP8 clean audit update 5
