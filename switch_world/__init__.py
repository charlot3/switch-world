"""The switch-world composition root.

This package owns configuration loading and object construction. Keep this
module free of imports that trigger work: importing ``switch_world`` must not
read the environment or build the application.
"""
