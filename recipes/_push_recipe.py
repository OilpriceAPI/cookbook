"""Import shim for tests; the executable recipe keeps its numbered filename."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_path = Path(__file__).with_name("11_stop_polling_push.py")
_spec = spec_from_file_location("stop_polling_push", _path)
assert _spec and _spec.loader
_module = module_from_spec(_spec)
_spec.loader.exec_module(_module)

verify_signature = _module.verify_signature
