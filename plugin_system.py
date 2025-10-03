# Plugin system scaffold for LM-Gambit
# Drop .py files in the plugins/ directory. Each should define a 'register' function.

import importlib.util
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).parent / "plugins"

class PluginManager:
    def __init__(self):
        self.plugins = []
        self.load_plugins()

    def load_plugins(self):
        if not PLUGIN_DIR.exists():
            return
        for file in PLUGIN_DIR.glob("*.py"):
            name = file.stem
            spec = importlib.util.spec_from_file_location(name, file)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                sys.modules[name] = mod
                spec.loader.exec_module(mod)
                if hasattr(mod, "register"):
                    self.plugins.append(mod)

    def run_hook(self, hook_name, *args, **kwargs):
        for plugin in self.plugins:
            hook = getattr(plugin, hook_name, None)
            if callable(hook):
                try:
                    hook(*args, **kwargs)
                except Exception as e:
                    print(f"Plugin {plugin.__name__} hook {hook_name} failed: {e}")
