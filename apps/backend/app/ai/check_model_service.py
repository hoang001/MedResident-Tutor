"""Read-only service probes; no inference, model loading, retries or secret output."""

import asyncio
import json
import time

from app.ai.model_service import ModelServiceClient, ModelServiceError
from app.core.config import get_settings


async def check():
    try:
        client = ModelServiceClient(get_settings())
    except ModelServiceError as exc:
        print(json.dumps({"error": exc.code}))
        return 1
    except ValueError:
        print(json.dumps({"error": "MODEL_SERVICE_CONFIGURATION_INVALID"}))
        return 1
    failed = False
    for path, probe in (("/health", client.health), ("/ready", client.ready)):
        start = time.perf_counter()
        try:
            status = await probe()
            result = {"endpoint": client.base + path, "http_status": 200, **status}
        except ModelServiceError as exc:
            failed = True
            result = {
                "endpoint": client.base + path,
                "http_status": exc.upstream_status,
                "error": exc.code,
                "upstream_code": exc.upstream_code,
            }
        result["elapsed_seconds"] = round(time.perf_counter() - start, 3)
        print(json.dumps(result))
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(check()))
