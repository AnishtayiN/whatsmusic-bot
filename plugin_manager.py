"""
سیستم پلاگین ساده برای افزودن سرویس‌های جدید
"""

import importlib
import inspect
from pathlib import Path
from typing import Dict, Type, Any

class Plugin:
    """کلاس پایه برای همه پلاگین‌ها"""
    name: str = "base"
    description: str = "پلاگین پایه"

    async def download(self, url: str, quality: int = 192) -> dict:
        raise NotImplementedError

    async def get_info(self, url: str) -> dict:
        raise NotImplementedError

    def is_supported(self, url: str) -> bool:
        raise NotImplementedError

class PluginManager:
    def __init__(self, plugins_dir: str = "plugins"):
        self.plugins_dir = Path(plugins_dir)
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        self._plugins: Dict[str, Plugin] = {}
        self._load_plugins()

    def _load_plugins(self):
        """بارگذاری خودکار پلاگین‌ها از دایرکتوری plugins"""
        for py_file in self.plugins_dir.glob("*.py"):
            module_name = py_file.stem
            if module_name.startswith("_"):
                continue
            try:
                spec = importlib.util.spec_from_file_location(module_name, py_file)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if inspect.isclass(attr) and issubclass(attr, Plugin) and attr is not Plugin:
                        plugin = attr()
                        self._plugins[plugin.name] = plugin
            except Exception as e:
                print(f"⚠️ خطا در بارگذاری پلاگین {py_file.name}: {e}")

    def get_plugin(self, url: str) -> Plugin | None:
        for plugin in self._plugins.values():
            if plugin.is_supported(url):
                return plugin
        return None

    def list_plugins(self) -> list:
        return [{"name": p.name, "description": p.description} for p in self._plugins.values()]