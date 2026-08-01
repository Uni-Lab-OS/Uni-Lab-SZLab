"""SZLab 动作与 PLC 调试日志的公共工具。"""

from __future__ import annotations

import inspect
import time
import uuid
from contextvars import ContextVar
from functools import wraps
from typing import Any, Callable, ParamSpec, TypeVar

from unilabos.utils.log import logger

P = ParamSpec("P")
R = TypeVar("R")

_TRACE_ID: ContextVar[str] = ContextVar("szlab_action_trace_id", default="-")
_ACTION_NAME: ContextVar[str] = ContextVar("szlab_action_name", default="-")
_SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "access_key",
    "secret_key",
)


def current_action_log_context() -> str:
    """返回可直接拼入日志的当前动作关联字段。"""

    return f"trace={_TRACE_ID.get()} action={_ACTION_NAME.get()}"


def _is_sensitive_key(key: Any) -> bool:
    normalized = str(key).strip().lower()
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def _sanitize_for_log(value: Any, *, key: Any = "", depth: int = 0) -> Any:
    if _is_sensitive_key(key):
        return "***"
    if depth >= 4:
        return f"<{type(value).__name__}>"
    if isinstance(value, dict):
        items = list(value.items())
        sanitized = {
            str(item_key): _sanitize_for_log(
                item_value,
                key=item_key,
                depth=depth + 1,
            )
            for item_key, item_value in items[:30]
        }
        if len(items) > 30:
            sanitized["..."] = f"{len(items) - 30} more"
        return sanitized
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        sanitized_items = [
            _sanitize_for_log(item, depth=depth + 1)
            for item in items[:30]
        ]
        if len(items) > 30:
            sanitized_items.append(f"... {len(items) - 30} more")
        return sanitized_items
    if isinstance(value, bytes):
        return f"<bytes:{len(value)}>"
    return value


def compact_log_value(value: Any, *, max_length: int = 1600) -> str:
    """生成单行、限长且脱敏的日志值。"""

    text = repr(_sanitize_for_log(value)).replace("\r", "\\r").replace("\n", "\\n")
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 3]}..."


def _bound_action_parameters(
    function: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> dict[str, Any]:
    try:
        bound = inspect.signature(function).bind_partial(*args, **kwargs)
        bound.apply_defaults()
        return {
            name: value
            for name, value in bound.arguments.items()
            if name not in {"self", "cls"}
        }
    except Exception:
        return {
            "args": list(args[1:] if args else args),
            "kwargs": kwargs,
        }


def _result_failed(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    if result.get("success") is False:
        return True
    return str(result.get("status", "")).lower() in {
        "error",
        "failed",
        "failure",
        "rejected",
        "timeout",
        "write_failed",
    }


def _result_reason(result: Any) -> Any:
    if not isinstance(result, dict):
        return result
    for key in ("message", "error", "reason", "detail", "status"):
        value = result.get(key)
        if value not in (None, ""):
            return value
    return result


def trace_action(function: Callable[P, R]) -> Callable[P, R]:
    """为一个设备动作打印开始、成功、失败和耗时日志。"""

    if getattr(function, "__szlab_action_traced__", False):
        return function

    @wraps(function)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        action_name = function.__qualname__
        trace_id = uuid.uuid4().hex[:10]
        parent_trace = _TRACE_ID.get()
        parameters = _bound_action_parameters(function, args, kwargs)
        trace_token = _TRACE_ID.set(trace_id)
        action_token = _ACTION_NAME.set(action_name)
        started_at = time.monotonic()
        parent_field = f" parent_trace={parent_trace}" if parent_trace != "-" else ""
        logger.info(
            f"[SZLAB-ACTION] START trace={trace_id}{parent_field} "
            f"action={action_name} params={compact_log_value(parameters)}"
        )
        try:
            result = function(*args, **kwargs)
        except Exception as exc:
            elapsed = time.monotonic() - started_at
            logger.error(
                f"[SZLAB-ACTION] FAIL trace={trace_id} action={action_name} "
                f"elapsed={elapsed:.3f}s cause={type(exc).__name__}: {exc}"
            )
            raise
        else:
            elapsed = time.monotonic() - started_at
            if _result_failed(result):
                logger.error(
                    f"[SZLAB-ACTION] FAIL trace={trace_id} action={action_name} "
                    f"elapsed={elapsed:.3f}s reason={compact_log_value(_result_reason(result))} "
                    f"result={compact_log_value(result)}"
                )
            else:
                logger.info(
                    f"[SZLAB-ACTION] SUCCESS trace={trace_id} action={action_name} "
                    f"elapsed={elapsed:.3f}s result={compact_log_value(_result_reason(result))}"
                )
            return result
        finally:
            _ACTION_NAME.reset(action_token)
            _TRACE_ID.reset(trace_token)

    wrapped.__szlab_action_traced__ = True
    return wrapped


def install_action_logging(device_class: type[Any]) -> type[Any]:
    """包装类中已由 Uni-Lab ``@action`` 标记的动作，不改变 AST 注册语义。"""

    for name, value in tuple(device_class.__dict__.items()):
        if not callable(value) or not hasattr(value, "_action_registry_meta"):
            continue
        setattr(device_class, name, trace_action(value))
    return device_class
