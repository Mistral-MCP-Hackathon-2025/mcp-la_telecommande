import os
import time
import uuid
from typing import Any

from mistralai import Mistral
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PayloadSchemaType, PointStruct, VectorParams

mistral_api_key = os.getenv("MISTRAL_API_KEY")
mistral_model = "mistral-embed"

client = Mistral(api_key=mistral_api_key)


qdrant_url = os.getenv("QDRANT_URL")
qdrant_api_key = os.getenv("QDRANT_API_KEY")

qdrant_client = QdrantClient(
    url=qdrant_url,
    api_key=qdrant_api_key,
)

def embed_text(text: str) -> list[float]:
    response = client.embeddings.create(
        model=mistral_model,
        inputs=[text],
    )
    return response.data[0].embedding


def ensure_collections_exist():
    collections_config = {
        "ssh_stdout": {
            "description": "SSH stdout logs with semantic search",
            "indexes": {
                "vm_name": PayloadSchemaType.KEYWORD,
                "requested_by": PayloadSchemaType.KEYWORD,
                "command": PayloadSchemaType.KEYWORD,
                "job_id": PayloadSchemaType.KEYWORD,
                "timestamp": PayloadSchemaType.FLOAT,
                "return_code": PayloadSchemaType.INTEGER,
            },
        },
        "ssh_commands": {
            "description": "SSH commands executed with metadata",
            "indexes": {
                "vm_name": PayloadSchemaType.KEYWORD,
                "requested_by": PayloadSchemaType.KEYWORD,
                "command": PayloadSchemaType.KEYWORD,
                "job_id": PayloadSchemaType.KEYWORD,
                "timestamp": PayloadSchemaType.FLOAT,
                "return_code": PayloadSchemaType.INTEGER,
            },
        },
        "ssh_stderr": {
            "description": "SSH stderr outputs",
            "indexes": {
                "vm_name": PayloadSchemaType.KEYWORD,
                "requested_by": PayloadSchemaType.KEYWORD,
                "command": PayloadSchemaType.KEYWORD,
                "job_id": PayloadSchemaType.KEYWORD,
                "timestamp": PayloadSchemaType.FLOAT,
                "return_code": PayloadSchemaType.INTEGER,
            },
        },
    }

    for collection_name, config in collections_config.items():
        # Créer la collection si elle n'existe pas
        if not qdrant_client.collection_exists(collection_name):
            print(f"Creating collection: {collection_name}")
            qdrant_client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
            )

        # Créer les index pour tous les champs de filtrage
        for field_name, field_type in config["indexes"].items():
            try:
                print(f"Creating index for {collection_name}.{field_name}")
                qdrant_client.create_payload_index(
                    collection_name=collection_name,
                    field_name=field_name,
                    field_schema=field_type,
                )
            except Exception as e:
                # L'index existe probablement déjà, on continue
                if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                    print(f"Index {collection_name}.{field_name} already exists")
                else:
                    print(
                        f"Warning: Could not create index {collection_name}.{field_name}: {e}"
                    )


def log_ssh_operation(
    job_id: str,
    vm_name: str,
    command: str,
    result: dict[str, Any],
    requested_by: str | None = None,
):
    ensure_collections_exist()
    timestamp = time.time()

    # Log the command itself
    command_embedding = embed_text(f"COMMAND: {command}")
    qdrant_client.upsert(
        collection_name="ssh_commands",
        points=[
            PointStruct(
                id=str(uuid.uuid4()),
                vector=command_embedding,
                payload={
                    "job_id": job_id,
                    "vm_name": vm_name,
                    "requested_by": requested_by or "",
                    "command": command,
                    "timestamp": timestamp,
                    "return_code": result["return_code"],
                },
            )
        ],
    )

    # Log stdout lines
    stdout = result.get("stdout", "")
    # check stdout size is less than the embedding model limit (8192 tokens ~ 6000 words ~ 30000 chars)
    if len(stdout) > 30000:
        stdout = stdout[:30000]

    if stdout:
        stdout_embedding = embed_text(f"STDOUT: {stdout}")
        qdrant_client.upsert(
            collection_name="ssh_stdout",
            points=[
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=stdout_embedding,
                    payload={
                        "job_id": job_id,
                        "vm_name": vm_name,
                        "requested_by": requested_by or "",
                        "command": command,
                        "timestamp": timestamp,
                        "stdout": stdout,
                        "return_code": result["return_code"],
                    },
                )
            ],
        )

    # Log stderr lines (errors)
    error = result.get("stderr") or ""
    if error and len(error) > 30000:
        error = error[:30000]

    if error:
        stderr_embedding = embed_text(f"ERROR: {error} ")
        qdrant_client.upsert(
            collection_name="ssh_stderr",
            points=[
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=stderr_embedding,
                    payload={
                        "job_id": job_id,
                        "vm_name": vm_name,
                        "requested_by": requested_by or "",
                        "command": command,
                        "timestamp": timestamp,
                        "stderr": error,
                        "return_code": result["return_code"],
                    },
                )
            ],
        )
