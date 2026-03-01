from __future__ import annotations


def main() -> None:
  rows = [
    {"name": "Alice", "score": 80},
    {"name": "Bob"},
    {"name": "Carol", "score": 92},
  ]
  result = [
    x.get('name').upper()
    for x in rows
    if (score := x.get('score')) is not None and score >= 60
  ]
  print(result)
