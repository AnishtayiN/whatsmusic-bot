"""plugin_manager.py - Simple plugin system for adding new download services."""
import importlib.util
import inspect
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class Plugin:
    """Base class for all plugins."""
    name: str = 'base'
    description: str = 'پلاگین پایه'

    async def download(self, url: str, quality: int = 192) -> dict:
        raise NotImplementedError

    async def get_info(self, url: str) -> dict:
        raise NotImplementedError

    def is_supported(self, url: str) -> bool:
        raise NotImplementedError


class PluginManager:
    """Auto-load plugins from a directory."""

    def __init__(self, plugins_dir: str = 'plugins'):
        self.plugins_dir = Path(plugins_dir)
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        self._plugins: Dict[str, Plugin] = {}
        self._load_plugins()

    def _load_plugins(self) -> None:
        """Load all plugin modules from the plugins directory."""
        for py_file in self.plugins_dir.glob('*.py'):
            module_name = py_file.stem
            if module_name.startswith('_'):
                continue
            try:
                spec = importlib.util.spec_from_file_location(module_name, py_file)
                if spec is None or spec.loader is None:
                    continue
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (inspect.isclass(attr) and issubclass(attr, Plugin)
                            and attr is not Plugin and attr.__module__ == module.__name__):
                        plugin = attr()
                        self._plugins[plugin.name] = plugin
            except Exception as e:
                logger.warning(f'خطا در بارگذاری پلاگین {py_file.name}: {e}')

    def get_plugin(self, url: str) -> Optional[Plugin]:
        for plugin in self._plugins.values():
            try:
                if plugin.is_supported(url):
                    return plugin
            except Exception:
                continue
        return None

    def list_plugins(self) -> List[dict]:
        return [{'name': p.name, 'description': p.description} for p in self._plugins.values()]
