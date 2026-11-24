"""Check the released contract with the standard Draft2020-12 validator."""
import json
from pathlib import Path
from jsonschema import Draft202012Validator

ref=Path(__file__).resolve().parents[1]/'references'
schema=json.loads((ref/'project.schema.json').read_text())
Draft202012Validator.check_schema(schema)
Draft202012Validator(schema).validate(json.loads((ref/'restaurant.example.json').read_text()))
print('Draft2020-12 Schema and restaurant example PASS')
