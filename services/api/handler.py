import json
import os
import uuid
import base64
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, Any, Optional
from urllib.parse import parse_qs

import boto3
from botocore.config import Config as BotocoreConfig
from boto3.dynamodb.conditions import Key


class Config:
    TABLE_NAME = os.getenv("TABLE_NAME", "taskflow-dev-tasks")
    BUCKET_NAME = os.getenv("BUCKET_NAME")
    AWS_REGION = os.getenv("AWS_REGION", "eu-central-1")
    SQS_QUEUE_URL = os.getenv("SQS_QUEUE_URL")
    STAGE = os.getenv("STAGE", "dev")


class AWSClients:
    def __init__(self):
        self.dynamo = boto3.resource("dynamodb")
        self.table = self.dynamo.Table(Config.TABLE_NAME)
        self.s3 = boto3.client(
            "s3",
            region_name=Config.AWS_REGION,
            config=BotocoreConfig(s3={"addressing_style": "virtual"})
        )
        self.sqs = boto3.client("sqs", region_name=Config.AWS_REGION)


aws_clients = AWSClients()

class RequestHandler:
    def __init__(self, event: Dict[str, Any]):
        self.event = event
        self.http = event.get("requestContext", {}).get("http", {})
        self.method = self.http.get("method", "").upper()
        self.raw_path = event.get("rawPath", "").lower()
        self.claims = self._extract_claims()

    def _extract_claims(self) -> Dict[str, Any]:
        return (
            self.event.get("requestContext", {})
            .get("authorizer", {})
            .get("jwt", {})
            .get("claims", {})
        )

    def _get_user_sub(self) -> Optional[str]:
        return self.claims.get("sub")

    def _require_auth(self) -> str:
        sub = self._get_user_sub()
        if not sub:
            raise UnauthorizedError("Missing user sub")
        return sub

    def _get_task_id_from_path(self) -> Optional[str]:
        task_id = (self.event.get("pathParameters") or {}).get("id")
        if not task_id and "/tasks/" in self.raw_path:
            task_id = self.raw_path.rsplit("/", 1)[-1]
        return task_id

    def route(self) -> Dict[str, Any]:
        if self.raw_path.endswith("/health"):
            return HealthService().get_health()

        if self.raw_path.endswith("/me"):
            return UserService().get_user_info(self.claims)

        if self.raw_path.endswith("/tasks") and self.method == "POST":
            return TaskService().create_task(self.event)

        if self.raw_path.endswith("/files/presign") and self.method == "POST":
            return FileService().presign_upload(self.event)

        if self.raw_path.endswith("/files/download") and self.method == "POST":
            return FileService().presign_download(self.event)

        if self.raw_path.endswith("/tasks") and self.method == "GET":
            return TaskService().list_tasks(self.event)

        if self.method == "GET":
            task_id = self._get_task_id_from_path()
            if task_id:
                return TaskService().get_task(self.event, task_id)

        return ResponseBuilder.not_found()


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    try:
        return RequestHandler(event).route()
    except UnauthorizedError as e:
        return ResponseBuilder.unauthorized(str(e))
    except ValidationError as e:
        return ResponseBuilder.bad_request(str(e))
    except NotFoundError as e:
        return ResponseBuilder.not_found(str(e))
    except Exception as e:
        return ResponseBuilder.internal_error(str(e))

