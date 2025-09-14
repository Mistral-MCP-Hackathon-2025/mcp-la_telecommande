import time
from typing import Annotated, TypedDict

from mcp.server.fastmcp import Context
from qdrant_client.models import FieldCondition, Filter, Range

from src.config.permissions import permissions_enabled
from src.server import config_manager, mcp

from .log_manager import (
    embed_text,
    ensure_collections_exist,
    qdrant_client,
)


class SearchItem(TypedDict):
    relevance_score: float
    vm_name: str
    requested_by: str
    command: str
    job_id: str
    timestamp: float
    formatted_time: str
    stdout: str
    stderr: str
    return_code: int | None


class SearchResult(TypedDict):
    query: str
    total_found: int
    results: list[SearchItem]


def _extract_api_key_from_headers(ctx: Context) -> str | None:
    """Retrieve API key from Authorization header (Bearer or raw)."""
    hdrs = None
    try:
        req = getattr(ctx.request_context, "request", None)
        if req is not None:
            hdrs = getattr(req, "headers", None)
        if hdrs is None:
            hdrs = getattr(ctx.request_context, "headers", None)
        if hdrs is None:
            meta = getattr(ctx.request_context, "meta", None)
            if isinstance(meta, dict):
                hdrs = meta.get("headers")
    except Exception:
        hdrs = None

    auth = None
    if hdrs:
        auth = hdrs.get("Authorization") or hdrs.get("authorization")
    if not auth:
        return None
    auth = str(auth).strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return auth or None


