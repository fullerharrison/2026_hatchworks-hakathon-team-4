# Historical v2 regression fixtures

These two frozen EDA outputs were recovered byte-for-byte from commit
`f937c454b336842ef3bf5b2aab132a3a0c5f8329`, rather than regenerated from the app code under test.
Original paths and SHA-256 values are recorded in `provenance.json`, together
with the matching supplied v2 archive fingerprint.

Commit `8974f13` retired the historical analysis reports, but app regression
tests still depended on their CSVs. Keeping the required oracles here preserves
those tests without reintroducing a superseded report as current analysis.
Do not regenerate these from application results to make a failing test pass.
The current candidate data and policy have separate tests and are unchanged.
