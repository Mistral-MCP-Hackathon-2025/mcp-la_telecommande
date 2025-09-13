import os
import time
import uuid

from mistralai import Mistral

mistral_api_key = os.getenv("MISTRAL_API_KEY")
# print("MISTRAL_API_KEY:", mistral_api_key)
mistral_model = "mistral-embed"

client = Mistral(api_key=mistral_api_key)

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams,
)

qdrant_api_key = os.getenv("QDRANT_API_KEY")

qdrant_client = QdrantClient(
    url="https://43f7d188-39ab-49fd-a399-2f72552bc113.eu-central-1-0.aws.cloud.qdrant.io:6333",
    api_key=qdrant_api_key,
)

# print("QDRANT_API_KEY:", qdrant_api_key)
# print("MISTRAL_API_KEY:", mistral_api_key)

def embed_text(text: str) -> list[float]:
    response = client.embeddings.create(
        model=mistral_model,
        inputs=[text],
    )
    return response.data[0].embedding

def ensure_collections_exist():
    collections = ["ssh_logs", "ssh_commands", "ssh_errors"]
    
    for collection_name in collections:
        if not qdrant_client.collection_exists(collection_name):
            qdrant_client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
            )

def log_ssh_operation(job_id: str, host: str, user: str, command: str, result: dict):

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
                    "host": host,
                    "user": user,
                    "command": command,
                    "timestamp": timestamp,
                    "return_code": result["return_code"],
                    "type": "command"
                }
            )
        ]
    )
    
    # Log stdout lines
    if result.get("stdout"):
        for i, line in enumerate(result["stdout"].split('\n')):
            if line.strip():
                stdout_embedding = embed_text(f"STDOUT: {line}")
                qdrant_client.upsert(
                    collection_name="ssh_logs",
                    points=[
                        PointStruct(
                            id=str(uuid.uuid4()),
                            vector=stdout_embedding,
                            payload={
                                "job_id": job_id,
                                "host": host,
                                "command": command,
                                "timestamp": timestamp,
                                "line_number": i + 1,
                                "log_line": line,
                                "type": "stdout"
                            }
                        )
                    ]
                )
    
    # Log stderr lines (errors)
    if result.get("stderr"):
        for i, line in enumerate(result["stderr"].split('\n')):
            if line.strip():
                stderr_embedding = embed_text(f"ERROR: {line}")
                qdrant_client.upsert(
                    collection_name="ssh_errors",
                    points=[
                        PointStruct(
                            id=str(uuid.uuid4()),
                            vector=stderr_embedding,
                            payload={
                                "job_id": job_id,
                                "host": host,
                                "command": command,
                                "timestamp": timestamp,
                                "line_number": i + 1,
                                "log_line": line,
                                "type": "stderr",
                                "return_code": result["return_code"]
                            }
                        )
                    ]
                )
