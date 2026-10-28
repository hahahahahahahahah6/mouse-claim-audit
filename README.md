# mouse-claim-audit

An offline static audit of documented synthetic pointer input against Python source calls. Source is parsed as AST and never executed. No dependencies are required at runtime.

Install and run:

```sh
python3 -m pip install .
mouse-claim-audit . --json
python3 -m mouse_claim_audit . --verbose
python3 -m unittest discover
python3 -m build
```

The positional argument is the repository root. Options: `--json` emits JSON; `--verbose` lists source evidence; repeatable `--ignore <glob>` excludes relative paths; `--fail-on {HIGH,MEDIUM}` sets the failure threshold (default HIGH); `--version` prints the version.

Findings carry rule identifiers `documented-mouse-claim-false` and `documented-no-mouse-claim-false`. A positive statement lacking production evidence is HIGH, or MEDIUM when evidence occurs only in tests. A negative statement contradicted by production evidence is HIGH. Each family yields at most one finding. No statement means PASS. Missing source contradicts a positive statement but agrees with a negative one. Exit codes: 0 for PASS, 2 when findings meet the threshold, 1 for usage or root access errors. MEDIUM findings remain visible at the default threshold.

Root README.md and Markdown under any docs path component supply statements. Fenced blocks are excluded; inline code counts. Paragraph lines join, case and hyphens are normalized, contractions expand, and exact word boundaries apply. Negative spans are removed before checking positive statements.

Production evidence comes from provider-resolved calls through pyautogui, pynput Mouse Controller instances, or autopy.mouse. Module and imported-name aliases are resolved per file. Controller assignment to a name or self attribute and chained construction are supported. Test files are assessed separately. Fixtures, docs, examples, and symlinked files are excluded from evidence. Environment files are never opened.

## Limitations

Only the exact phrase vocabulary encoded in the package constants is recognized. Bare nouns, user-facing click instructions, and descriptions of keyboard, screen capture, clipboard, voice, or network operations do not count. This tool checks program-driven pointer movement, not whether an action succeeds at runtime.

Shell pointer helpers such as xdotool and xte are outside scope. Strings, comments, listeners, widget handlers, and unrelated methods supply no evidence. Analysis is module-local and does not model runtime control flow, rebinding, dynamic imports, or inter-module Controller transfers. Invalid Python syntax is skipped. Static call presence does not establish reachability.
