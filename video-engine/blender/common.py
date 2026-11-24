"""Utilitaires partagés par les scripts exécutés DANS Blender (bpy). Communication par JSON."""
import json
import sys


def args() -> dict:
    """Arguments passés après « -- » sous forme d'un JSON unique."""
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return json.loads(argv[0]) if argv else {}


def emit(kind: str, **data) -> None:
    """Ligne lue par le backend : « @@PROFIA {json} »."""
    print("@@PROFIA " + json.dumps({"type": kind, **data}, ensure_ascii=False), flush=True)


def engine_ids() -> dict:
    import bpy
    items = {i.identifier for i in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items}
    eevee = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in items else "BLENDER_EEVEE"
    return {"workbench": "BLENDER_WORKBENCH", "eevee": eevee, "cycles": "CYCLES"}