@mcp.tool(
    name="ssh_search_logs",
    description=(
        "Semantic search across SSH history.\n\n"
        "Collections:\n"
        "- 'commands' (default): executed commands\n"
        "- 'stdout': command outputs\n"
        "- 'stderr': error outputs\n\n"
        "Args:\n"
        "- query (str, required): natural language query, e.g. 'database errors', 'failed rsync'.\n"
        "- collection (str, optional): one of 'stdout' | 'commands' | 'stderr' (default: 'commands').\n"
        "- vm_name (str|None, optional): restrict results to this VM name. Authorization is enforced.\n"
        "- user_filter (str|None, optional): only results from this user.\n"
        "- time_hours (int|None, optional): restrict to last N hours.\n"
        "- limit (int, optional): number of results to return (default: 10).\n\n"
        "Returns: { query, total_found, results[] } where each result has:\n"
        "- relevance_score (float), vm_name (str), requested_by (str), command (str), job_id (str), timestamp (float),\n"
        "  formatted_time (YYYY-MM-DD HH:MM:SS), stdout (str), stderr (str), return_code (int|None).\n\n"
        "Example: search 'oom killer' in last 6 hours of stderr: { query: 'oom killer', collection: 'stderr', time_hours: 6 }"
    ),
)
def search_ssh_logs(
    query: Annotated[
        str, "Search query (e.g. 'database errors', 'memory usage', 'failed commands')"
    ],
    collection: Annotated[
        str, "Collection to search: 'stdout', 'commands', or 'stderr'"
    ] = "commands",
    vm_name: Annotated[str | None, "Filter by specific VM name (authorization enforced)"] = None,
    user_filter: Annotated[str | None, "Filter by YAML username (requested_by)"] = None,
    time_hours: Annotated[int | None, "Filter by last N hours"] = None,
    limit: Annotated[int, "Number of results to return"] = 10,
    ctx: Context | None = None,
) -> SearchResult:
    ensure_collections_exist()

    collection_name = f"ssh_{collection}"
    if collection_name not in ["ssh_stdout", "ssh_commands", "ssh_stderr"]:
        raise ValueError("Invalid collection. Use 'stdout', 'commands', or 'stderr'")

    # Authorization: if a vm_name filter is specified and permissions are enabled, require a valid API key
    if vm_name and permissions_enabled(config_manager.raw):
        if ctx is None:
            raise ValueError("API key invalid or VM not permitted")
        api_key = _extract_api_key_from_headers(ctx)
        if not api_key:
            raise ValueError("API key invalid or VM not permitted")
        # This will raise if not permitted
        config_manager.ensure_can_access(api_key, vm_name)

    filters = []
    if vm_name:
        filters.append(FieldCondition(key="vm_name", match={"value": vm_name}))

    if user_filter:
        filters.append(FieldCondition(key="requested_by", match={"value": user_filter}))

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

    formatted_results: list[SearchItem] = []
    for point in results.points:
        payload = point.payload
        formatted_results.append(
            {
                "relevance_score": point.score,
                "vm_name": payload.get("vm_name", ""),
                "requested_by": payload.get("requested_by", ""),
                "command": payload.get("command", ""),
                "job_id": payload.get("job_id", ""),
                "timestamp": payload.get("timestamp", 0),
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
    description=(
        "Aggregate usage stats over SSH command history.\n\n"
        "Args:\n"
        "- time_hours (int, optional): lookback window (default: 24).\n"
        "- user_filter (str|None, optional): limit to one user.\n"
        "- vm_name (str|None, optional): limit to one VM name (authorization enforced).\n\n"
        "Returns: {\n"
        "  time_period_hours (int),\n"
        "  commands_executed (int), successful_commands (int), failed_commands (int),\n"
        "  most_used_vms (map vm_name->count, top 10),\n"
        "  most_common_commands (map cmd->count, top 10),\n"
        "  recent_errors: [{ vm_name, command, error, timestamp, requested_by }] (up to 10)\n"
        "}.\n\n"
        "Notes: success/failed based on return_code == 0."
    ),
)
def get_ssh_statistics(
    time_hours: Annotated[int, "Statistics for last N hours"] = 24,
    user_filter: Annotated[str | None, "Filter statistics by specific user"] = None,
    vm_name: Annotated[str | None, "Filter statistics by specific VM name (authorization enforced)"] = None,
    ctx: Context | None = None,
) -> dict:
    ensure_collections_exist()

    # Authorization if filtering to a vm_name
    if vm_name and permissions_enabled(config_manager.raw):
        if ctx is None:
            raise ValueError("API key invalid or VM not permitted")
        api_key = _extract_api_key_from_headers(ctx)
        if not api_key:
            raise ValueError("API key invalid or VM not permitted")
        config_manager.ensure_can_access(api_key, vm_name)

    filters = []
    if vm_name:
        filters.append(FieldCondition(key="vm_name", match={"value": vm_name}))

    if user_filter:
        filters.append(FieldCondition(key="requested_by", match={"value": user_filter}))

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
        "most_used_vms": {},
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

        # Count VMs
        if not vm_name:
            vm = payload.get("vm_name", "unknown")
            stats["most_used_vms"][vm] = stats["most_used_vms"].get(vm, 0) + 1

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
                "vm_name": payload.get("vm_name", ""),
                "command": payload.get("command", ""),
                "error": payload.get("stderr", ""),
                "requested_by": payload.get("requested_by", ""),
                "timestamp": time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(payload.get("timestamp", 0))
                ),
            }
        )

    # Sort most common items
    if vm_name is None:
        stats["most_used_vms"] = dict(
            sorted(stats["most_used_vms"].items(), key=lambda x: x[1], reverse=True)[
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
    description=(
        "Suggest commands from prior successful executions using semantic similarity.\n\n"
        "Args:\n"
        "- context (str, required): natural language goal, e.g. 'check disk space'.\n"
        "- vm_name (str|None, optional): bias suggestions to a specific VM name (authorization enforced).\n"
        "- limit (int, optional): number of suggestions to return (default: 5).\n\n"
        "Returns: { context, vm_name, total_suggestions, suggestions[] } where each suggestion has:\n"
        "- command (str), relevance_score (float), vm_name (str), requested_by (str), last_used (YYYY-MM-DD HH:MM:SS), success_rate (float).\n\n"
        "Notes: results are deduplicated by command and only drawn from return_code == 0 history."
    ),
)
def suggest_commands(
    context: Annotated[
        str, "Current situation or goal (e.g. 'check disk space', 'restart service')"
    ],
    vm_name: Annotated[
        str | None, "Target VM for context-specific suggestions (authorization enforced)"
    ] = None,
    limit: Annotated[int, "Number of suggestions to return"] = 5,
    ctx: Context | None = None,
) -> dict:
    ensure_collections_exist()

    search_query = context
    if vm_name:
        search_query += f" vm:{vm_name}"

    # Authorization if narrowing to a VM
    if vm_name and permissions_enabled(config_manager.raw):
        if ctx is None:
            raise ValueError("API key invalid or VM not permitted")
        api_key = _extract_api_key_from_headers(ctx)
        if not api_key:
            raise ValueError("API key invalid or VM not permitted")
        config_manager.ensure_can_access(api_key, vm_name)

    filters = [FieldCondition(key="return_code", match={"value": 0})]
    if vm_name:
        filters.append(FieldCondition(key="vm_name", match={"value": vm_name}))

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
                "vm_name": payload.get("vm_name", ""),
                "requested_by": payload.get("requested_by", ""),
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
        "vm_name": vm_name,
        "suggestions": sorted_suggestions,
        "total_suggestions": len(sorted_suggestions),
    }
