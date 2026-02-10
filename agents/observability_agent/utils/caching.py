"""
Caching Utility Module.

This module provides a robust caching mechanism for agent tools, storing results
in the agent's session state (`ToolContext` or `InvocationContext`).

Features:
- **Session-scoped caching**: Results are stored in the session state.
- **Automatic key generation**: Keys are generated based on tool name and arguments.
- **Statistics tracking**: Tracks hits, misses, and stores for optimization analysis.
- **Context-aware**: Handles both `InvocationContext` and `ToolContext`.
"""
import hashlib
import json
import logging
from functools import wraps
from typing import Any, Callable, Optional, Union
from google.adk.agents.invocation_context import InvocationContext
from google.adk.tools.tool_context import ToolContext

logger = logging.getLogger(__name__)


# Cache key prefix
CACHE_PREFIX = "SHARED_CACHE"

# Cache statistics (for optimization metrics)
_cache_stats = {
    "hits": 0,
    "misses": 0,
    "stores": 0
}

def get_cache_stats() -> dict:
    """
    Get current cache statistics (hits, misses, stores).
    
    Returns:
        dict: A dictionary containing 'hits', 'misses', 'stores', 'total_requests', and 'hit_rate_pct'.
    """
    total = _cache_stats["hits"] + _cache_stats["misses"]
    hit_rate = (_cache_stats["hits"] / total * 100) if total > 0 else 0
    return {
        **_cache_stats,
        "total_requests": total,
        "hit_rate_pct": round(hit_rate, 2)
    }

def reset_cache_stats():
    """Reset cache statistics."""
    _cache_stats["hits"] = 0
    _cache_stats["misses"] = 0
    _cache_stats["stores"] = 0

def _hash_params(*args, **kwargs) -> str:
    """Generate a stable hash for function parameters."""
    params_dict = {
        "args": args,
        "kwargs": kwargs
    }
    params_str = json.dumps(params_dict, sort_keys=True, default=str)
    return hashlib.md5(params_str.encode()).hexdigest()[:16]

def _get_cache_key(tool_name: str, *args, **kwargs) -> str:
    """Generate cache key for a tool call."""
    params_hash = _hash_params(*args, **kwargs)
    return f"{CACHE_PREFIX}_{tool_name}_{params_hash}"

def _get_state(ctx: Union[InvocationContext, ToolContext]) -> Optional[dict]:
    """Get the state dict from either InvocationContext or ToolContext."""
    if isinstance(ctx, ToolContext):
        return ctx.state
    elif hasattr(ctx, 'session') and hasattr(ctx.session, 'state'):
        return ctx.session.state
    elif hasattr(ctx, 'state'):
        return ctx.state
    return None

def get_from_cache(ctx: Union[InvocationContext, ToolContext], cache_key: str) -> Optional[Any]:
    """Retrieve value from cache."""
    try:
        state = _get_state(ctx)
        if state is not None:
            cached_value = state.get(cache_key)
            if cached_value is not None:
                _cache_stats["hits"] += 1
                logger.info(f"Cache HIT: {cache_key}")
                return cached_value
        
        _cache_stats["misses"] += 1
        logger.info(f"Cache MISS: {cache_key}")
        return None
    except Exception as e:
        logger.warning(f"Cache read error for {cache_key}: {e}")
        _cache_stats["misses"] += 1
        return None

def store_in_cache(ctx: Union[InvocationContext, ToolContext], cache_key: str, value: Any):
    """Store value in cache."""
    try:
        state = _get_state(ctx)
        if state is not None:
            state[cache_key] = value
            _cache_stats["stores"] += 1
            logger.info(f"Cache STORE: {cache_key}")
        else:
            logger.warning(f"Could not get state from context type: {type(ctx)}")
    except Exception as e:
        logger.warning(f"Cache write error for {cache_key}: {e}")

