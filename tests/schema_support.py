"""A validator for the part of JSON Schema that schema/world.schema.json uses, in the standard library: the schema is enforced by a test even where `jsonschema` is not
installed (the repository needs nothing outside the standard library). A keyword that it does not know is an error, not a silent pass, so it cannot be weaker than the schema it reads.
tests/test_world_schema.py checks it against `jsonschema` where that is installed. Not collected by pytest (the name has no test_ prefix)."""

import json
import re

ANNOTATIONS = {"$schema", "$defs", "title", "description", "$comment"}
KEYWORDS = {"$ref", "type", "const", "enum", "required", "properties", "additionalProperties", "items", "minItems", "maxItems", "uniqueItems", "minimum", "maximum", "minLength",
            "pattern", "not", "anyOf", "oneOf"}


def is_type(value, name: str) -> bool:
    if name == "null":
        return value is None
    if name == "boolean":
        return isinstance(value, bool)
    if name == "integer":
        return (isinstance(value, int) and not isinstance(value, bool)) or (isinstance(value, float) and value.is_integer())
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if name == "string":
        return isinstance(value, str)
    if name == "array":
        return isinstance(value, list)
    if name == "object":
        return isinstance(value, dict)
    raise ValueError(f"unknown type {name!r}")


def same(a, b) -> bool:
    return type(a) is type(b) and json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def resolve(root: dict, ref: str) -> dict:
    assert ref.startswith("#/"), ref
    node = root
    for part in ref[2:].split("/"):
        node = node[part]
    return node


def faults(instance, schema: dict, root: dict | None = None, path: str = "$") -> list[str]:
    """What is wrong with `instance` against `schema`: one line for each fault, with its place. Empty: it satisfies the schema."""
    root = schema if root is None else root
    unknown = set(schema) - KEYWORDS - ANNOTATIONS
    if unknown:
        raise ValueError(f"{path}: the validator does not know {sorted(unknown)}")
    out: list[str] = []
    if "$ref" in schema:
        out += faults(instance, resolve(root, schema["$ref"]), root, path)
    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(is_type(instance, t) for t in types):
            out.append(f"{path}: not of type {types}")
            return out
    if "const" in schema and not same(instance, schema["const"]):
        out.append(f"{path}: not {schema['const']!r}")
    if "enum" in schema and not any(same(instance, v) for v in schema["enum"]):
        out.append(f"{path}: not one of {schema['enum']}")
    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                out.append(f"{path}: missing {key}")
        props = schema.get("properties", {})
        for key, value in instance.items():
            if key in props:
                out += faults(value, props[key], root, f"{path}.{key}")
            elif schema.get("additionalProperties") is False:
                out.append(f"{path}: unknown {key}")
            elif isinstance(schema.get("additionalProperties"), dict):
                out += faults(value, schema["additionalProperties"], root, f"{path}.{key}")
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            out.append(f"{path}: fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            out.append(f"{path}: more than {schema['maxItems']} items")
        if schema.get("uniqueItems") and len({json.dumps(v, sort_keys=True) for v in instance}) != len(instance):
            out.append(f"{path}: an item twice")
        if "items" in schema:
            for i, value in enumerate(instance):
                out += faults(value, schema["items"], root, f"{path}[{i}]")
    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            out.append(f"{path}: shorter than {schema['minLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            out.append(f"{path}: does not match {schema['pattern']!r}")
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            out.append(f"{path}: less than {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            out.append(f"{path}: more than {schema['maximum']}")
    if "not" in schema and not faults(instance, schema["not"], root, path):
        out.append(f"{path}: matches what the schema forbids")
    if "anyOf" in schema and not any(not faults(instance, s, root, path) for s in schema["anyOf"]):
        out.append(f"{path}: matches none of anyOf")
    if "oneOf" in schema:
        matching = sum(1 for s in schema["oneOf"] if not faults(instance, s, root, path))
        if matching != 1:
            out.append(f"{path}: matches {matching} of oneOf, not one")
    return out


def valid(instance, schema: dict, root: dict | None = None) -> bool:
    return not faults(instance, schema, root)
