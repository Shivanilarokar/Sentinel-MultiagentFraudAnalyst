"""Pure SQL over the read-only database.

Repositories know the schema and nothing else. No language model, no prompt,
no formatting decisions - just parameterised queries returning plain dicts.
That separation is what lets the SQL be tested on its own, and it keeps the
tool layer above thin enough to read in one sitting.
"""
