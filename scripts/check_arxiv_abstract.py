#!/usr/bin/env python3
"""Check arXiv abstract length for the RAGWarrant preprint package."""
from pathlib import Path
import re
import sys

LIMIT = 1920
path = Path(__file__).resolve().parents[1] / "paper" / "arxiv" / "ABSTRACT.txt"
text = path.read_text(encoding="utf-8").strip()
normalized = re.sub(r"\r\n?", "\n", text)
count_including_spaces = len(normalized)
count_excluding_line_ending_normalization = len(text)
word_count = len(re.findall(r"\S+", normalized))
report = (
    f"characters_including_spaces: {count_including_spaces}\n"
    f"characters_excluding_line_ending_normalization: {count_excluding_line_ending_normalization}\n"
    f"word_count: {word_count}\n"
    f"limit: {LIMIT}\n"
)
(path.parent / "abstract_character_count.txt").write_text(report, encoding="utf-8")
print(f"arXiv abstract characters: {count_including_spaces}/{LIMIT}")
print(f"arXiv abstract words: {word_count}")
if count_including_spaces > LIMIT:
    print(f"ERROR: abstract exceeds arXiv limit by {count_including_spaces - LIMIT} characters", file=sys.stderr)
    sys.exit(1)
