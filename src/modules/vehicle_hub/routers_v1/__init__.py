"""Load the complete API only when bootstrap requests it.

Importing an auth dependency must not register every vehicle endpoint: vehicle
endpoints also import licensing dependencies, which otherwise creates a cycle.
The existing ``from routers_v1 import api_router`` entry point is preserved.
"""

__all__ = ["api_router"]


def __getattr__(name):
    if name != "api_router":
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from .registry import api_router

    globals()[name] = api_router
    return api_router