class TaskService:
    def __init__(self):
        self.table = aws_clients.table
        self.sqs = aws_clients.sqs

    def create_task(self, event: Dict[str, Any]) -> Dict[str, Any]:
        claims = RequestUtils.extract_claims(event)
        sub = RequestUtils.require_user_sub(claims)
        
        user_pk = f"tenant_default#{sub}"
        body = RequestUtils.parse_json_body(event)
        
        task_data = self._build_task_data(body, user_pk)
        
        try:
            self._create_task_item(task_data)
        except aws_clients.dynamo.meta.client.exceptions.ConditionalCheckFailedException:
            return self._handle_existing_task(user_pk, task_data["task_id"])
        
        self._enqueue_task(task_data)
        
        return ResponseBuilder.created({
            "task": {
                "task_id": task_data["task_id"],
                "status": "PENDING",
                "file_key": task_data["file_key"],
                "created_at": task_data["created_at"]
            }
        })

    def _build_task_data(self, body: Dict[str, Any], user_pk: str) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        return {
            "pk": user_pk,
            "sk": body.get("task_id") or str(uuid.uuid4()),
            "task_id": body.get("task_id") or str(uuid.uuid4()),
            "created_at": now.isoformat(),
            "status": "PENDING",
            "file_key": body.get("file_key", ""),
            "client_token": (body.get("client_token") or str(uuid.uuid4()))[:64],
            "ttl": int((now + timedelta(days=7)).timestamp()),
        }

    def _create_task_item(self, task_data: Dict[str, Any]) -> None:
        self.table.put_item(
            Item=task_data,
            ConditionExpression="attribute_not_exists(pk) AND attribute_not_exists(sk)"
        )

    def _handle_existing_task(self, user_pk: str, task_id: str) -> Dict[str, Any]:
        existing = self.table.get_item(Key={"pk": user_pk, "sk": task_id}).get("Item")
        if existing:
            return ResponseBuilder.ok({"task": existing, "idem": True})
        return ResponseBuilder.conflict("Task conflict")

    def _enqueue_task(self, task_data: Dict[str, Any]) -> None:
        if not Config.SQS_QUEUE_URL:
            return
        
        try:
            self.sqs.send_message(
                QueueUrl=Config.SQS_QUEUE_URL,
                MessageBody=json.dumps({
                    "task_id": task_data["task_id"],
                    "user_pk": task_data["pk"],
                    "file_key": task_data["file_key"]
                })
            )
        except Exception as e:
            print(f"Failed to enqueue task {task_data['task_id']}: {e}")

    def list_tasks(self, event: Dict[str, Any]) -> Dict[str, Any]:
        claims = RequestUtils.extract_claims(event)
        sub = RequestUtils.require_user_sub(claims)
        
        params = RequestUtils.parse_query_string(event)
        limit = self._parse_limit(params.get("limit", "10"))
        cursor = self._parse_cursor(params.get("cursor"))
        
        user_pk = f"tenant_default#{sub}"
        
        query_args = {
            "IndexName": "by_user_created",
            "KeyConditionExpression": Key("pk").eq(user_pk),
            "ScanIndexForward": False,
            "Limit": limit,
        }
        
        if cursor:
            query_args["ExclusiveStartKey"] = cursor
        
        resp = self.table.query(**query_args)
        
        return ResponseBuilder.ok({
            "items": resp.get("Items", []),
            "next_cursor": self._encode_cursor(resp.get("LastEvaluatedKey"))
        })

    def _parse_limit(self, limit_str: str) -> int:
        try:
            limit = int(limit_str)
            return max(1, min(limit, 50))
        except ValueError:
            return 10

    def _parse_cursor(self, cursor_raw: Optional[str]) -> Optional[Dict[str, Any]]:
        if not cursor_raw:
            return None
        try:
            return json.loads(base64.urlsafe_b64decode(cursor_raw.encode()).decode("utf-8"))
        except Exception:
            return None

    def _encode_cursor(self, last_key: Optional[Dict[str, Any]]) -> Optional[str]:
        if not last_key:
            return None
        return base64.urlsafe_b64encode(json.dumps(last_key).encode()).decode()

    def get_task(self, event: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        claims = RequestUtils.extract_claims(event)
        sub = RequestUtils.require_user_sub(claims)
        
        user_pk = f"tenant_default#{sub}"
        item = self.table.get_item(Key={"pk": user_pk, "sk": task_id}).get("Item")
        
        if not item:
            raise NotFoundError("Task not found")
        
        return ResponseBuilder.ok({"task": item})

class FileService:
    def __init__(self):
        self.s3 = aws_clients.s3

    def presign_upload(self, event: Dict[str, Any]) -> Dict[str, Any]:
        claims = RequestUtils.extract_claims(event)
        sub = RequestUtils.require_user_sub(claims)
        
        body = RequestUtils.parse_json_body(event)
        filename = body.get("filename", "file.bin")
        content_type = body.get("content_type", "application/octet-stream")
        
        key = f"uploads/{sub}/{uuid.uuid4()}-{filename}"
        
        url = self.s3.generate_presigned_url(
            ClientMethod="put_object",
            Params={"Bucket": Config.BUCKET_NAME, "Key": key, "ContentType": content_type},
            ExpiresIn=900,
            HttpMethod="PUT",
        )
        
        return ResponseBuilder.ok({
            "upload_url": url,
            "object_key": key,
            "content_type": content_type
        })

    def presign_download(self, event: Dict[str, Any]) -> Dict[str, Any]:
        claims = RequestUtils.extract_claims(event)
        sub = RequestUtils.require_user_sub(claims)
        
        body = RequestUtils.parse_json_body(event)
        file_key = body.get("file_key", "").strip()
        
        if not file_key:
            raise ValidationError("file_key required")
        
        self._validate_file_access(sub, file_key)
        
        url = self.s3.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": Config.BUCKET_NAME, "Key": file_key},
            ExpiresIn=900,
            HttpMethod="GET",
        )
        
        return ResponseBuilder.ok({"download_url": url})

    def _validate_file_access(self, sub: str, file_key: str) -> None:
        allowed_prefixes = [f"uploads/{sub}/", f"results/{sub}/"]
        if not any(file_key.startswith(p) for p in allowed_prefixes):
            raise ValidationError("Access denied to file")

