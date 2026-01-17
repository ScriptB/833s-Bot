from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Any

import discord

log = logging.getLogger("guardian.observability")


class LogLevel(Enum):
    """Structured log levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ActionType(Enum):
    """Action types for structured logging."""
    COMMAND = "command"
    PANEL_DEPLOY = "panel_deploy"
    PANEL_REPAIR = "panel_repair"
    ROLE_ASSIGN = "role_assign"
    TICKET_CREATE = "ticket_create"
    TICKET_CLOSE = "ticket_close"
    API_CALL = "api_call"
    ERROR = "error"
    STARTUP = "startup"


@dataclass
class StructuredLogEntry:
    """Structured log entry with context."""
    timestamp: datetime
    level: LogLevel
    action: ActionType
    guild_id: int | None
    user_id: int | None
    message: str
    details: dict[str, Any]
    duration_ms: float | None = None
    success: bool | None = None
    error_type: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        data["level"] = self.level.value
        data["action"] = self.action.value
        return data


class ObservabilityManager:
    """Manager for structured logging and observability."""
    
    def __init__(self):
        self._startup_time = datetime.utcnow()
        self._command_counts: dict[str, int] = {}
        self._error_counts: dict[str, int] = {}
        self._api_call_counts: dict[str, int] = {}
        self._health_status = {
            "database": False,
            "views_registered": False,
            "panel_registry_ready": False,
            "command_sync_done": False
        }
    
    def log_structured(
        self,
        level: LogLevel,
        action: ActionType,
        message: str,
        guild_id: int | None = None,
        user_id: int | None = None,
        details: dict[str, Any] | None = None,
        duration_ms: float | None = None,
        success: bool | None = None,
        error_type: str | None = None
    ):
        """Log a structured event."""
        entry = StructuredLogEntry(
            timestamp=datetime.utcnow(),
            level=level,
            action=action,
            guild_id=guild_id,
            user_id=user_id,
            message=message,
            details=details or {},
            duration_ms=duration_ms,
            success=success,
            error_type=error_type
        )
        
        # Log to standard logger with structured format
        log_data = entry.to_dict()
        
        # Choose appropriate log level
        log_method = {
            LogLevel.DEBUG: log.debug,
            LogLevel.INFO: log.info,
            LogLevel.WARNING: log.warning,
            LogLevel.ERROR: log.error,
            LogLevel.CRITICAL: log.critical
        }.get(level, log.info)
        
        log_method(f"[{action.value}] {message} | {json.dumps(log_data, separators=(',', ':'))}")
        
        # Update counters
        if action == ActionType.COMMAND:
            command_name = details.get("command", "unknown")
            self._command_counts[command_name] = self._command_counts.get(command_name, 0) + 1
        elif action == ActionType.ERROR:
            error_key = f"{error_type or 'unknown'}:{message}"
            self._error_counts[error_key] = self._error_counts.get(error_key, 0) + 1
        elif action == ActionType.API_CALL:
            api_operation = details.get("operation", "unknown")
            self._api_call_counts[api_operation] = self._api_call_counts.get(api_operation, 0) + 1
    
    def log_command(
        self,
        command_name: str,
        user: discord.User,
        guild: discord.Guild | None = None,
        success: bool = True,
        duration_ms: float | None = None,
        error: Exception | None = None
    ):
        """Log a command execution."""
        self.log_structured(
            level=LogLevel.INFO if success else LogLevel.ERROR,
            action=ActionType.COMMAND,
            message=f"Command {command_name} {'executed' if success else 'failed'}",
            guild_id=guild.id if guild else None,
            user_id=user.id,
            details={
                "command": command_name,
                "user_display_name": user.display_name
            },
            duration_ms=duration_ms,
            success=success,
            error_type=type(error).__name__ if error else None
        )
    
    def log_api_call(
        self,
        operation: str,
        success: bool,
        duration_ms: float,
        attempts: int,
        guild_id: int | None = None,
        user_id: int | None = None,
        error: Exception | None = None
    ):
        """Log an API call."""
        self.log_structured(
            level=LogLevel.INFO if success else LogLevel.WARNING,
            action=ActionType.API_CALL,
            message=f"API call {operation} {'succeeded' if success else 'failed'}",
            guild_id=guild_id,
            user_id=user_id,
            details={
                "operation": operation,
                "attempts": attempts
            },
            duration_ms=duration_ms,
            success=success,
            error_type=type(error).__name__ if error else None
        )
    
    def log_panel_operation(
        self,
        operation: str,
        panel_key: str,
        guild_id: int,
        success: bool,
        duration_ms: float | None = None,
        error: Exception | None = None
    ):
        """Log a panel operation."""
        self.log_structured(
            level=LogLevel.INFO if success else LogLevel.ERROR,
            action=ActionType.PANEL_DEPLOY if operation == "deploy" else ActionType.PANEL_REPAIR,
            message=f"Panel {operation} {panel_key} {'succeeded' if success else 'failed'}",
            guild_id=guild_id,
            details={
                "panel_key": panel_key,
                "operation": operation
            },
            duration_ms=duration_ms,
            success=success,
            error_type=type(error).__name__ if error else None
        )
    
    def log_ticket_operation(
        self,
        operation: str,
        ticket_number: int,
        guild_id: int,
        user_id: int,
        success: bool,
        duration_ms: float | None = None,
        error: Exception | None = None
    ):
        """Log a ticket operation."""
        self.log_structured(
            level=LogLevel.INFO if success else LogLevel.ERROR,
            action=ActionType.TICKET_CREATE if operation == "create" else ActionType.TICKET_CLOSE,
            message=f"Ticket {operation} #{ticket_number} {'succeeded' if success else 'failed'}",
            guild_id=guild_id,
            user_id=user_id,
            details={
                "ticket_number": ticket_number,
                "operation": operation
            },
            duration_ms=duration_ms,
            success=success,
            error_type=type(error).__name__ if error else None
        )
    
    def log_startup_event(
        self,
        component: str,
        status: str,
        details: dict[str, Any] | None = None
    ):
        """Log a startup event."""
        self.log_structured(
            level=LogLevel.INFO if status == "OK" else LogLevel.ERROR,
            action=ActionType.STARTUP,
            message=f"Startup component {component}: {status}",
            details=details or {"component": component, "status": status},
            success=status == "OK"
        )
        
        # Update health status - add new components dynamically
        self._health_status[component] = (status == "OK")
    
    def log_startup_complete(self, total_duration_ms: float):
        """Log complete startup summary."""
        all_healthy = all(self._health_status.values())
        
        self.log_structured(
            level=LogLevel.INFO if all_healthy else LogLevel.WARNING,
            action=ActionType.STARTUP,
            message=f"Startup complete in {total_duration_ms:.2f}ms - {'Healthy' if all_healthy else 'Issues detected'}",
            details={
                "duration_ms": total_duration_ms,
                "health_status": self._health_status,
                "components_healthy": sum(self._health_status.values()),
                "components_total": len(self._health_status)
            },
            duration_ms=total_duration_ms,
            success=all_healthy
        )
    
    def get_health_summary(self) -> dict[str, Any]:
        """Get health summary for monitoring."""
        uptime_ms = (datetime.utcnow() - self._startup_time).total_seconds() * 1000
        
        return {
            "uptime_ms": uptime_ms,
            "startup_time": self._startup_time.isoformat(),
            "health_status": self._health_status,
            "all_healthy": all(self._health_status.values()),
            "command_counts": dict(self._command_counts),
            "error_counts": dict(self._error_counts),
            "api_call_counts": dict(self._api_call_counts)
        }
    
    def get_error_summary(self) -> dict[str, Any]:
        """Get error summary for debugging."""
        return {
            "total_errors": sum(self._error_counts.values()),
            "error_types": dict(self._error_counts),
            "most_common_error": max(self._error_counts.items(), key=lambda x: x[1])[0] if self._error_counts else None
        }
    
    def reset_counters(self):
        """Reset all counters (useful for periodic cleanup)."""
        self._command_counts.clear()
        self._error_counts.clear()
        self._api_call_counts.clear()


# Global observability manager instance
observability = ObservabilityManager()


def log_command_execution(command_name: str):
    """Decorator to automatically log command execution."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            success = True
            error = None
            
            # Extract user and guild from interaction if available
            user = None
            guild = None
            
            for arg in args:
                if isinstance(arg, discord.Interaction):
                    user = arg.user
                    guild = arg.guild
                    break
            
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                success = False
                error = e
                raise
            finally:
                duration_ms = (time.time() - start_time) * 1000
                if user:
                    observability.log_command(
                        command_name=command_name,
                        user=user,
                        guild=guild,
                        success=success,
                        duration_ms=duration_ms,
                        error=error
                    )
        
        return wrapper
    return decorator


