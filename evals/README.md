# Filing development baselines

This is a fixed **development diagnostic suite**, not a final holdout or a
production-quality benchmark. The original v1 suite contains five adapted excerpts from locally
cached 10-Q filings (one per configured company) and seven synthetic cases for
8-K events, missing headings, section boundaries, table-only content, empty input
and the existing 10-K fallback. The v2 suite adds three cached Amazon 8-K excerpts
with repeated TOC/body item headings, bringing the current total to 15. The
original 12-case manifest is preserved as `cases-v1.json`; `cases.json` is current.
No provider calls or live downloads are needed.

## Review and provenance

References were inspected by Codex against the input paragraphs. Human review is
pending; no independently human-labelled corpus is claimed. Each real paragraph
has a source filing URL, accession, date, original clean-text digest and line
number. Surrounding structure is deliberately shortened and labelled adapted.
These local cached sources were not independently refetched for this suite.
Fixture hashes freeze exactly what was evaluated. Synthetic figures are invented.

All cases are development data. Once used to find or fix defects they cannot be
called an untouched confirmation set. Build and human-review separate cases before
final LLM-versus-rules quality claims. Keep reference answers out of future indexes.

## Plan fixed before the section-selection change

Hypothesis: choosing a real MD&A heading and its bounded section will recover the
Nvidia evidence lost by the last-phrase heuristic, without changing sentence
ranking. Fixed factors: the same 12 cases/references, four-sentence limit, scoring
rules and locked runtime. The planned change is only section boundary selection.

Acceptance: the Nvidia excerpt must include its reviewed financial evidence; the
section-boundary case must exclude market-risk figures; no previously passing
case may regress; all ingestion tests must still pass. Inspect the full cached
Nvidia filing separately, without using it as a quality holdout.

## Plan fixed before the 8-K TOC correction

The three newly observed Amazon cases are development regressions, not a new
holdout. Freeze their inputs and references before changing the selector. Record
the pre-fix predictions on all 15 cases. Hypothesis: distinguishing repeated
TOC/body item headings will recover their disclosure text without changing the
sentence-ranking rules. Require all three to include their reviewed evidence,
preserve the original 12 outcomes and pass the complete regression suite.
The main-document earnings announcement may remain short: exhibits are still
outside this branch's scope. Narrative quality work is also deferred.

## Reproduce

From the repository root in the locked environment:

```powershell
python -m evals.run --verify reports/rule-based-baseline-v2.json
```

To evaluate a future change without replacing the baseline:

```powershell
python -m evals.run --output data/candidate-evaluation.json
```

Existing output files are refused. All case errors remain in the denominator.
`--verify` fails if input, code, dependency identity, predictions or scores differ.
A candidate command exits nonzero on execution errors; a zero exit alone does
not mean its quality scores pass the acceptance criteria.

## Metrics and limitations

For every case, record event-type agreement, expected fallback behaviour, presence
of required verbatim evidence and exclusion of forbidden evidence. Report errors,
fallback counts and slices by form, company and input type. Verbatim evidence is
an extractive-baseline diagnostic, not a fair general scorer for paraphrased LLM
answers. Future LLM evaluation needs factual coverage and citation review as well.

Reports retain predictions, all check outcomes, fixture/suite hashes, normalised
source-code hashes, source revision, locked package versions, runtime target and
a run ID. Code hashes identify uncommitted code too; the source revision alone
must not be read as claiming a clean committed run. Timestamps vary across runs.
The runner does not read operational data/ files or alter dashboard outputs.
