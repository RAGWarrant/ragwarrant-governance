# Docker Reproduction

Build:

```bash
docker build -t ragwarrant-governance:latest .
```

Validate the publication bundle:

```bash
docker run --rm ragwarrant-governance:latest make validate-publication
```

Run CRAG reproduction with raw data mounted:

```bash
docker run --rm \
  -v "/path/to/crag/raw:/data/crag/raw:ro" \
  -v "$PWD/results:/app/results" \
  ragwarrant-governance:latest \
  make reproduce-crag
```

Raw CRAG data, credentials, and model weights are not included in the image.
