import json
import os
import tempfile
import threading
from pathlib import Path
from zipfile import ZipFile

import bpy
import requests
from bpy.props import (
    StringProperty,
    FloatProperty,
    BoolProperty,
    CollectionProperty,
    EnumProperty,
)
from bpy.types import OperatorProperties, UILayout

from ...utils import background, wrap_text
from ...utils.getters import (
    get_allow_networking,
    get_asset_browser_dir,
    get_preferences,
    get_user_library,
)
from ...utils.logger import error, success
from .. import previews, utils
from ..ops.misc import DummyOperator, SelectItemOperator
from ..ops.popup import OpenPreviewPopup
from .base import BaseWidget

FREE_ASSETS_JSON_LIST_URL = "https://asset-downloads.gscatter.com/file-downloads/gscatter/free-assets/asset-list"

ASSET = {"3D_PLANT": "Asset", "ENVIRONMENT": "Environment"}

TIMEOUT = (10, 60)  # seconds to connect, and to wait for each read


class FreeAssetWidget(BaseWidget):
    name: StringProperty(name="Name")
    icon: StringProperty(name="Icon")
    description: StringProperty(name="Description")
    asset_id: StringProperty(name="Asset ID")
    asset_type: EnumProperty(
        items=[
            ("3D_PLANT", "Plants", ""),
            ("ENVIRONMENT", "Environment", ""),
        ]
    )
    tags: CollectionProperty(name="Tags", type=BaseWidget)
    select: BoolProperty()
    expanded: BoolProperty(default=False)
    url: StringProperty(name="URL")
    total_size: StringProperty(name="Size")
    progress: FloatProperty(name="Progress", min=0, max=100, subtype="PERCENTAGE")
    downloading: BoolProperty()
    installing: BoolProperty()
    cancel_download: BoolProperty()

    def load(self, data: dict):
        self.name = data.get("name", "")
        self.url = data.get("url", "")
        self.asset_id = data.get("asset_id", "")
        self.description = data.get("description", "")
        self.asset_type = data.get("asset_type", "3D_PLANT")

        # Icons are downloaded with the list, so they're missing if that failed.
        icon = icon_path(icons_dir(), self.asset_id)
        self.icon = icon.as_posix() if icon.exists() else ""

    def icon_id(self) -> int:
        return previews.get(self.icon).icon_id if self.icon else 0

    def draw_gallery(self, layout: UILayout):
        box = layout.box()
        box.template_icon(
            icon_value=self.icon_id(), scale=utils.icon_scale_from_res(173)
        )
        row = layout.row(align=True)
        row.scale_y = 1.6
        library = self.parent
        op = row.operator(
            SelectItemOperator.bl_idname,
            text=self.name,
            depress=self.select,
            icon="CHECKMARK" if library.get_asset(self.asset_id) else "NONE",
        )
        op.target, op.deselect = repr(self), False

    def draw_compact(self, layout: UILayout):
        library = self.parent
        if self.asset_type == "3D_PLANT" and library.get_asset(self.asset_id):
            return
        elif self.asset_type == "ENVIRONMENT" and library.get_environment_by_id(
            self.asset_id
        ):
            return
        elif self.asset_type == "ENVIRONMENT" and library.get_environment_by_name(
            self.name
        ):
            return

        col = layout.column(align=True)
        col.box().prop(
            self,
            "expanded",
            toggle=True,
            text=self.name + f" - [{ASSET[self.asset_type]}]",
            emboss=False,
            icon="TRIA_RIGHT" if not self.expanded else "TRIA_DOWN",
        )
        if self.expanded:
            self.draw_details(col.box())

    def draw_details(self, layout: UILayout):
        main_col = layout.column(align=True)

        box = main_col.box()
        box.template_icon(
            icon_value=self.icon_id(), scale=utils.icon_scale_from_res(250)
        )

        row = main_col.box().row()
        row.operator(
            DummyOperator.bl_idname, text=self.name, emboss=False, depress=True
        )
        row.operator(
            OpenPreviewPopup.bl_idname, text="", icon="SEQ_PREVIEW"
        ).icon_id = repr(self.icon_id())

        box = main_col.box()
        text_col = box.column(align=True)
        text_col.scale_y = 0.8
        for text in wrap_text(self.description, bpy.context.region.width):
            text_col.label(text=text)

        box = main_col.box()
        box.label(text=f"Type: {ASSET[self.asset_type]}")

        main_col.separator()
        col = main_col.column()
        col.scale_y = 2.0
        library = self.parent

        if not self.downloading:
            if self.asset_type == "3D_PLANT" and library.get_asset(self.asset_id):
                col.operator(
                    DummyOperator.bl_idname,
                    text="Asset is Installed.",
                    emboss=False,
                    depress=True,
                )
            elif self.asset_type == "ENVIRONMENT" and library.get_environment_by_id(
                self.asset_id
            ):
                col.operator(
                    DummyOperator.bl_idname,
                    text="Asset is Installed.",
                    emboss=False,
                    depress=True,
                )
            else:
                if library.loading_free_assets:
                    c = col.column()
                    c.enabled = False
                    c.scale_y = 0.5
                    c.label(text="Cannot download while assets are loading.")
                op: OperatorProperties = col.operator(
                    DownloadFreeAssetOperator.bl_idname, text="Download"
                )
                op.asset_id = self.asset_id
        else:
            row = col.row()
            row.enabled = False

            if not self.installing:
                row.prop(
                    self, "progress", slider=True, text=f"Downloading {self.total_size}"
                )
                row = col.row()
                row.prop(
                    self,
                    "cancel_download",
                    text="Cancel Download",
                    toggle=True,
                    emboss=False,
                )
            else:
                row.operator(
                    DummyOperator.bl_idname,
                    text="Installing Asset...",
                    emboss=True,
                    depress=True,
                )


