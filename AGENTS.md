# Repository conventions

- Keep this skill portable: use paths relative to the skill or task workspace, never personal absolute paths.
- Preserve source vocabulary fields; model decisions belong in classification and page fields.
- Keep test and render outputs in `.work/`; do not commit caches, credentials, source datasets or generated documents.
- Validate changes with `python -B -m unittest discover -s tests -v`; run `tests/check_schema.py` when jsonschema is available.
- Image generation is separate from prompt preparation. Do not claim a generated image was verified from text-only checks.
- Keep release packaging free of `.git`, caches and generated outputs. Remote mutations follow the active user's authorization.
