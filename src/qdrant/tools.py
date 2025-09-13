import time
from typing import Annotated, TypedDict

from qdrant_client.models import (
    FieldCondition,
    Filter,
    Range,
)

from src.server import mcp

from .log_manager import (
    embed_text,
    ensure_collections_exist,
    qdrant_client,
)


class SearchResult(TypedDict):
    query: str
    results: list[dict]
    total_found: int


@mcp.tool(
    name="ssh_search_logs",
    description="Search through SSH command history and outputs using semantic search. Search 'commands' for executed commands, 'stdout' for command outputs, or 'stderr' for error messages. Supports filtering by collection (stdout, commands, stderr), host, user, and time period.",
)
def search_ssh_logs(
    query: Annotated[
        str, "Search query (e.g. 'database errors', 'memory usage', 'failed commands')"
    ],
    collection: Annotated[
        str, "Collection to search: 'stdout', 'commands', or 'stderr'"
    ] = "commands",
    host_filter: Annotated[str | None, "Filter by specific host"] = None,
    user_filter: Annotated[str | None, "Filter by specific user"] = None,
    time_hours: Annotated[int | None, "Filter by last N hours"] = None,
    limit: Annotated[int, "Number of results to return"] = 10,
) -> SearchResult:
    ensure_collections_exist()

    collection_name = f"ssh_{collection}"
    if collection_name not in ["ssh_stdout", "ssh_commands", "ssh_stderr"]:
        raise ValueError("Invalid collection. Use 'stdout', 'commands', or 'stderr'")

    filters = []
    if host_filter:
        filters.append(FieldCondition(key="host", match={"value": host_filter}))

    if user_filter:
        filters.append(FieldCondition(key="user", match={"value": user_filter}))

    if time_hours:
        since_timestamp = time.time() - (time_hours * 3600)
        filters.append(
            FieldCondition(key="timestamp", range=Range(gte=since_timestamp))
        )

    # Create embedding for search query
    embedding = embed_text(query)

    # Search in Qdrant
    results = qdrant_client.query_points(
        collection_name=collection_name,
        query=embedding,
        query_filter=Filter(must=filters) if filters else None,
        with_payload=True,
        limit=limit,
    )

    formatted_results = []
    for point in results.points:
        payload = point.payload
        formatted_results.append(
            {
                "relevance_score": point.score,
                "host": payload.get("host", ""),
                "command": payload.get("command", ""),
                "timestamp": payload.get("timestamp", 0),
                "job_id": payload.get("job_id", ""),
                "stdout": payload.get("stdout", ""),
                "stderr": payload.get("stderr", ""),
                "return_code": payload.get("return_code"),
                "formatted_time": time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(payload.get("timestamp", 0))
                ),
            }
        )

    return {
        "query": query,
        "results": formatted_results,
        "total_found": len(formatted_results),
    }


@mcp.tool(
    name="ssh_get_statistics",
    description="Get comprehensive usage statistics and insights from SSH command history including success rates, most used hosts/commands, and recent errors. Available filters: time period, user, host.",
)
def get_ssh_statistics(
    time_hours: Annotated[int, "Statistics for last N hours"] = 24,
    user_filter: Annotated[str | None, "Filter statistics by specific user"] = None,
    host_filter: Annotated[str | None, "Filter statistics by specific host"] = None,
) -> dict:
    ensure_collections_exist()

    filters = []
    if host_filter:
        filters.append(FieldCondition(key="host", match={"value": host_filter}))

    if user_filter:
        filters.append(FieldCondition(key="user", match={"value": user_filter}))

    if time_hours:
        since_timestamp = time.time() - (time_hours * 3600)
        filters.append(
            FieldCondition(key="timestamp", range=Range(gte=since_timestamp))
        )

    stats = {
        "time_period_hours": time_hours,
        "commands_executed": 0,
        "successful_commands": 0,
        "failed_commands": 0,
        "most_used_hosts": {},
        "most_common_commands": {},
        "recent_errors": [],
    }

    # Get command statistics
    cmd_results = qdrant_client.scroll(
        collection_name="ssh_commands",
        scroll_filter=Filter(must=filters) if filters else None,
        limit=1000,
        with_payload=True,
    )

    for point in cmd_results[0]:
        payload = point.payload
        stats["commands_executed"] += 1

        if payload.get("return_code") == 0:
            stats["successful_commands"] += 1
        else:
            stats["failed_commands"] += 1

        # Count hosts
        if not host_filter:
            host = payload.get("host", "unknown")
            stats["most_used_hosts"][host] = stats["most_used_hosts"].get(host, 0) + 1

        # Count commands
        command = payload.get("command", "").split()[0]  # First word of command
        if command:
            stats["most_common_commands"][command] = (
                stats["most_common_commands"].get(command, 0) + 1
            )

    # Get recent errors
    error_results = qdrant_client.scroll(
        collection_name="ssh_stderr",
        scroll_filter=Filter(must=filters) if filters else None,
        limit=10,
        with_payload=True,
    )

    for point in error_results[0]:
        payload = point.payload
        stats["recent_errors"].append(
            {
                "host": payload.get("host", ""),
                "command": payload.get("command", ""),
                "error": payload.get("stderr", ""),
                "timestamp": time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(payload.get("timestamp", 0))
                ),
            }
        )

    # Sort most common items
    if host_filter is None:
        stats["most_used_hosts"] = dict(
            sorted(stats["most_used_hosts"].items(), key=lambda x: x[1], reverse=True)[
                :10
            ]
        )

    stats["most_common_commands"] = dict(
        sorted(stats["most_common_commands"].items(), key=lambda x: x[1], reverse=True)[
            :10
        ]
    )

    return stats


@mcp.tool(
    name="ssh_suggest_commands",
    description="Get command suggestions based on context using semantic search of successful command history. Finds similar commands that have been executed successfully in the past.",
)
def suggest_commands(
    context: Annotated[
        str, "Current situation or goal (e.g. 'check disk space', 'restart service')"
    ],
    host: Annotated[str | None, "Target host for context-specific suggestions"] = None,
    limit: Annotated[int, "Number of suggestions to return"] = 5,
) -> dict:
    ensure_collections_exist()

    search_query = context
    if host:
        search_query += f" host:{host}"

    filters = [
        FieldCondition(key="return_code", match={"value": 0})
    ]  # Only successful commands
    if host:
        filters.append(FieldCondition(key="host", match={"value": host}))

    embedding = embed_text(search_query)
    results = qdrant_client.query_points(
        collection_name="ssh_commands",
        query=embedding,
        query_filter=Filter(must=filters),
        with_payload=True,
        limit=limit * 2,  # Get more to filter duplicates
    )

    # Process suggestions and remove duplicates
    suggestions = {}
    for point in results.points:
        payload = point.payload
        command = payload.get("command", "")
        if command and command not in suggestions:
            suggestions[command] = {
                "command": command,
                "relevance_score": point.score,
                "host": payload.get("host", ""),
                "last_used": time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(payload.get("timestamp", 0))
                ),
                "success_rate": 1.0,  # We only queried successful commands
            }

    # Sort by relevance and limit results
    sorted_suggestions = sorted(
        suggestions.values(), key=lambda x: x["relevance_score"], reverse=True
    )[:limit]

    return {
        "context": context,
        "host": host,
        "suggestions": sorted_suggestions,
        "total_suggestions": len(sorted_suggestions),
    }