class DownloadFreeAssetOperator(bpy.types.Operator):
    bl_idname = "gscatter.download_free_asset"
    bl_label = "Download"
    bl_description = "Download this free asset from Graswald and add it to your library"

    asset_id: StringProperty()  # type: ignore

    @classmethod
    def poll(cls, context):
        if not get_allow_networking():
            cls.poll_message_set(
                "Allow Online Access in Blender's System preferences to download"
            )
            return False
        library = context.window_manager.gscatter.library
        return not library.loading_free_assets

    def execute(self, context):
        asset = find_free_asset(self.asset_id)
        if asset is None:
            return {"CANCELLED"}
        if asset.downloading:
            self.report({"WARNING"}, message="Already Downloading. Cancelled.")
            return {"CANCELLED"}

        folder = "Environments" if asset.asset_type == "ENVIRONMENT" else "Assets"
        extract_dir = utils.user_library().joinpath(folder)
        asset_browser_dir = None
        if get_preferences().enable_experimental_features:
            asset_browser_dir = get_asset_browser_dir(context)

        asset.downloading = True
        asset.installing = False
        asset.cancel_download = False
        asset.progress = 0

        asset_id = self.asset_id
        url, name, asset_type = asset.url, asset.name, asset.asset_type
        state = DownloadState()

        def work():
            install(url, extract_dir, name, asset_type, asset_browser_dir, state)

        def on_tick():
            # The asset is looked up each time, as reloading the library
            # replaces it.
            asset = find_free_asset(asset_id)
            if asset is None or asset.cancel_download:
                state.cancel.set()
            if asset is not None:
                asset.total_size = state.total_size
                asset.progress = state.progress
                asset.installing = state.installing

        def on_done(_result, exception):
            asset = find_free_asset(asset_id)
            if asset is not None:
                asset.downloading = False
                asset.installing = False
                asset.cancel_download = False
                asset.progress = 0

            if isinstance(exception, DownloadCancelled):
                return
            if exception is not None:
                error(exception, f"Couldn't download {name}")
                return

            success(f"Installed {name}")
            utils.load_library()
            if not bpy.app.background:
                bpy.ops.gscatter.popup_message(
                    "INVOKE_DEFAULT", message="Asset Installed", width=200
                )

        background.run(work, on_done, on_tick)
        return {"FINISHED"}


