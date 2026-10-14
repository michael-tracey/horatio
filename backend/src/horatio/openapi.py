"""Print the API's OpenAPI spec, for generating the frontend's types:
`uv run python -m horatio.openapi > ../frontend/openapi.json`."""

import json

from horatio.app import app

if __name__ == "__main__":
    print(json.dumps(app.openapi(), indent=2, sort_keys=True))
