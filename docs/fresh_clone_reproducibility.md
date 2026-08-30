# Fresh Clone Reproducibility

The fresh-clone drill checks whether a new checkout can install RAGWarrant, run the public-mini reproduction, run the finite governance job, and validate the publication bundle without private data, CRAG, HotpotQA cache, generator credentials, or secrets.

If GitHub network cloning is unavailable, the drill falls back to a clean tracked-file local copy and records `FRESH_CLONE_REPRODUCTION_PASSED_LOCAL_COPY` or a blocked class.
