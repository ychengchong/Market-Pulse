# Reproducible local environment

## Supported target

The verified target is **CPython 3.14.5 on Windows AMD64**, with pip 26.1.1.
`.python-version` records the interpreter version. `requirements.in` is the
editable list of five direct runtime dependencies; `requirements.txt` is the
complete generated artifact lock, including 39 direct/transitive packages and
one SHA-256 hash per resolved wheel. The lock contains no credentials or local
paths. `scripts/environment.py` checks the target, installed versions and whether
the input manifest still matches the lock.

This wheel lock is intentionally platform-specific. Do not claim it supports
Linux/macOS or another Python version; resolve and verify a separate lock for
those targets. Hashes verify selected distribution artifacts, not the Python
installer or operating system. Pinned packages are not a security certification.

## Fresh installation

Install CPython 3.14.5 first. From the repository root, use a **new** environment
without `--system-site-packages`. If `.venv` already exists, use a different name
or recreate it before following these commands:

```powershell
py -3.14 -m venv .venv
& .\.venv\Scripts\Activate.ps1
python --version
python -m pip install pip==26.1.1
python -m pip install --require-hashes -r requirements.txt
python -m pip check
python -m scripts.environment
python -B -m unittest discover -s tests -v
python -m evals.run --verify reports/rule-based-baseline-v3.json
```

The environment check refuses a different patch version or mismatched package
versions. Installation needs PyPI access or a previously prepared wheel cache;
the tests and baseline evaluation are offline. No paid API is needed.

Upgrade 2 was verified in a new environment under ignored `data/.venv-verify/`
with no access to system site-packages. The existing developer environment was
not used as proof of a clean installation. Native Streamlit AppTest prints a
bare-mode ScriptRunContext warning; it does not indicate a failed assertion.

## Deliberate dependency updates

Change `requirements.in`, then resolve in a clean environment on the supported
target with the pinned pip version:

```powershell
python -m pip install --dry-run --ignore-installed --only-binary=:all: --report data/dependency-resolution.json -r requirements.in
python -m scripts.lock_dependencies
```

The helper converts pip's actual resolution report into sorted pinned/hash-checked
requirements and checks that all direct pins are included. Do not generate hashes
from installed package files or invent lock entries. The raw report stays ignored
because it includes bulky upstream metadata. A future resolution may choose newer
transitive packages; the committed lock, not re-resolution, reproduces this build.

Install the new lock into another fresh environment, run `pip check`, regression
tests and a candidate evaluation. Preserve existing reports; select a new report
filename for an intentional baseline replacement. Evaluation refuses environment
mismatches rather than silently comparing different dependency sets.

`.gitattributes` keeps source, fixture and manifest line endings stable. Report
source-code hashes normalise line endings; dependency hashes cover actual wheels.
Git source revisions and code hashes are both recorded because local code may
not yet be committed. A matching run is deterministic for this local rule-based
component; future hosted LLM outputs need explicit nondeterminism and provider
identity records.
