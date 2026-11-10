# Rule-based development baselines

The current reference is [rule-based-baseline-v3.json](rule-based-baseline-v3.json),
using the expanded 15-case suite. Reproduce it in the locked environment:

```powershell
python -m evals.run --verify reports/rule-based-baseline-v3.json
```

Preserved history:

| Report | Suite | Purpose |
|---|---|---|
| [rule-based-before.json](rule-based-before.json) | v1, 12 cases | Branch-1 summariser before MD&A correction |
| [rule-based-baseline.json](rule-based-baseline.json) | v1, 12 cases | After Nvidia MD&A correction, before the 8-K TOC correction |
| [8k-toc-before.json](8k-toc-before.json) | v2, 15 cases | Expanded suite evaluated before changing the 8-K selector |
| [rule-based-baseline-v2.json](rule-based-baseline-v2.json) | v2, 15 cases | After both section-selection fixes, under the original 37-package lock |
| [rule-based-baseline-v3.json](rule-based-baseline-v3.json) | v2, 15 cases | Same predictions under the 39-package PostgreSQL-enabled lock |

Compare reports on the same suite and environment; their hashes are recorded.
Do not compare aggregate percentages across differently sized suites as a quality
improvement claim. All reports retain predictions, check outcomes, slices and
source/environment identities. The current suite's two fallbacks are expected
empty/table-only cases. These short development diagnostics do not establish
production accuracy, proper 10-K support or LLM performance.

The original v1 manifest is preserved as `evals/cases-v1.json`; existing fixtures
are shared unchanged. Current references are agent-reviewed; human review remains
pending. The fixture provenance, acceptance plans, metrics and limitations live
in [evals/README.md](../evals/README.md). None of these cases is an untouched holdout.

Historical reports intentionally will not verify against changed code or the
expanded suite. Their recorded code and input hashes describe the earlier runs.
Current verification uses content hashes, not the current Git HEAD, so it remains
valid after committing unchanged source. The evaluation command refuses to
overwrite existing report files.

The three observed Amazon 8-K TOC failures are corrected. Short earnings
announcements still require exhibit ingestion for richer source content; Apple
10-Q narrative selection remains a separate quality gap. Follow-up ownership and
scope are recorded in [the project brief](../docs/problem.md#recorded-follow-up-gaps).

Upgrade 4 adds [PostgreSQL verification evidence](postgres-storage-v1.json). The
new summary report reflects a dependency-identity change, not a quality improvement.

Upgrade 5 adds [financial analytics verification](financial-analytics-v1.json):
synthetic numerical expectations, real PostgreSQL queries/imports and dashboard
rendering. This is integration evidence, not a human-reviewed accounting benchmark.

The [frozen portfolio demo verification](portfolio-demo-v1.json) records snapshot
precision/provenance parity, offline tab checks and Linux wheel hash verification.
It does not claim a completed hosted deployment or native Linux runtime check.
