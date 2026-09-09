"""Operational helpers with lazy imports.

The shadow pipeline imports the model replay code.  Importing it from the
package initializer created a cycle for the standalone research CLI, so keep
the public API while loading each operation only when requested.
"""

__all__ = ["create_backup", "shadow_run", "verify_backup", "generate_qa_baseline"]


def __getattr__(name):
    if name in {"create_backup", "verify_backup"}:
        from .backup import create_backup, verify_backup

        return {"create_backup": create_backup, "verify_backup": verify_backup}[name]
    if name == "shadow_run":
        from .shadow import shadow_run

        return shadow_run
    if name == "generate_qa_baseline":
        from .qa_baseline import generate_qa_baseline

        return generate_qa_baseline
    raise AttributeError(name)
