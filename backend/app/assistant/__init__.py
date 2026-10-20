"""Data360 assistant: answers questions about one client's data with server-side lookups.

The model never sees the database. It asks for facts through a small set of tools that run here,
only for the client whose AI switch is on, and every string sent to the model is redacted first
(names, identifiers, people, emails, phone numbers become tokens such as [CLIENT-1]). Answers are
de-tokenised before they are shown, so users see the real names.
"""
