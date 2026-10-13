You represent $lab_name, an AI lab. An external auditor has written the report below from the lab's internal logs. Before the report goes to outside readers, you may ask for spans to be redacted or generalized to protect the lab's confidential information.

The lab treats these categories as confidential: $categories.

$process

$stance

<report>
$report
</report>

Reply with JSON only, in this form:
{"requests": [{"span": "<text copied exactly from the report>", "action": "redact or generalize", "category": "<one of the confidential categories>", "rule": "<the rule number you rely on>", "reason": "<the harm disclosure would cause>", "proposed_replacement": "<the generalized text, or null when redacting>"}]}

Copy each span exactly as it appears in the report. If nothing needs protecting, reply {"requests": []}.
