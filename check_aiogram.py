import aiogram
import inspect
from aiogram import Dispatcher

print(f"Aiogram version: {aiogram.__version__}")
try:
    print(f"Dispatcher init signature: {inspect.signature(Dispatcher.__init__)}")
except Exception as e:
    print(f"Could not get signature: {e}")

try:
    from aiogram.fsm.storage.memory import MemoryStorage
    print("Imported MemoryStorage from aiogram.fsm (v3)")
except ImportError:
    print("Could not import MemoryStorage from aiogram.fsm")

try:
    from aiogram.contrib.fsm_storage.memory import MemoryStorage
    print("Imported MemoryStorage from aiogram.contrib (v2)")
except ImportError:
    print("Could not import MemoryStorage from aiogram.contrib")
