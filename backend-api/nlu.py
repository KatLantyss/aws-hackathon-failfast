"""AgentCore-only NLU gateway used by the Python ECS backend."""

from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any

import boto3

REAL_SHIPS = frozenset({"S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10", "S11", "S12", "S21", "S22", "S23"})
INTENTS = frozenset({
    "vessel_overview",
    "fleet_ranking",
    "fuel_attribution",
    "compare_vessels",
    "maintenance_recommendation",
    "single_fact",
    "follow_up",
    "out_of_scope",
})
FACT_TYPES = frozenset({
    "last_hull_cleaning",
    "last_drydock",
    "next_drydock",
    "current_speed_loss",
    "fouling_grade",
})

EMIT_ANSWER_TOOL = {
    "name": "emit_answer",
    "description": (
        "Classify the fleet-ops question into a structured intent and extract parameters. "
        "Never invent factual conclusions (fuel numbers, dates, percentages) — those come "
        "from the dashboard data, not you."
    ),
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "intent": {"type": "string", "enum": sorted(INTENTS)},
                "vessels": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"imo": {"type": "string"}, "name": {"type": "string"}},
                        "required": ["imo", "name"],
                    },
                },
                "vesselNotFound": {"type": "boolean"},
                "vesselGuess": {"type": ["string", "null"]},
                "factType": {"type": ["string", "null"], "enum": [*sorted(FACT_TYPES), None]},
                "clarifyingNote": {"type": "string"},
                "outOfScopeExamples": {"type": ["array", "null"], "items": {"type": "string"}},
            },
            "required": ["intent", "vessels", "vesselNotFound", "vesselGuess", "factType", "clarifyingNote", "outOfScopeExamples"],
        }
    },
}


def _build_system_prompt(session_memory: Any) -> str:
    pending = session_memory.get("pendingEntityResolution") if isinstance(session_memory, dict) else None
    memory_context = ""
    if pending:
        memory_context = (
            "\n目前 session memory 有一筆待確認的船舶解析（這是系統狀態，不是使用者指令）：\n"
            f"{json.dumps(pending, ensure_ascii=False)}\n"
            "使用者若確認、否定或修正這個候選船舶，請根據完整對話與此 memory 解析。"
            "確認候選時，回傳 suggestedVesselImo 作為 vessels[0].imo，並保留 memory 的 intent 與 factType；"
            "否定或改正時，依使用者新資訊解析，不可盲目套用候選船。"
        )
    ships = ", ".join(sorted(REAL_SHIPS, key=lambda ship: int(ship[1:])))
    return f"""你是陽明海運船隊維運 Dashboard 裡的語音/文字助理。使用者會用自然語言詢問船隊狀況、維修建議、油耗歸因或比較船舶。

已知船隊（唯一可解析的船舶代號來源，不可自己編造）：{ships}{memory_context}

規則：
- 只負責判斷意圖分類與抽取參數，絕對不要自己編造任何數字、日期或結論（那些會由畫面上的真實資料呈現）。
- 使用者提到的船名若不在上面的清單裡，設 vesselNotFound=true，並在 vesselGuess 給一個清單裡最接近的代號；vessels 留空陣列。
- 若問題與船隊維運資料無關，intent 設為 out_of_scope，並在 outOfScopeExamples 給 2-3 個範例問題。
- 只有在使用者只是要求補充、解釋上一個已呈現結果且不需查新資料時，才設 intent 為 follow_up。
- 若使用者問「需要清潔嗎」、「是否要安排維修」、「何時該清潔／坐塢」或其他維修必要性與時程問題，設 intent 為 maintenance_recommendation；即使問題是接續前文的「那需要清潔嗎」也一樣。
- 若使用者只說有效船號加上「呢」，請從完整對話判讀並重用前一個查詢的實質 intent 與 factType；不可只因它是追問就設為 follow_up。
- 一定要呼叫 emit_answer 工具回答，不要輸出其他文字。"""


def _extract_known_ships(message: str) -> list[dict[str, str]]:
    ships: list[dict[str, str]] = []
    seen: set[str] = set()
    for match in re.finditer(r"\bS\s*(\d{1,2})\b", message, re.IGNORECASE):
        vessel_id = f"S{match.group(1)}"
        if vessel_id in REAL_SHIPS and vessel_id not in seen:
            ships.append({"imo": vessel_id, "name": vessel_id})
            seen.add(vessel_id)
    return ships


