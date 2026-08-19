Apply the frozen ontology to each CURRENT observable event. Use only category IDs present in the ontology. Do not use the trajectory's overall outcome and do not invent categories.

For command, file, and tool events, assign `action` and `object`; `message_role` and `message_subject` must be null. For agent messages, assign `message_role` and `message_subject`; `action` and `object` must be null. Set `fit` to `exact`, `ambiguous`, or `no_fit`. For `ambiguous`, list category IDs in `alternatives`. For `no_fit`, use null labels and explain the missing concept.

Ontology:

{ontology}

Events:

{events}
