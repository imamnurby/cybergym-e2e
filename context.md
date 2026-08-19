# OpenAI-style `sk-` scan findings

Scope: all currently untracked `results_pi/**/trajectory/*.jsonl` (including `.session.jsonl`) identified by `git ls-files --others --exclude-standard`. Matches were read-only scanned with JSON line parsing; no complete secret values are included.

## Findings

All long matches below are in `message.content[0].thinkingSignature` (or corresponding `messages[*].content[0].thinkingSignature`). Their lengths (797–38,789) and placement in provider metadata, repeated verbatim between trajectory/session renderings, indicate **model output/signature metadata, not credentials**. Severity: **informational / no credential exposure established**.

- `results_pi/gpt-5.4/md4c_arvo_31332/20260816_111637_e2e/trajectory/attempt_1.jsonl`: lines **3835, 3846, 5980**; field `message.content[0].thinkingSignature` (line 5980 is `messages[68]...`); fingerprint `sk-8X…OkhA` (length 1593). Classification: model output/signature metadata; not an API credential.
- `results_pi/gpt-5.4/md4c_arvo_31332/20260816_111637_e2e/trajectory/attempt_1.session.jsonl`: lines **72**; `message.content[0].thinkingSignature`; same fingerprint `sk-8X…OkhA` (length 1593). Model output/signature metadata.
- `results_pi/gpt-5.4/miniz_arvo_26682/20260816_132947_e2e/trajectory/attempt_1.jsonl`: lines **10156, 10164, 17660**; `message.content[0].thinkingSignature` / `messages[140].content[0].thinkingSignature`; fingerprint `sk-nW…y-Kg` (length 797). Model output/signature metadata.
- `results_pi/gpt-5.4/miniz_arvo_26682/20260816_132947_e2e/trajectory/attempt_1.session.jsonl`: line **144**; `message.content[0].thinkingSignature`; same fingerprint `sk-nW…y-Kg` (length 797). Model output/signature metadata.
- `results_pi/gpt-5.4/spice-usbredir_arvo_36861/20260816_112448_e2e/trajectory/attempt_1.jsonl`: lines **5916, 5921, 13416, 13421, 15422**; `message.content[0].thinkingSignature` / `messages[93]` and `messages[139]`; fingerprints `sk-vl…8ksc` (length 17638) and `sk-b8…vNg_` (length 38789). Model output/signature metadata.
- `results_pi/gpt-5.4/spice-usbredir_arvo_36861/20260816_112448_e2e/trajectory/attempt_1.session.jsonl`: lines **97, 143**; corresponding `message.content[0].thinkingSignature`; fingerprints `sk-vl…8ksc` (length 17638) and `sk-b8…vNg_` (length 38789). Model output/signature metadata.

## Non-credential false positives

These also match the literal regex but are ordinary source/document text or prose, not credentials:

- `results_pi/gpt-5.4/md4c_arvo_31332/20260816_111637_e2e/trajectory/attempt_1.jsonl`: lines **348, 355, 356, 359**, `*.content[0].text`; fingerprints `sk-li…item` (length 12) and `sk-li…kbox` (length 21), HTML CSS class fragments (`task-list-item`, `task-list-item-checkbox`) in tool/model source output. Same `sk-li` occurrences appear in `.session.jsonl` line **18**.
- `results_pi/qwen-3.6-27b/md4c_arvo_31332/20260815_085731_e2e/trajectory/attempt_1.jsonl`: lines **310, 313, 314, 315, 22529**, `*.content[0].text`; same HTML fragments above, plus `sk-en…oded` (length 10), ordinary prose fragment from “asterisk-encoded”. `.session.jsonl`: lines **19, 129**, same fragments.
- `results_pi/qwen-3.6-27b/miniz_arvo_26682/20260814_162023_e2e/trajectory/attempt_1.jsonl`: lines **27180, 27183, 27190**, `assistantMessageEvent.content` / `message.content[0].thinking`; fingerprint `sk-ba…ased` (length 8), prose fragment from “masked base...” (word-boundary regex artifact). `.session.jsonl`: line **127**, same.

No occurrence was found in a JSON credential field, Authorization header, environment-variable value, prompt/example explicitly presenting an API key, or tool command. The long values are signature fields and should still be treated as sensitive provider metadata despite not resembling usable OpenAI API credentials.

```acceptance-report
{
  "criteriaSatisfied": [{"id":"criterion-1","status":"satisfied","evidence":"Read-only scan of every untracked results_pi trajectory/session JSONL found the concrete paths, 1-based lines, JSON fields, redacted fingerprints, classifications, and severity above."}],
  "changedFiles": [],
  "testsAddedOrUpdated": [],
  "commandsRun": [{"command":"git status --short --untracked-files=all","result":"passed","summary":"Identified untracked results_pi session/trajectory JSONL files."},{"command":"Python JSONL scan for sk-[A-Za-z0-9_-]+","result":"passed","summary":"Enumerated and classified matches without printing complete values."}],
  "validationOutput": ["No complete secret value printed; no staged or committed files."],
  "residualRisks": ["Long sk- prefixed thinkingSignature metadata remains present in untracked files; although not credentials, provider-side sensitivity cannot be ruled out."],
  "noStagedFiles": true,
  "diffSummary": "No project files modified; findings artifact only.",
  "reviewFindings": ["informational: long sk- matches are model thinkingSignature metadata, not credential fields", "no confirmed real OpenAI credential found"],
  "manualNotes": "Short matches are regex false positives in source/prose; trajectory and session duplicates are reported separately by exact line."
}
```
