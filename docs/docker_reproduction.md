# Docker Reproduction

The hardening phase reports Docker decision reproduction for the CRAG mock-API result. The reproduction class was decision-supporting rather than exact numeric reproduction: the governed winner, quality-only winner, result class, failure rate, and win/tie/loss matched, while some floating metrics differed.

Build:

```bash
docker build -t ragwarrant-governance:latest .
```

Publication validation:

```bash
docker run --rm ragwarrant-governance:latest make validate-publication
```

CRAG reproduction requires an external CRAG data mount:

```bash
docker run --rm \
  -v "/path/to/crag/raw:/data/crag/raw:ro" \
  -v "$PWD/results:/app/results" \
  ragwarrant-governance:latest \
  make reproduce-crag
```

Raw data are intentionally not baked into the image.
