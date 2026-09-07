"""The roles of the crew, one module each, every one a plain function over the workspace.

Consultant (the brief), Scout (the inventory), Methodologist (the plan),
Analysts (the run), Critic (the review), Author (the report). Each has a
keyless behaviour and uses the model, when one is present, as stateless
calls with compact JSON. Nothing here is imported at package import time:
the Coordinator imports the role it needs when it needs it.
"""
