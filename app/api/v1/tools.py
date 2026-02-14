import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api import deps
from app.tools.registry import tool_registry

router = APIRouter()
logger = logging.getLogger(__name__)


class ToolExecuteRequest(BaseModel):
    tool: str
    arguments: Dict[str, Any] = {}


@router.get("/")
async def list_tools(
    api_key: str = Depends(deps.verify_api_key)
):
    """List all available tools."""
    tools = tool_registry.list_tools()
    return {"tools": [tool.to_openai_tool() for tool in tools]}


@router.post("/execute")
async def execute_tool(
    request: ToolExecuteRequest,
    api_key: str = Depends(deps.verify_api_key)
):
    """Execute a tool with the given arguments."""
    tool = tool_registry.get_tool(request.tool)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")

    # Only pass arguments that match the tool's parameter schema
    allowed_params = set(tool.parameters.get("properties", {}).keys())
    filtered_args = {k: v for k, v in request.arguments.items() if k in allowed_params}

    try:
        result = await tool.execute(**filtered_args)
    except Exception:
        logger.exception("Tool execution failed: %s", request.tool)
        raise HTTPException(status_code=500, detail="Tool execution failed")

    return {
        "tool": request.tool,
        "result": result
    }