def find_free_asset(asset_id: str):
    library = bpy.context.window_manager.gscatter.library
    return next((a for a in library.free_assets if a.asset_id == asset_id), None)


def icons_dir() -> Path:
    path = get_user_library(bpy.context).joinpath("icons")
    path.mkdir(exist_ok=True)
    return path


def icon_path(icons: Path, asset_id: str) -> Path:
    return icons.joinpath(asset_id + ".bip")


# Everything below runs on download threads, so it mustn't touch Blender's data.


class DownloadCancelled(Exception):
    pass


class DownloadState:
    """A download's progress, shared between its thread and the interface."""

    def __init__(self):
        self.total_size = ""
        self.progress = 0.0
        self.installing = False
        self.cancel = threading.Event()


def request_download(url: str) -> requests.Response:
    """Request a file, following Graswald's JSON reply that holds the real URL."""
    response = requests.get(url, stream=True, timeout=TIMEOUT)
    response.raise_for_status()
    if response.headers.get("content-type") != "application/json":
        return response

    json_data = response.json()
    download_url = (json_data.get("data") or {}).get("downloadUrl")
    if not download_url:
        return response

    response = requests.get(download_url, stream=True, timeout=TIMEOUT)
    response.raise_for_status()
    return response


def download_file(url: str, destination: Path, state: DownloadState = None):
    """Download url to destination, which is only written once it's complete."""
    partial = destination.with_name(destination.name + ".part")
    with request_download(url) as response, open(partial, "wb") as file:
        total_size = int(response.headers.get("content-length", 0))
        if state is not None:
            state.total_size = utils.convert_size(total_size)
        done = 0
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if state is not None and state.cancel.is_set():
                raise DownloadCancelled()
            file.write(chunk)
            done += len(chunk)
            if state is not None and total_size:
                state.progress = min(done / total_size * 100, 100)
    os.replace(partial, destination)


def install(
    url: str,
    extract_dir: Path,
    name: str,
    asset_type: str,
    asset_browser_dir: Path,
    state: DownloadState,
):
    """Download an asset's zip into the library, and add it to the asset browser
    if asset_browser_dir is given."""
    with tempfile.TemporaryDirectory() as temp_dir:
        zip_path = Path(temp_dir, os.path.basename(url) or "asset.zip")
        download_file(url, zip_path, state)
        state.installing = True

        extract_dir.mkdir(parents=True, exist_ok=True)
        before = set(os.listdir(extract_dir))
        with ZipFile(zip_path, "r") as file:
            file.extractall(extract_dir)

    if asset_browser_dir is None:
        return
    new_folders = [f for f in os.listdir(extract_dir) if f not in before]
    asset_dir = extract_dir.joinpath(new_folders[0] if new_folders else name)
    product_data = json.loads(asset_dir.joinpath("product.json").read_text())
    utils.create_asset_browser_entry(
        None,
        product_data.get("name", name),
        product_data,
        asset_type.upper(),
        asset_dir,
        asset_browser_dir=asset_browser_dir,
    )


def read_free_assets_list() -> dict:
    """The list of free assets saved by the last successful download."""
    path = get_asset_browser_dir().joinpath("free_assets.json")
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def fetch_free_assets(on_done):
    """Download the list of free assets and their icons in the background, then
    call on_done(data). If the download fails, data is the saved list."""
    list_path = get_asset_browser_dir().joinpath("free_assets.json")
    icons = icons_dir()

    def work():
        with request_download(FREE_ASSETS_JSON_LIST_URL) as response:
            data = response.json()
        for asset_data in data.get("assets", []):
            asset_id, url = asset_data.get("asset_id"), asset_data.get("icon")
            if not asset_id or not url or icon_path(icons, asset_id).exists():
                continue
            try:
                download_file(url, icon_path(icons, asset_id))
            except (requests.RequestException, OSError):
                pass  # The asset is listed without an icon.
        list_path.write_text(json.dumps(data))
        return data

    def finish(data, exception):
        if exception is not None:
            error(exception, "Couldn't download the list of free assets")
            data = read_free_assets_list()
        on_done(data)

    background.run(work, finish)


classes = (
    FreeAssetWidget,
    DownloadFreeAssetOperator,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
