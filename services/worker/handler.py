import json
import os
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

import boto3
from botocore.config import Config as BotocoreConfig


class WorkerConfig:
    TABLE_NAME = os.getenv("TABLE_NAME", "taskflow-dev-tasks")
    BUCKET_NAME = os.getenv("BUCKET_NAME")
    AWS_REGION = os.getenv("AWS_REGION", "eu-central-1")


class AWSClients:
    def __init__(self):
        self.dynamo = boto3.resource("dynamodb", region_name=WorkerConfig.AWS_REGION)
        self.table = self.dynamo.Table(WorkerConfig.TABLE_NAME)
        self.s3 = boto3.client(
            "s3",
            region_name=WorkerConfig.AWS_REGION,
            config=BotocoreConfig(s3={"addressing_style": "virtual"})
        )


aws_clients = AWSClients()

class Logger:
    @staticmethod
    def info(message: str) -> None:
        print(f"[worker] {message}", flush=True)

    @staticmethod
    def error(message: str) -> None:
        print(f"[worker] ERROR: {message}", flush=True)


class DateUtils:
    @staticmethod
    def now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

class TaskMessage:
    def __init__(self, raw_message: Dict[str, Any]):
        self.task_id = (raw_message.get("task_id") or "").strip()
        self.user_pk = (raw_message.get("user_pk") or "").strip()
        self.file_key = (raw_message.get("file_key") or "").strip()
        self.sub = self._extract_sub()

    def _extract_sub(self) -> str:
        return self.user_pk.split("#", 1)[-1] if "#" in self.user_pk else "unknown"

    def is_valid(self) -> bool:
        return bool(
            self.task_id and 
            self.user_pk and 
            self.file_key and 
            WorkerConfig.BUCKET_NAME
        )


class FileProcessor:
    def __init__(self):
        self.s3 = aws_clients.s3

    def download_file(self, file_key: str) -> bytes:
        Logger.info(f"Downloading s3://{WorkerConfig.BUCKET_NAME}/{file_key}")
        obj = self.s3.get_object(Bucket=WorkerConfig.BUCKET_NAME, Key=file_key)
        return obj["Body"].read()

    def calculate_stats(self, data: bytes) -> Dict[str, Any]:
        byte_count = len(data)
        line_count = self._count_lines(data)
        sha256_hash = hashlib.sha256(data).hexdigest()
        
        return {
            "byte_count": byte_count,
            "line_count": line_count,
            "sha256": sha256_hash,
        }

    def _count_lines(self, data: bytes) -> Optional[int]:
        try:
            return len(data.decode("utf-8", errors="ignore").splitlines())
        except Exception:
            return None

    def save_result(self, task_message: TaskMessage, stats: Dict[str, Any]) -> str:
        result_key = f"results/{task_message.sub}/{task_message.task_id}.json"
        result_payload = {
            "task_id": task_message.task_id,
            "file_key": task_message.file_key,
            "stats": stats,
            "generated_at": DateUtils.now_iso(),
        }
        
        self.s3.put_object(
            Bucket=WorkerConfig.BUCKET_NAME,
            Key=result_key,
            Body=json.dumps(result_payload, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json",
        )
        
        return result_key


class TaskRepository:
    def __init__(self):
        self.table = aws_clients.table

    def get_task(self, task_message: TaskMessage) -> Optional[Dict[str, Any]]:
        return self.table.get_item(
            Key={"pk": task_message.user_pk, "sk": task_message.task_id}
        ).get("Item")

    def is_task_already_processed(self, task: Dict[str, Any]) -> bool:
        return (
            task.get("result_key") is not None or 
            task.get("status") in ("DONE", "FAILED")
        )

    def mark_task_completed(self, task_message: TaskMessage, result_key: str, stats: Dict[str, Any]) -> None:
        self.table.update_item(
            Key={"pk": task_message.user_pk, "sk": task_message.task_id},
            UpdateExpression="SET #s=:s, processed_at=:ts, result_key=:rk, stats=:st",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":s": "DONE",
                ":ts": DateUtils.now_iso(),
                ":rk": result_key,
                ":st": stats,
            },
        )

    def mark_task_failed(self, task_message: TaskMessage, error: str) -> None:
        try:
            self.table.update_item(
                Key={"pk": task_message.user_pk, "sk": task_message.task_id},
                UpdateExpression="SET #s=:s, processed_at=:ts, error=:err",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={
                    ":s": "FAILED",
                    ":ts": DateUtils.now_iso(),
                    ":err": error[:2000],
                },
            )
        except Exception as e:
            Logger.error(f"Failed to mark task as failed: {e}")


class TaskProcessor:
    def __init__(self):
        self.file_processor = FileProcessor()
        self.task_repository = TaskRepository()

    def process_task(self, task_message: TaskMessage) -> None:
        if not task_message.is_valid():
            raise ValueError("Invalid task message: missing required fields")

        task = self.task_repository.get_task(task_message)
        if not task:
            Logger.info(f"Task not found: {task_message.user_pk}#{task_message.task_id} - skipping")
            return

        if self.task_repository.is_task_already_processed(task):
            Logger.info(f"Task {task_message.task_id} already processed (status={task.get('status')}) - skipping")
            return

        data = self.file_processor.download_file(task_message.file_key)
        stats = self.file_processor.calculate_stats(data)
        result_key = self.file_processor.save_result(task_message, stats)
        
        self.task_repository.mark_task_completed(task_message, result_key, stats)
        Logger.info(f"Task {task_message.task_id} completed -> {result_key}")


class WorkerHandler:
    def __init__(self):
        self.task_processor = TaskProcessor()

    def handle_records(self, records: List[Dict[str, Any]]) -> None:
        for record in records:
            self._process_record(record)

    def _process_record(self, record: Dict[str, Any]) -> None:
        body = record.get("body", "{}")
        try:
            message_data = json.loads(body)
            task_message = TaskMessage(message_data)
            self.task_processor.process_task(task_message)
        except Exception as e:
            Logger.error(f"Processing failed: {e}")
            try:
                message_data = json.loads(body)
                task_message = TaskMessage(message_data)
                if task_message.task_id and task_message.user_pk:
                    TaskRepository().mark_task_failed(task_message, str(e))
            except Exception:
                Logger.error("Failed to mark task as failed")


def handler(event: Dict[str, Any], context: Any) -> Dict[str, bool]:
    worker_handler = WorkerHandler()
    worker_handler.handle_records(event.get("Records", []))
    return {"ok": True}
