# jev-client

Budget-guarded client for [Jev](https://docs.typesafe.ai) (`POST
https://api.typesafe.ai/v1/systemone`), TypeSafe's typed-question model.

Built on `httpx` rather than the vendor SDK so that `base_url` stays
swappable, every response is metered against a local spend ceiling, and the
test suite never touches the network.

```python
from jev_client import Budget, JevClient, noul

with JevClient(budget=Budget(max_usd=1.00)) as jev:
    answers = jev.ask(abstract, {"on_target": noul("Reports PPP1CC degradation")})
print(answers["on_target"].value)
```

Set `TYPESAFE_API_KEY` in `.env`, which is gitignored. Paste it there in your
editor rather than through an agent: session transcripts are written to disk.
Never commit it and never paste it into a notebook, a question set or a
results file.
