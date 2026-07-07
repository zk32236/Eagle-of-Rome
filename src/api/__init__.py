# src/api/__init__.py
from typing import Any, Dict, List, Optional

def api_response(success: bool, message: str = "", data: Any = None, errors: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    统一的API返回值格式
    """
    return {
        "success": success,
        "message": message,
        "data": data,
        "errors": errors or []
    }