from typing import Annotated

from pydantic import StringConstraints

# Non-empty text, surrounding whitespace removed. Invalid input is answered with 422 by FastAPI.
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]
