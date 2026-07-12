"""
JSON协议定义
============
功能：
  - 定义统一的任务命令JSON协议格式
  - TaskCommand: 任务命令数据模型（支持move/vision/complex/query/system五种类型）
  - 提供命令验证、序列化和反序列化功能
  - extract_json_from_response(): 从API响应中提取JSON
  - create_clarify_command(): 创建澄清命令（当指令不明确时使用）

协议格式：
  {
    "version": "1.0",
    "type": "move",
    "mode": "single",
    "payload": {},
    "priority": 5,
    "timeout": 30,
    "request_id": "uuid"
  }

依赖：
  - pydantic: 数据模型验证
"""
import json
import uuid
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator


class MovePayload(BaseModel):
    command: str = Field(..., description="forward, backward, turn_left, turn_right, stop")
    speed: Optional[int] = Field(10, ge=0, le=100, description="0-100")
    duration: Optional[float] = Field(None, description="移动时间（秒）")
    distance: Optional[float] = Field(None, description="移动距离（米）")
    angle: Optional[int] = Field(None, ge=0, le=360, description="转向角度（度）")

    @validator("command")
    def validate_command(cls, v):
        valid_commands = ["forward", "backward", "turn_left", "turn_right", "stop"]
        if v not in valid_commands:
            raise ValueError(f"command must be one of {valid_commands}")
        return v

    @validator("distance", always=True)
    def check_distance_or_duration(cls, v, values):
        command = values.get("command")
        if command in ["turn_left", "turn_right", "stop"]:
            return v
        if v is None and values.get("duration") is None:
            raise ValueError("distance or duration must be provided")
        return v


class VisionResponse(BaseModel):
    include_image: Optional[bool] = False
    include_bbox: Optional[bool] = True


class VisionPayload(BaseModel):
    operation: str = Field(..., description="detect, capture, track, stream")
    targets: List[str] = Field(..., description="检测目标列表")
    confidence: Optional[float] = Field(0.7, ge=0.0, le=1.0)
    response: Optional[VisionResponse] = None

    @validator("operation")
    def validate_operation(cls, v):
        valid_ops = ["detect", "capture", "track", "stream"]
        if v not in valid_ops:
            raise ValueError(f"operation must be one of {valid_ops}")
        return v

    @validator("targets")
    def validate_targets(cls, v):
        valid_targets = ["puddle", "fallen_person", "obstacle", "traffic_light", "person", "vehicle"]
        for target in v:
            if target not in valid_targets:
                raise ValueError(f"target {target} must be one of {valid_targets}")
        return v


class ComplexStep(BaseModel):
    type: str = Field(..., description="move, vision, complex, query, system")
    payload: Dict[str, Any] = Field(..., description="任务参数")


class ComplexPayload(BaseModel):
    policy: Optional[str] = Field(None, description="patrol, explore, follow_wall")
    steps: Optional[List[ComplexStep]] = None
    tasks: Optional[List[ComplexStep]] = None
    triggers: Optional[Dict[str, str]] = None
    max_duration: Optional[int] = Field(600, description="最大执行时间（秒）")


class QueryPayload(BaseModel):
    target: str = Field(..., description="battery, position, speed, status, sensor, all")
    format: Optional[str] = Field("json", description="json, text")

    @validator("target")
    def validate_target(cls, v):
        valid_targets = ["battery", "position", "speed", "status", "sensor", "all", "clarify"]
        if v not in valid_targets:
            raise ValueError(f"target must be one of {valid_targets}")
        return v

    @validator("format")
    def validate_format(cls, v):
        valid_formats = ["json", "text"]
        if v not in valid_formats:
            raise ValueError(f"format must be one of {valid_formats}")
        return v


class SystemParams(BaseModel):
    delay: Optional[int] = None


class SystemPayload(BaseModel):
    operation: str = Field(..., description="reboot, shutdown, reset, update, status")
    params: Optional[SystemParams] = None

    @validator("operation")
    def validate_operation(cls, v):
        valid_ops = ["reboot", "shutdown", "reset", "update", "status"]
        if v not in valid_ops:
            raise ValueError(f"operation must be one of {valid_ops}")
        return v


class TaskCommand(BaseModel):
    version: str = Field("1.0", description="协议版本号")
    type: str = Field(..., description="move, vision, complex, query, system")
    mode: Optional[str] = Field("single", description="single, sequence, parallel")
    payload: Dict[str, Any] = Field(..., description="具体任务参数")
    priority: Optional[int] = Field(5, ge=1, le=10, description="优先级（1-10）")
    timeout: Optional[int] = Field(30, description="超时时间（秒）")
    request_id: Optional[str] = Field(None, description="请求追踪ID")

    @validator("version")
    def validate_version(cls, v):
        if v != "1.0":
            raise ValueError("version must be '1.0'")
        return v

    @validator("type")
    def validate_type(cls, v):
        valid_types = ["move", "vision", "complex", "query", "system"]
        if v not in valid_types:
            raise ValueError(f"type must be one of {valid_types}")
        return v

    @validator("mode")
    def validate_mode(cls, v):
        valid_modes = ["single", "sequence", "parallel"]
        if v not in valid_modes:
            raise ValueError(f"mode must be one of {valid_modes}")
        return v

    @validator("request_id", always=True)
    def set_request_id(cls, v):
        return v or str(uuid.uuid4())

    def to_json(self) -> str:
        return json.dumps(self.dict(), indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "TaskCommand":
        data = json.loads(json_str)
        return cls(**data)

    def validate_payload(self) -> bool:
        try:
            if self.type == "move":
                MovePayload(**self.payload)
            elif self.type == "vision":
                VisionPayload(**self.payload)
            elif self.type == "complex":
                ComplexPayload(**self.payload)
            elif self.type == "query":
                QueryPayload(**self.payload)
            elif self.type == "system":
                SystemPayload(**self.payload)
            return True
        except Exception as e:
            raise ValueError(f"Payload validation failed: {str(e)}")

    def is_valid(self) -> bool:
        try:
            self.validate_payload()
            return True
        except Exception:
            return False


def create_clarify_command(question: str) -> TaskCommand:
    return TaskCommand(
        type="query",
        payload={
            "target": "clarify",
            "question": question,
            "format": "text"
        }
    )


def extract_json_from_response(response_text: str) -> str:
    start_idx = response_text.find("{")
    end_idx = response_text.rfind("}") + 1
    if start_idx == -1 or end_idx == 0:
        raise ValueError("No JSON found in response")
    return response_text[start_idx:end_idx]