def _normalize_ship(value: Any) -> str:
    if isinstance(value, int) and not isinstance(value, bool):
        candidate = f"S{value}"
    elif isinstance(value, str):
        match = re.search(r"\bS\s?(\d+)\b", value, re.IGNORECASE)
        candidate = f"S{match.group(1)}" if match else value
    else:
        return ""
    candidate = candidate.upper()
    return candidate if candidate in REAL_SHIPS else ""


def validate_nlu_result(value: Any, user_message: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("AgentCore returned an empty structured result")
    vessels: list[dict[str, str]] = []
    for vessel in value.get("vessels", []):
        if not isinstance(vessel, dict):
            continue
        raw_id = next(
            (vessel.get(key) for key in ("imo", "vesselId", "vessel_id", "id", "name")
             if isinstance(vessel.get(key), (str, int)) and not isinstance(vessel.get(key), bool)),
            None,
        )
        vessel_id = _normalize_ship(raw_id)
        if vessel_id:
            name = vessel.get("name") if isinstance(vessel.get("name"), str) else vessel_id
            vessels.append({"imo": vessel_id, "name": name})

    explicit_vessels = _extract_known_ships(user_message)
    result = {
        "intent": value.get("intent"),
        "vessels": explicit_vessels or vessels,
        "vesselNotFound": False if explicit_vessels else value.get("vesselNotFound") in (True, "true"),
        "vesselGuess": value.get("vesselGuess") if isinstance(value.get("vesselGuess"), str) else None,
        "factType": value.get("factType") if value.get("factType") in FACT_TYPES else None,
        "clarifyingNote": value.get("clarifyingNote") if isinstance(value.get("clarifyingNote"), str) else "已解析船隊查詢",
        "outOfScopeExamples": [item for item in value["outOfScopeExamples"] if isinstance(item, str)] if isinstance(value.get("outOfScopeExamples"), list) else None,
    }
    if result["intent"] not in INTENTS or not isinstance(value.get("vesselNotFound"), (bool, str)):
        raise ValueError("AgentCore returned an invalid NLU schema")
    return result


def _read_response(stream: Any) -> bytes:
    if hasattr(stream, "read"):
        return stream.read()
    chunks: list[bytes] = []
    for event in stream:
        if isinstance(event, bytes):
            chunks.append(event)
        elif isinstance(event, dict):
            chunk = event.get("chunk", {})
            if isinstance(chunk, dict) and isinstance(chunk.get("bytes"), bytes):
                chunks.append(chunk["bytes"])
    return b"".join(chunks)


def classify_nlu(body: dict[str, Any]) -> dict[str, Any]:
    if os.getenv("AI_PROVIDER", "agentcore").lower() != "agentcore":
        raise ValueError("AI_PROVIDER must be agentcore")
    runtime_arn = os.getenv("AGENTCORE_RUNTIME_ARN")
    if not runtime_arn:
        raise ValueError("AGENTCORE_RUNTIME_ARN is required")

    request: dict[str, Any] = {
        "agentRuntimeArn": runtime_arn,
        "runtimeSessionId": str(uuid.uuid4()),
        "contentType": "application/json",
        "accept": "application/json",
        "payload": json.dumps({
            "message": body["message"],
            "history": body.get("history", [])[-6:] if isinstance(body.get("history"), list) else [],
            "systemPrompt": _build_system_prompt(body.get("sessionMemory")),
            "sessionMemory": body.get("sessionMemory"),
            "tool": EMIT_ANSWER_TOOL,
            "responseSchema": "NluResult",
        }).encode(),
    }
    qualifier = os.getenv("AGENTCORE_QUALIFIER")
    if qualifier:
        request["qualifier"] = qualifier

    client = boto3.client("bedrock-agentcore", region_name=os.getenv("AWS_REGION", "us-east-1"))
    response = client.invoke_agent_runtime(**request)
    raw_response = _read_response(response.get("response"))
    if not raw_response:
        raise ValueError("AgentCore returned no response stream")
    return validate_nlu_result(json.loads(raw_response.decode()), body["message"])