class CustomError(Exception):
    pass


class UnauthorizedError(CustomError):
    pass


class ValidationError(CustomError):
    pass


class NotFoundError(CustomError):
    pass


class RequestUtils:
    @staticmethod
    def parse_query_string(event: Dict[str, Any]) -> Dict[str, str]:
        raw = event.get("rawQueryString", "").strip()
        if not raw:
            return {}
        return {k: v[0] for k, v in parse_qs(raw, keep_blank_values=True).items()}

    @staticmethod
    def extract_claims(event: Dict[str, Any]) -> Dict[str, Any]:
        return (
            event.get("requestContext", {})
            .get("authorizer", {})
            .get("jwt", {})
            .get("claims", {})
        )

    @staticmethod
    def require_user_sub(claims: Dict[str, Any]) -> str:
        sub = claims.get("sub")
        if not sub:
            raise UnauthorizedError("Missing user sub")
        return sub

    @staticmethod
    def parse_json_body(event: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return json.loads(event.get("body", "{}"))
        except Exception:
            return {}


class ResponseBuilder:
    @staticmethod
    def _build_response(body: Any, status: int = 200) -> Dict[str, Any]:
        def json_serializer(obj):
            if isinstance(obj, Decimal):
                return int(obj) if obj % 1 == 0 else float(obj)
            raise TypeError(f"Not JSON serializable: {type(obj)}")
        
        return {
            "statusCode": status,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(body, default=json_serializer),
        }

    @staticmethod
    def ok(body: Any) -> Dict[str, Any]:
        return ResponseBuilder._build_response(body, 200)

    @staticmethod
    def created(body: Any) -> Dict[str, Any]:
        return ResponseBuilder._build_response(body, 201)

    @staticmethod
    def bad_request(message: str) -> Dict[str, Any]:
        return ResponseBuilder._build_response({"error": message}, 400)

    @staticmethod
    def unauthorized(message: str) -> Dict[str, Any]:
        return ResponseBuilder._build_response({"error": message}, 401)

    @staticmethod
    def not_found(message: str = "Not found") -> Dict[str, Any]:
        return ResponseBuilder._build_response({"error": message}, 404)

    @staticmethod
    def conflict(message: str) -> Dict[str, Any]:
        return ResponseBuilder._build_response({"error": message}, 409)

    @staticmethod
    def internal_error(message: str) -> Dict[str, Any]:
        return ResponseBuilder._build_response({"error": message}, 500)


class HealthService:
    @staticmethod
    def get_health() -> Dict[str, Any]:
        return ResponseBuilder.ok({
            "ok": True,
            "stage": Config.STAGE,
            "region": Config.AWS_REGION
        })


class UserService:
    @staticmethod
    def get_user_info(claims: Dict[str, Any]) -> Dict[str, Any]:
        return ResponseBuilder.ok({
            "sub": claims.get("sub"),
            "email": claims.get("email") or claims.get("cognito:username"),
            "stage": Config.STAGE
        })
