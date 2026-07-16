import json

import numpy as np

from app.modules.pipelines.runtime import json_safe


def test_json_safe_recursively_converts_numpy_values() -> None:
    payload = {
        "scores": np.asarray([0.91, 0.93]),
        "best": {
            "trial": np.int64(3),
            "parameters": [{"weights": np.asarray([[1, 2], [3, 4]])}],
        },
    }

    safe = json_safe(payload)

    assert safe == {
        "scores": [0.91, 0.93],
        "best": {
            "trial": 3,
            "parameters": [{"weights": [[1, 2], [3, 4]]}],
        },
    }
    json.dumps(safe)
