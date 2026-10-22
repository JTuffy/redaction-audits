# Paper

LaTeX sources (NeurIPS 2025 style). The prose is written by hand; code writes only `generated/`.

- `uv run redaction paper watch` recompiles on every save and updates the site's Paper page, which reloads the PDF by itself.
- `uv run redaction paper build` compiles once. `uv run redaction paper tables` regenerates `generated/` from the frozen builds and the run ledger.
- In text, use the macros in `generated/numbers.tex` (`\LeakageTextRedaction`, `\PersistenceSelfRedaction`, ...) rather than typing numbers.

Compilation uses [Tectonic](https://tectonic-typesetting.github.io), which fetches LaTeX packages on first use. Output goes to `build/` (git-ignored).