def log_api_operation(operation: str):
    """Decorator to automatically log API operations."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            success = True
            error = None
            attempts = 1  # This could be enhanced to track actual retry attempts
            
            # Extract context information
            guild_id = None
            user_id = None
            
            for arg in args:
                if isinstance(arg, discord.Guild):
                    guild_id = arg.id
                elif isinstance(arg, discord.Interaction):
                    guild_id = arg.guild.id if arg.guild else None
                    user_id = arg.user.id
                elif isinstance(arg, discord.Member):
                    guild_id = arg.guild.id
                    user_id = arg.id
                elif isinstance(arg, discord.User):
                    user_id = arg.id
            
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                success = False
                error = e
                raise
            finally:
                duration_ms = (time.time() - start_time) * 1000
                observability.log_api_call(
                    operation=operation,
                    success=success,
                    duration_ms=duration_ms,
                    attempts=attempts,
                    guild_id=guild_id,
                    user_id=user_id,
                    error=error
                )
        
        return wrapper
    return decorator


# Utility functions for common logging patterns
def log_error_with_context(error: Exception, context: dict[str, Any]):
    """Log an error with full context."""
    observability.log_structured(
        level=LogLevel.ERROR,
        action=ActionType.ERROR,
        message=str(error),
        guild_id=context.get("guild_id"),
        user_id=context.get("user_id"),
        details=context,
        error_type=type(error).__name__
    )


def log_health_check(component: str, is_healthy: bool, details: dict[str, Any] | None = None):
    """Log a health check result."""
    status = "OK" if is_healthy else "FAILED"
    observability.log_startup_event(component, status, details)


# Integration with existing logging
class StructuredLogHandler(logging.Handler):
    """Custom log handler that converts standard logs to structured format."""
    
    def emit(self, record):
        """Emit a log record."""
        try:
            # Extract structured data if present
            if hasattr(record, 'msg') and isinstance(record.msg, str) and record.msg.startswith('['):
                # Already structured, just log normally
                super().emit(record)
            else:
                # Convert to structured format
                observability.log_structured(
                    level=LogLevel(record.levelname),
                    action=ActionType.ERROR,
                    message=record.getMessage(),
                    details={
                        "module": record.module,
                        "function": record.funcName,
                        "line": record.lineno
                    }
                )
                super().emit(record)
        except Exception:
            # Fallback to standard logging
            super().emit(record)
