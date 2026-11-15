# Reference answer — `jev_client/CLAUDE.md`

*One reasonable answer to Part B of `docs/exercise-claude-md.md`. Read it
after you have written your own.*

---

## jev-client

Budget-guarded access to Jev, TypeSafe's typed-question model
(`POST https://api.typesafe.ai/v1/systemone`). Jev answers bounded, typed
questions about a piece of text and returns probabilities — it does not
generate prose, and nothing here should ever ask it to.

### What this package deliberately does not do

It does not use the vendor's `typesafe-sdk`. Everything goes through `httpx`
so that `base_url` stays swappable, every response passes through `Budget`,
and the tests can run against a mock transport. Adding the SDK would bypass
all three.

It also does not know anything about abstracts, papers or screening. Keep
domain knowledge in `abstract_scanner`; this package only knows how to ask
typed questions and account for what they cost.

### The rule about money

**Every network call must pass through `Budget.check()` before it is sent and
`Budget.record()` after it returns.** If you add a method that calls the API
without both, the spend ceiling silently stops working — and the first anyone
notices is the card statement.

### The non-obvious arithmetic in `Budget`

You would expect the pre-flight check to price the request from its own text.
That is not enough. The vendor bills the tokens it *processes*, which can be
much larger than the text we send, so a single oversized call can sail past a
ceiling that looked fine beforehand.

So `check()` projects the cost as the **larger** of (a) the character-based
estimate of this request and (b) `peak_request_usd`, the most expensive
request seen so far. The guard assumes the next call could cost as much as the
worst one yet, and tightens as it learns. The character estimate is
deliberately pessimistic — 3 characters per token, where real English is
nearer 4 — so it blocks early rather than late.

This was found by a test, not by reasoning: `test_budget_stops_a_runaway_loop`
originally overshot its ceiling by 26%.

### Testing

Tests run against `httpx.MockTransport`, so a real `JevClient` is exercised —
budget accounting, retries, caching, resume — without a network call.

**No test may make a network call or require an API key.** If you need a new
response shape, add a handler to the mock. If you ever find yourself wanting
to hit the real API in a test, that is a sign the thing you want to test
belongs behind an interface instead.

### Keys

`TYPESAFE_API_KEY` comes from the environment or `.env`. Never log it, never
include it in an error message, never write it into a results or cache file.
Construction fails loudly when it is missing — keep it that way, so a missing
key is never mistaken for an empty result.
