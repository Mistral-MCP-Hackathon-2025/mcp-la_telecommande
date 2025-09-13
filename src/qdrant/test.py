import os
import time
import uuid
from typing import Annotated

from dotenv import load_dotenv

load_dotenv()

from mistralai import Mistral

mistral_api_key = os.getenv("MISTRAL_API_KEY")
# print("MISTRAL_API_KEY:", mistral_api_key)
mistral_model = "mistral-embed"

client = Mistral(api_key=mistral_api_key)

from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct, FieldCondition, Range, Filter

qdrant_api_key = os.getenv("QDRANT_API_KEY")

qdrant_client = QdrantClient(
    url="https://43f7d188-39ab-49fd-a399-2f72552bc113.eu-central-1-0.aws.cloud.qdrant.io:6333",
    api_key=qdrant_api_key,
)

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

def search_ssh_logs(
    query: Annotated[str, "Search query (e.g. 'database errors', 'memory usage', 'failed commands')"],
    collection: Annotated[str, "Collection to search: 'logs', 'commands', or 'errors'"] = "logs",
    host_filter: Annotated[str | None, "Filter by specific host"] = None,
    time_hours: Annotated[int | None, "Filter by last N hours"] = None,
    limit: Annotated[int, "Number of results to return"] = 10,
):
    """Search through logged SSH operations using semantic similarity"""
    ensure_collections_exist()
    
    collection_name = f"ssh_{collection}"
    if collection_name not in ["ssh_logs", "ssh_commands", "ssh_errors"]:
        raise ValueError(f"Invalid collection. Use 'logs', 'commands', or 'errors'")
    
    # Build filters
    filters = []
    if host_filter:
        filters.append(FieldCondition(key="host", match={"value": host_filter}))
    
    if time_hours:
        since_timestamp = time.time() - (time_hours * 3600)
        filters.append(FieldCondition(key="timestamp", range=Range(gte=since_timestamp)))
    
    # Create embedding for search query
    embedding = embed_text(query)
    
    # Search in Qdrant
    results = qdrant_client.query_points(
        collection_name=collection_name,
        query=embedding,
        query_filter=Filter(must=filters) if filters else None,
        with_payload=True,
        limit=limit
    )
    
    # Format results
    formatted_results = []
    for point in results.points:
        payload = point.payload
        formatted_results.append({
            "relevance_score": point.score,
            "log_line": payload.get("log_line", payload.get("command", "")),
            "host": payload.get("host", ""),
            "command": payload.get("command", ""),
            "timestamp": payload.get("timestamp", 0),
            "job_id": payload.get("job_id", ""),
            "type": payload.get("type", ""),
            "return_code": payload.get("return_code"),
            "formatted_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(payload.get("timestamp", 0)))
        })
    
    return {
        "query": query,
        "results": formatted_results,
        "total_found": len(formatted_results)
    }


# Test with fake logs
if __name__ == "__main__":
    ensure_collections_exist()

    # Create fake SSH job data for testing
    fake_jobs = [
        {
            "job_id": "job_001",
            "host": "web-server-01",
            "user": "admin",
            "command": "systemctl status nginx",
            "result": {
                "return_code": 0,
                "stdout": "● nginx.service - A high performance web server\n   Loaded: loaded (/lib/systemd/system/nginx.service; enabled)\n   Active: active (running) since Mon 2024-01-15 10:30:00 UTC",
                "stderr": ""
            }
        },
        {
            "job_id": "job_002", 
            "host": "db-server-01",
            "user": "postgres",
            "command": "psql -c 'SELECT * FROM users LIMIT 5;'",
            "result": {
                "return_code": 1,
                "stdout": "",
                "stderr": "psql: FATAL: database \"users\" does not exist\nConnection to database failed"
            }
        },
        {
            "job_id": "job_003",
            "host": "app-server-01", 
            "user": "deploy",
            "command": "docker ps -a",
            "result": {
                "return_code": 0,
                "stdout": "CONTAINER ID   IMAGE     COMMAND   CREATED   STATUS    PORTS     NAMES\n12345abc       nginx     nginx     2 hours   Up 2h     80/tcp    web_app\n67890def       redis     redis     1 hour    Up 1h     6379/tcp  cache",
                "stderr": ""
            }
        },
        {
            "job_id": "job_004",
            "host": "web-server-01",
            "user": "admin", 
            "command": "tail -n 20 /var/log/nginx/error.log",
            "result": {
                "return_code": 0,
                "stdout": "2024/01/15 14:23:45 [error] 1234#0: *5678 connect() failed (111: Connection refused) while connecting to upstream\n2024/01/15 14:25:12 [crit] 1234#0: malloc() failed (12: Cannot allocate memory)",
                "stderr": ""
            }
        },
        {
            "job_id": "job_005",
            "host": "db-server-01",
            "user": "admin",
            "command": "free -h",
            "result": {
                "return_code": 0,
                "stdout": "              total        used        free      shared  buff/cache   available\nMem:           7.8G        6.2G        234M        123M        1.4G        1.1G\nSwap:          2.0G        1.8G        234M",
                "stderr": ""
            }
        }
    ]

    # Index all fake jobs
    for job in fake_jobs:
        log_ssh_operation(
            job_id=job["job_id"],
            host=job["host"], 
            user=job["user"],
            command=job["command"],
            result=job["result"]
        )

    print(f"Indexed {len(fake_jobs)} fake SSH jobs")

    # Test search
    results = search_ssh_logs("database error", collection="logs", limit=3)
    print("Search results for 'database error':")
    for result in results["results"]:
        print(f"- {result['log_line']} (score: {result['relevance_score']})")