def cached_tool(tool_name: Optional[str] = None, session_scope: bool = True):
    """
    Decorator to add caching to async or sync tool functions.
    
    This decorator wraps a tool function to:
    1. Generate a unique cache key based on the function name and arguments.
    2. Check if the result is already in the session state.
    3. Return the cached result if found (Hit).
    4. Execute the function, store the result, and return it if not found (Miss).
    
    Args:
        tool_name (str, optional): Custom name for the tool (defaults to function name).
        session_scope (bool): Whether to store in session state (default: True).
    
    Usage:
        @cached_tool()
        async def my_tool(param1: str, tool_context: ToolContext = None) -> str:
            ...
    """
    def decorator(func: Callable):
        import inspect
        
        if inspect.iscoroutinefunction(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # Extract context from kwargs (prefer tool_context, fall back to ctx)
                ctx = kwargs.get('tool_context') or kwargs.get('ctx')
                if ctx is None:
                    # Try to find context in args
                    for arg in reversed(args):
                        if isinstance(arg, (InvocationContext, ToolContext)):
                            ctx = arg
                            break
                
                # If no context found, run without caching
                if ctx is None:
                    logger.warning(f"No InvocationContext/ToolContext found for {func.__name__}, skipping cache")
                    return await func(*args, **kwargs)
                
                # Verify we can access state
                state = _get_state(ctx)
                if state is None:
                    logger.warning(f"Cannot access state from context for {func.__name__}, skipping cache")
                    return await func(*args, **kwargs)
                
                # Generate cache key
                cache_name = tool_name or func.__name__
                
                # Filter out context from cache key parameters
                cache_args = tuple(
                    arg for arg in args 
                    if not isinstance(arg, (InvocationContext, ToolContext))
                )
                cache_kwargs = {
                    k: v for k, v in kwargs.items() 
                    if k not in ('ctx', 'tool_context') and not isinstance(v, (InvocationContext, ToolContext))
                }
                
                cache_key = _get_cache_key(cache_name, *cache_args, **cache_kwargs)
                
                # Try to get from cache
                cached_result = get_from_cache(ctx, cache_key)
                if cached_result is not None:
                    return cached_result
                
                # Cache miss - execute function
                result = await func(*args, **kwargs)
                
                # Store in cache
                if session_scope:
                    store_in_cache(ctx, cache_key, result)
                
                return result
            return wrapper
        else:
            @wraps(func)
            def wrapper(*args, **kwargs):
                # Extract context from kwargs (prefer tool_context, fall back to ctx)
                ctx = kwargs.get('tool_context') or kwargs.get('ctx')
                if ctx is None:
                    # Try to find context in args
                    for arg in reversed(args):
                        if isinstance(arg, (InvocationContext, ToolContext)):
                            ctx = arg
                            break
                
                # If no context found, run without caching
                if ctx is None:
                    logger.warning(f"No InvocationContext/ToolContext found for {func.__name__}, skipping cache")
                    return func(*args, **kwargs)
                
                # Verify we can access state
                state = _get_state(ctx)
                if state is None:
                    logger.warning(f"Cannot access state from context for {func.__name__}, skipping cache")
                    return func(*args, **kwargs)
                
                # Generate cache key
                cache_name = tool_name or func.__name__
                
                # Filter out context from cache key parameters
                cache_args = tuple(
                    arg for arg in args 
                    if not isinstance(arg, (InvocationContext, ToolContext))
                )
                cache_kwargs = {
                    k: v for k, v in kwargs.items() 
                    if k not in ('ctx', 'tool_context') and not isinstance(v, (InvocationContext, ToolContext))
                }
                
                cache_key = _get_cache_key(cache_name, *cache_args, **cache_kwargs)
                
                # Try to get from cache
                cached_result = get_from_cache(ctx, cache_key)
                if cached_result is not None:
                    return cached_result
                
                # Cache miss - execute function
                result = func(*args, **kwargs)
                
                # Store in cache
                if session_scope:
                    store_in_cache(ctx, cache_key, result)
                
                return result
            return wrapper
    return decorator

def clear_cache(ctx: Union[InvocationContext, ToolContext], pattern: Optional[str] = None):
    """Clear cache entries matching pattern."""
    try:
        state = _get_state(ctx)
        if state is None:
            logger.warning("Cannot access state for cache clearing")
            return
            
        if pattern is None:
            keys_to_delete = [k for k in state.keys() if k.startswith(CACHE_PREFIX)]
        else:
            keys_to_delete = [k for k in state.keys() if k.startswith(f"{CACHE_PREFIX}_{pattern}")]
        
        for key in keys_to_delete:
            del state[key]
        
        logger.info(f"Cleared {len(keys_to_delete)} cache entries")
    except Exception as e:
        logger.warning(f"Cache clear error: {e}")

async def get_cache_info(tool_context: ToolContext = None) -> str:
    """Tool to get cache statistics and information."""
    stats = get_cache_stats()
    
    info = {
        "cache_statistics": stats,
        "description": "Cache hit rate shows how many tool calls were eliminated by caching"
    }
    
    return json.dumps(info, indent=2)
