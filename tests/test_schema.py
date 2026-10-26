"""The JSON Schema files of schema/ say what bibliopolis.inputs checks (they cannot say all of it: see docs/format.md)."""

import json
from pathlib import Path

import pytest

from bibliopolis import inputs

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = json.loads((ROOT / "schema" / "library.schema.json").read_text(encoding="utf-8"))
TREE = json.loads((ROOT / "schema" / "tree.schema.json").read_text(encoding="utf-8"))


def test_the_schemas_name_the_same_required_and_optional_fields_as_the_program():
    item = LIBRARY["$defs"]["item"]
    assert LIBRARY["required"] == ["items"] and TREE["required"] == ["nodes"]
    assert tuple(item["required"]) == inputs.LIBRARY_REQUIRED
    assert tuple(sorted(item["properties"])) == tuple(sorted((*inputs.LIBRARY_REQUIRED, *inputs.LIBRARY_OPTIONAL)))
    node = TREE["$defs"]["node"]
    assert tuple(node["required"]) == inputs.TREE_REQUIRED and tuple(sorted(node["properties"])) == tuple(sorted(inputs.TREE_REQUIRED))


def test_the_schemas_are_json_schema_documents_and_the_format_page_names_every_field():
    for schema in (LIBRARY, TREE):
        assert schema["$schema"].startswith("https://json-schema.org/") and schema["type"] == "object"
    page = (ROOT / "docs" / "format.md").read_text(encoding="utf-8")
    for name in (*inputs.LIBRARY_REQUIRED, *inputs.LIBRARY_OPTIONAL, *inputs.TREE_REQUIRED):
        assert f"`{name}`" in page, name


def test_the_example_files_satisfy_the_schemas_and_a_wrong_file_does_not():
    jsonschema = pytest.importorskip("jsonschema")
    tree = json.loads((ROOT / "examples" / "tree.json").read_text(encoding="utf-8"))
    library = json.loads((ROOT / "examples" / "library.json").read_text(encoding="utf-8"))
    jsonschema.validate(tree, TREE)
    jsonschema.validate(library, LIBRARY)
    for bad in ({"items": [{"id": "a"}]}, {"items": "x"}, {"items": [{**library["items"][0], "year": "2020"}]}, {"items": [{**library["items"][0], "topics": "a"}]}):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, LIBRARY)
    for bad in ({"nodes": [{"id": "a", "label": "A"}]}, {"nodes": [{"id": "a", "label": "", "parent": None}]}, {"nodes": {}}):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, TREE)
