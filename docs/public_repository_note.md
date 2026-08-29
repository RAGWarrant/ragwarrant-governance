# Public Repository Note

This public repository is the canonical RAGWarrant repository. It was formerly published under the RAGTune name and was transferred and renamed through GitHub's native repository migration flow.

It intentionally does not include:

- raw CRAG datasets;
- raw CRAG question text;
- raw source documents;
- raw API responses;
- credentials or private local paths.

The historical validation ledger in `results/historical/` is a sanitized evidence summary, not a raw artifact dump. It preserves positive, negative, inconclusive, blocked, refused, and engineering-only findings without redistributing licensed dataset text. Historical identifiers may still contain the former RAGTune name where changing them would break provenance.
