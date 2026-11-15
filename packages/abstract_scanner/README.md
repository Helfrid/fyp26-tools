# abstract-scanner

Screen PubMed abstracts with typed [Jev](https://docs.typesafe.ai) questions,
reproducibly and within a spend ceiling.

```bash
abstract-scanner validate -q question_sets/example.toml
abstract-scanner estimate -a pool.json -q question_sets/example.toml
abstract-scanner scan -a pool.json -q question_sets/example.toml \
    -o results.jsonl --budget 0.50 --cache .cache
```

`--budget` is required. The scan stops itself at the ceiling and leaves
partial results on disk; re-running the same command resumes.

Every run writes `<out>.manifest.json` recording the question-set
fingerprint, model id, token count and actual spend — without it, a later
comparison against ground truth cannot say what was asked.
