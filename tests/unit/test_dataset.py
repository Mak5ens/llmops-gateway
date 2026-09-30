"""The benchmark dataset (benchmarks/dataset.jsonl): annotations point at their values, identifiers are valid."""

import json
import subprocess
import sys
from pathlib import Path

import phonenumbers
import pytest

BENCHMARKS = Path(__file__).resolve().parents[2] / "benchmarks"
ROWS = [json.loads(line) for line in (BENCHMARKS / "dataset.jsonl").read_text().splitlines()]
ENTITIES = [(row["id"], e) for row in ROWS for e in row["entities"]]


def digits(value: str) -> str:
    return "".join(c for c in value if c.isalnum())


def test_one_hundred_texts_of_ten_kinds():
    assert len(ROWS) == 100
    assert len({row["kind"] for row in ROWS}) == 10


def test_every_annotation_points_at_its_value():
    for row in ROWS:
        for e in row["entities"]:
            assert row["text"][e["start"] : e["end"]] == e["value"], row["id"]


def test_annotations_do_not_overlap():
    for row in ROWS:
        spans = sorted((e["start"], e["end"]) for e in row["entities"])
        assert all(end <= next_start for (_, end), (next_start, _) in zip(spans, spans[1:])), row["id"]


@pytest.mark.parametrize(("row_id", "entity"), [(i, e) for i, e in ENTITIES if e["type"] == "FR_NIR"])
def test_nir_key(row_id, entity):
    nir = digits(entity["value"])
    body = int(nir[:13].replace("2A", "19").replace("2B", "18"))
    assert 97 - body % 97 == int(nir[13:]), row_id


@pytest.mark.parametrize(("row_id", "entity"), [(i, e) for i, e in ENTITIES if e["type"] == "FR_FISCAL_NUMBER"])
def test_tax_number_key(row_id, entity):
    number = digits(entity["value"])
    assert int(number[:10]) % 511 == int(number[10:]), row_id


@pytest.mark.parametrize(("row_id", "entity"), [(i, e) for i, e in ENTITIES if e["type"] == "IBAN_CODE"])
def test_iban_check_digits(row_id, entity):
    iban = digits(entity["value"])
    rearranged = iban[4:] + iban[:4]
    assert int("".join(str(int(c, 36)) for c in rearranged)) % 97 == 1, row_id


@pytest.mark.parametrize(("row_id", "entity"), [(i, e) for i, e in ENTITIES if e["type"] == "CREDIT_CARD"])
def test_card_luhn(row_id, entity):
    numbers = [int(c) for c in digits(entity["value"])][::-1]
    total = sum(n if i % 2 == 0 else (n * 2 - 9 if n * 2 > 9 else n * 2) for i, n in enumerate(numbers))
    assert total % 10 == 0, row_id


@pytest.mark.parametrize(("row_id", "entity"), [(i, e) for i, e in ENTITIES if e["type"] == "PHONE_NUMBER"])
def test_phone_number_is_valid(row_id, entity):
    assert phonenumbers.is_valid_number(phonenumbers.parse(entity["value"], "FR")), row_id


def test_the_generator_gives_the_committed_file(tmp_path):
    # The same seed must give the same texts, or results.md would no longer match dataset.jsonl.
    script = (BENCHMARKS / "generate_dataset.py").read_text()
    copy = tmp_path / "generate_dataset.py"
    copy.write_text(script)
    subprocess.run([sys.executable, str(copy)], check=True, capture_output=True)
    assert (tmp_path / "dataset.jsonl").read_text() == (BENCHMARKS / "dataset.jsonl").read_text()
