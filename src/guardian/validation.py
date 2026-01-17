from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .constants import ROLE_KINDS, CHANNEL_KINDS, COLORS

log = logging.getLogger("guardian.validation")


@dataclass
class ValidationError:
    """Validation error information."""
    field: str
    message: str
    severity: str  # "error", "warning", "info"


class ValidationResult:
    """Result of validation with errors and warnings."""
    
    def __init__(self) -> None:
        self.errors: List[ValidationError] = []
        self.warnings: List[ValidationError] = []
        self.info: List[ValidationError] = []
    
    def add_error(self, field: str, message: str) -> None:
        """Add an error."""
        self.errors.append(ValidationError(field, message, "error"))
    
    def add_warning(self, field: str, message: str) -> None:
        """Add a warning."""
        self.warnings.append(ValidationError(field, message, "warning"))
    
    def add_info(self, field: str, message: str) -> None:
        """Add an info message."""
        self.info.append(ValidationError(field, message, "info"))
    
    def is_valid(self) -> bool:
        """Check if there are no errors."""
        return len(self.errors) == 0
    
    def has_warnings(self) -> bool:
        """Check if there are warnings."""
        return len(self.warnings) > 0
    
    def get_summary(self) -> str:
        """Get a summary of validation results."""
        total = len(self.errors) + len(self.warnings) + len(self.info)
        if total == 0:
            return "✅ Validation passed with no issues"
        
        summary_parts = []
        if self.errors:
            summary_parts.append(f"❌ {len(self.errors)} errors")
        if self.warnings:
            summary_parts.append(f"⚠️ {len(self.warnings)} warnings")
        if self.info:
            summary_parts.append(f"ℹ️ {len(self.info)} info")
        
        return f"Validation complete: {', '.join(summary_parts)}"


