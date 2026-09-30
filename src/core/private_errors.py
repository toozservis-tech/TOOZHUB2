"""Diagnostics without exception messages, SQL parameters, locals or file contents.

Exception text often contains credentials, document contents or personal records.
Keep only a random correlation ID, type and source locations. Do not use str/repr
or traceback.format_exception here, including for chained/provider exceptions.
"""
from pathlib import PurePath
import re
import sys
from uuid import uuid4


def incident_id(exc: BaseException) -> str:
    current = exc
    seen = set()
    for _ in range(12):
        if current is None or id(current) in seen:
            break
        seen.add(id(current))
        existing = getattr(current, '_private_incident_id', None)
        if isinstance(existing, str) and re.fullmatch(r'[a-f0-9]{32}', existing):
            return existing
        current = current.__cause__ or current.__context__
    result = uuid4().hex
    try:
        exc._private_incident_id = result
    except (AttributeError, TypeError):
        pass
    return result


def report_exception(exc: BaseException | None = None) -> str:
    """Log only safe diagnostics and return their opaque reference."""
    exc = exc if exc is not None else sys.exc_info()[1]
    if exc is None:
        exc = RuntimeError()
    reference = incident_id(exc)
    frames = []
    trace = exc.__traceback__
    while trace is not None:
        code = trace.tb_frame.f_code
        frames.append(f'{PurePath(code.co_filename).name}:{code.co_name}:{trace.tb_lineno}')
        trace = trace.tb_next
    print(f'[ERROR] incident={reference} kind={type(exc).__name__} locations={" > ".join(frames[-8:])}')
    return reference
