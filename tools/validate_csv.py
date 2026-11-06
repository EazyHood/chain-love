from functools import lru_cache
from pathlib import Path
from typing import Iterator, Callable, List, Dict, FrozenSet
import os
import csv
import json
import re

URL_PATTERN = re.compile(r'https?://', re.IGNORECASE)

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.json"
BOOLEAN_VALUES = ("TRUE", "FALSE")

Rule = Callable[[Path, List[Dict[str, str]]], List[str]]

class CSVValidator:
    def __init__(self) -> None:
        self._rules: List[Rule] = []

    def add_rule(self, rule: Rule) -> None:
        self._rules.append(rule)

    def validate_file(self, path: Path) -> List[str]:
        errors: List[str] = []

        try:
            with path.open(newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
        except Exception as e:
            return [f"{path}: read error: {e}"]

        for rule in self._rules:
            errors.extend(rule(path, rows))

        return errors

def rule_slug_sorted(path: Path, rows: List[Dict[str, str]]) -> List[str]:
    if not rows:
        return []

    if "slug" not in rows[0]:
        return []

    errors: List[str] = []
    prev = None

    for idx, row in enumerate(rows, start=2):  # header = row 1
        slug = row.get("slug", "")
        if prev is not None and slug < prev:
            errors.append(
                f"{path}: row {idx}: slug ordering violation: '{slug}' must not appear after '{prev}' (ascending order required)"
            )
        prev = slug

    return errors

@lru_cache(maxsize=None)
def boolean_columns_by_file(schema_path: Path = SCHEMA_PATH) -> Dict[str, FrozenSet[str]]:
    """
    Maps a CSV file name (without .csv) to its boolean columns, read from schema.json.
    Category files share their name with a $defs entry; providers.csv rows become meta.providers.
    """
    with schema_path.open(encoding="utf-8") as f:
        defs = json.load(f)["$defs"]

    columns: Dict[str, FrozenSet[str]] = {}
    for name, definition in defs.items():
        boolean = set()
        for column, spec in definition.get("properties", {}).items():
            types = spec.get("type")
            if not isinstance(types, list):
                types = [types]
            if "boolean" in types:
                boolean.add(column)
        columns[name] = frozenset(boolean)

    columns["providers"] = columns.get("providerMeta", frozenset())
    return columns

def rule_boolean_values(path: Path, rows: List[Dict[str, str]]) -> List[str]:
    columns = boolean_columns_by_file().get(path.stem)
    if not columns:
        return []

    errors: List[str] = []

    for idx, row in enumerate(rows, start=2):  # header = row 1
        for column in sorted(columns):
            value = row.get(column)
            if value is None or value == "":
                continue  # blank: not set, or inherited from the canonical offer
            if value not in BOOLEAN_VALUES:
                errors.append(
                    f"{path}: row {idx}: column '{column}': boolean value must be TRUE or FALSE (uppercase), got '{value}'"
                )

    return errors

def looks_like_url(v: str) -> bool:
    return v.startswith("http://") or v.startswith("https://")

def rule_links_must_be_quoted(path: Path, rows: List[Dict[str, str]]) -> List[str]:
    errors: List[str] = []
    delimiter: str = ","

    with path.open(newline="", encoding="utf-8") as f:
        lines = f.readlines()
    
    if not lines:
        return []
    
    for raw_line in lines:
        line = raw_line.rstrip("\r\n")
        parts = line.split(delimiter)
        for i, cell in enumerate(parts):
            cell = cell.strip()
            if (
                not (cell.startswith('"') and cell.endswith('"'))
                and looks_like_url(cell)
            ):
                errors.append(
                    f"{path}: row {lines.index(raw_line) + 1}: column {i + 1}: URL '{cell}' must be quoted"
                )

    return errors

def iter_csv_files(root: Path) -> Iterator[Path]:
    for dirpath, _, filenames in os.walk(root):
        for name in sorted(filenames):
            if name.lower().endswith(".csv"):
                yield Path(dirpath) / name

def main():
    root = Path(".")

    validator = CSVValidator()
    validator.add_rule(rule_slug_sorted)
    validator.add_rule(rule_boolean_values)
    #validator.add_rule(rule_links_must_be_quoted)

    all_errors: List[str] = []

    for csv_file in iter_csv_files(root):
        errors = validator.validate_file(csv_file)
        all_errors.extend(errors)

    if all_errors:
        print("Validation errors:")
        for err in all_errors:
            print(f"  - {err}")
        exit(1)
    else:
        print("All checks passed.")
        exit(0)

if __name__ == "__main__":
    main()