class ConfigValidator:
    """Validate server configuration."""
    
    def validate_server_config(self, config: Dict[str, Any]) -> ValidationResult:
        """Validate server configuration."""
        result = ValidationResult()
        
        # Validate server name
        server_name = config.get("server_name", "")
        if not server_name:
            result.add_error("server_name", "Server name is required")
        elif len(server_name) > 100:
            result.add_warning("server_name", "Server name is very long (max 100 characters)")
        
        # Validate verification level
        verification_level = config.get("verification_level", "")
        valid_levels = ["none", "low", "medium", "high", "highest"]
        if verification_level not in valid_levels:
            result.add_error("verification_level", f"Invalid verification level. Must be one of: {', '.join(valid_levels)}")
        
        # Validate default notifications
        default_notifications = config.get("default_notifications", "")
        valid_notifications = ["all_messages", "only_mentions"]
        if default_notifications not in valid_notifications:
            result.add_error("default_notifications", f"Invalid default notifications. Must be one of: {', '.join(valid_notifications)}")
        
        # Validate content filter
        content_filter = config.get("content_filter", "")
        valid_filters = ["disabled", "members_without_roles", "all_members"]
        if content_filter not in valid_filters:
            result.add_error("content_filter", f"Invalid content filter. Must be one of: {', '.join(valid_filters)}")
        
        return result
    
    def validate_roles_config(self, roles: List[Dict[str, Any]]) -> ValidationResult:
        """Validate roles configuration."""
        result = ValidationResult()
        
        if not roles:
            result.add_warning("roles", "No roles configured")
            return result
        
        role_names = set()
        for i, role in enumerate(roles):
            role_name = role.get("name", "")
            
            # Validate role name
            if not role_name:
                result.add_error(f"roles[{i}].name", "Role name is required")
            elif len(role_name) > 100:
                result.add_error(f"roles[{i}].name", "Role name is too long (max 100 characters)")
            elif role_name in role_names:
                result.add_error(f"roles[{i}].name", f"Duplicate role name: {role_name}")
            else:
                role_names.add(role_name)
            
            # Validate color
            color = role.get("color", "")
            if not color:
                result.add_warning(f"roles[{i}].color", "No color specified, using default")
            elif color not in COLORS and color != "default":
                result.add_error(f"roles[{i}].color", f"Invalid color: {color}")
            
            # Validate kind
            kind = role.get("kind", "")
            if kind and kind not in ROLE_KINDS:
                result.add_error(f"roles[{i}].kind", f"Invalid role kind: {kind}")
            
            # Validate boolean fields
            hoist = role.get("hoist")
            if hoist is not None and not isinstance(hoist, bool):
                result.add_error(f"roles[{i}].hoist", "hoist must be a boolean")
            
            mentionable = role.get("mentionable")
            if mentionable is not None and not isinstance(mentionable, bool):
                result.add_error(f"roles[{i}].mentionable", "mentionable must be a boolean")
        
        return result
    
    def validate_categories_config(self, categories: List[Dict[str, Any]]) -> ValidationResult:
        """Validate categories configuration."""
        result = ValidationResult()
        
        if not categories:
            result.add_warning("categories", "No categories configured")
            return result
        
        category_names = set()
        for i, category in enumerate(categories):
            category_name = category.get("name", "")
            
            # Validate category name
            if not category_name:
                result.add_error(f"categories[{i}].name", "Category name is required")
            elif len(category_name) > 100:
                result.add_error(f"categories[{i}].name", "Category name is too long (max 100 characters)")
            elif category_name in category_names:
                result.add_error(f"categories[{i}].name", f"Duplicate category name: {category_name}")
            else:
                category_names.add(category_name)
            
            # Validate channels
            channels = category.get("channels", [])
            if not isinstance(channels, list):
                result.add_error(f"categories[{i}].channels", "Channels must be a list")
                continue
            
            channel_names = set()
            for j, channel in enumerate(channels):
                if not isinstance(channel, dict):
                    result.add_error(f"categories[{i}].channels[{j}]", "Channel must be a dictionary")
                    continue
                
                channel_name = channel.get("name", "")
                if not channel_name:
                    result.add_error(f"categories[{i}].channels[{j}].name", "Channel name is required")
                elif len(channel_name) > 100:
                    result.add_error(f"categories[{i}].channels[{j}].name", "Channel name is too long (max 100 characters)")
                elif channel_name in channel_names:
                    result.add_error(f"categories[{i}].channels[{j}].name", f"Duplicate channel name: {channel_name}")
                else:
                    channel_names.add(channel_name)
                
                # Validate channel kind
                kind = channel.get("kind", "")
                if kind and kind not in CHANNEL_KINDS:
                    result.add_error(f"categories[{i}].channels[{j}].kind", f"Invalid channel kind: {kind}")
                
                # Validate slowmode
                slowmode = channel.get("slowmode", 0)
                if not isinstance(slowmode, int) or slowmode < 0 or slowmode > 21600:
                    result.add_error(f"categories[{i}].channels[{j}].slowmode", "slowmode must be an integer between 0 and 21600")
        
        return result
    
        
    def validate_full_config(self, config: Dict[str, Any]) -> ValidationResult:
        """Validate the complete configuration."""
        result = ValidationResult()
        
        # Validate server settings
        server_result = self.validate_server_config(config)
        result.errors.extend(server_result.errors)
        result.warnings.extend(server_result.warnings)
        result.info.extend(server_result.info)
        
        # Validate roles
        roles = config.get("roles", [])
        roles_result = self.validate_roles_config(roles)
        result.errors.extend(roles_result.errors)
        result.warnings.extend(roles_result.warnings)
        result.info.extend(roles_result.info)
        
        # Validate categories
        categories = config.get("categories", [])
        categories_result = self.validate_categories_config(categories)
        result.errors.extend(categories_result.errors)
        result.warnings.extend(categories_result.warnings)
        result.info.extend(categories_result.info)
        
                
        # Cross-validation
        role_names = {role.get("name", "") for role in roles}
        category_names = {cat.get("name", "") for cat in categories}
        
        # Check for reserved names
        reserved_names = {"@everyone", "@here", "bot", "admin", "moderator"}
        for role_name in role_names:
            if role_name.lower() in reserved_names:
                result.add_warning("roles", f"Role name '{role_name}' may conflict with Discord built-in roles")
        
        # Check for reasonable limits
        if len(roles) > 250:
            result.add_warning("roles", f"Too many roles ({len(roles)}). Discord limit is 250")
        
        if len(categories) > 50:
            result.add_warning("categories", f"Too many categories ({len(categories)}). Discord limit is 50")
        
        total_channels = sum(len(cat.get("channels", [])) for cat in categories)
        if total_channels > 500:
            result.add_warning("categories", f"Too many channels ({total_channels}). Discord limit is 500")
        
        return result
