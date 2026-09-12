# Grounding accuracy: submodular vs top-k context selection

Source: real retrieval over 121 nodes for `elena`, traced in Phoenix project `grounding-eval`. Metric = fraction of gold facts placed into the selected context (a faithful answer can only ground in facts that were selected).

| case | gold | submodular | top-k | Δ |
|---|---|---|---|---|
| sunday-call | 2 | 50% | 100% | -50% |
| dinner-time | 2 | 100% | 50% | +50% |
| play-with-mateo | 2 | 50% | 0% | +50% |
| morning-garden | 2 | 100% | 50% | +50% |
| friday-plans | 2 | 100% | 0% | +100% |
| after-lunch-rest | 2 | 100% | 50% | +50% |
| **MEAN** | | **83.3%** | **41.7%** | **+41.7%** |
