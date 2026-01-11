from __future__ import annotations

import contextvars
from typing import Any

# Context variable for tracking dry run mode
dry_run_var = contextvars.ContextVar('dry_run', default=False)

def is_dry_run() -> bool:
    """Check if currently in dry run mode."""
    return dry_run_var.get()

class dry_run_mode:
    """Context manager for temporarily enabling dry run mode."""
    
    def __init__(self):
        self.token = None
    
    def __enter__(self):
        self.token = dry_run_var.set(True)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        dry_run_var.reset(self.token)
