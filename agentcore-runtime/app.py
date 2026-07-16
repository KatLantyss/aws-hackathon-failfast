"""AgentCore Runtime entrypoint for the fleet-operations NLU agent."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import boto3
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

app = FastAPI(title="Fleet Operations NLU Agent")


def _history_messages(history: Any) -> list[dict[str, Any]]:
    if not isinstance(history, list):
        return []
    messages: list[dict[str, Any]] = []
    for message in history[-6:]:
        if not isinstance(message, dict):
            continue
        role, content = message.get("role"), message.get("content")
        if role in {"user", "assistant"} and isinstance(content, str):
            messages.append({"role": role, "content": [{"text": content}]})
    return messages


def _classify(payload: dict[str, Any]) -> dict[str, Any]:
    message = payload.get("message")
    system_prompt = payload.get("systemPrompt")
    tool = payload.get("tool")
    if not isinstance(message, str) or not message.strip():
        raise ValueError("message is required")
    if not isinstance(system_prompt, str) or not system_prompt:
        raise ValueError("systemPrompt is required")
    if not isinstance(tool, dict):
        raise ValueError("tool is required")

    response = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION", "us-east-1")).converse(
        modelId=os.getenv("AGENT_MODEL_ID", "us.anthropic.claude-sonnet-4-6"),
        system=[{"text": system_prompt}],
        messages=[*_history_messages(payload.get("history")), {"role": "user", "content": [{"text": message}]}],
        inferenceConfig={"maxTokens": 512, "temperature": 0},
        toolConfig={
            "tools": [{"toolSpec": tool}],
            "toolChoice": {"tool": {"name": tool.get("name", "emit_answer")}},
        },
    )
    tool_use = next(
        (block["toolUse"] for block in response.get("output", {}).get("message", {}).get("content", [])
         if "toolUse" in block and block["toolUse"].get("name") == tool.get("name", "emit_answer")),
        None,
    )
    if not tool_use:
        raise ValueError("Agent did not return the required structured result")
    return tool_use.get("input", {})


@app.get("/ping")
def ping() -> Response:
    return Response(status_code=200)


@app.post("/invocations")
async def invocations(request: Request):
    try:
        payload = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JSONResponse(content={"error": "invalid JSON body"}, status_code=400)
    if not isinstance(payload, dict):
        return JSONResponse(content={"error": "JSON object required"}, status_code=400)
    try:
        return await asyncio.to_thread(_classify, payload)
    except ValueError as exc:
        return JSONResponse(content={"error": str(exc)}, status_code=400)
    except Exception:
        return JSONResponse(content={"error": "AgentCore NLU invocation failed"}, status_code=502)
