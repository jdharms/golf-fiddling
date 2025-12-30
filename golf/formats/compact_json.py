"""
Compact JSON formatter that keeps arrays of numbers on single lines.
"""

import json


def dumps(obj, indent=2):
    """
    Serialize obj to a JSON formatted string.

    Arrays containing only numbers (int/float) are kept on a single line.
    Nested structures are indented normally.

    Args:
        obj: The object to serialize
        indent: Number of spaces for indentation (default: 2)

    Returns:
        A formatted JSON string
    """
    def is_primitive(v):
        return v is None or isinstance(v, (bool, int, float, str))

    def is_numeric_array(v):
        return isinstance(v, list) and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v)

    def format_value(v, level):
        pad = " " * (indent * level)
        child_pad = " " * (indent * (level + 1))

        if is_primitive(v):
            return json.dumps(v)

        elif is_numeric_array(v):
            return json.dumps(v)

        elif isinstance(v, list):
            if not v:
                return "[]"
            items = [format_value(x, level + 1) for x in v]
            inner = ",\n".join(child_pad + item for item in items)
            return "[\n" + inner + "\n" + pad + "]"

        elif isinstance(v, dict):
            if not v:
                return "{}"
            items = [f"{json.dumps(k)}: {format_value(val, level + 1)}" for k, val in v.items()]
            inner = ",\n".join(child_pad + item for item in items)
            return "{\n" + inner + "\n" + pad + "}"

        else:
            return json.dumps(v)

    return format_value(obj, 0)


def dump(obj, fp, indent=2):
    """
    Serialize obj to a JSON formatted stream.

    Args:
        obj: The object to serialize
        fp: A file-like object with a write() method
        indent: Number of spaces for indentation (default: 2)
    """
    fp.write(dumps(obj, indent))


def load(fp):
    """
    Wraps json.load for consistency.

    Args:
        fp: A file-like object with a read() method

    Returns:
        Deserialized Python object
    """
    return json.load(fp)


if __name__ == "__main__":
    # Demo
    test_data = {
        "name": "example",
        "tags": ["foo", "bar", "baz"],
        "rows": [
            [1, 2, 3, 4, 5],
            [6, 7, 8, 9, 10],
        ],
        "nested": {
            "values": [100, 200, 300],
            "deep": [
                [1, 1, 1],
                [2, 2, 2]
            ]
        }
    }
    print(dumps(test_data))
