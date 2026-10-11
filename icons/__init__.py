import glob
import os
from pathlib import Path

from ..utils import startup
from ..utils.getters import get_library_dir
from ..utils.previews import Previews

folder = Path(__file__).parent
collection: Previews = None
all_icons = {}


def load_icons_from_folder(folder_path: str):
    for i in glob.glob(folder_path + "/*.bip"):
        no_ext = os.path.splitext(i)[0]
        file_name = os.path.basename(no_ext)
        all_icons[file_name] = Path(i).as_posix()


def get(name: str) -> int:
    """The icon_value of an icon, or 0 (no icon) if there isn't one by that name."""
    name = name.removesuffix(".bip") if name.endswith(".bip") else name
    icon = all_icons.get(name)
    if collection is None or icon is None:
        return 0
    return collection.get(icon).icon_id


def get_icon_path(name: str) -> int:
    name = name.removesuffix(".bip") if name.endswith(".bip") else name
    icon = all_icons.get(name)
    return icon


def get_all() -> list[str]:
    return all_icons.keys()


def is_custom(icon: str) -> bool:
    return icon.startswith("custom_")


def get_name_from_custom(icon: str) -> str:
    return icon.removeprefix("custom_").replace("_", " ").title()


def load_user_icons():
    store_path = get_library_dir().joinpath("icons")
    if store_path.exists():
        load_icons_from_folder(store_path.as_posix())


def register():
    global collection
    global all_icons
    collection = Previews(lazy=False)
    load_icons_from_folder(folder.as_posix())
    startup.add_callback(load_user_icons)


def unregister():
    collection.close()
