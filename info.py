import bpy
from .utils.getters import get_allow_networking

from .common.ops import OpenUrlOperator
from .common.ui import BasePanel


class InfoPanel(BasePanel):
    bl_idname = "GSCATTER_PT_info"
    bl_label = "Info"
    bl_order = 200

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return get_allow_networking()

    def draw_header(self, context: bpy.types.Context):
        self.layout.label(icon="HELP")

    def draw(self, context: bpy.types.Context):
        layout = self.layout

        op = layout.operator(
            OpenUrlOperator.bl_idname, text="Help & Support", icon="HELP"
        )
        op.tooltip = "Read the original GScatter documentation by Graswald"
        url = "https://www.notion.so/graswald/Help-Support-Documentation-8822cee19a4944beb30bc6f80c6c699a"
        OpenUrlOperator.configure(op, url, "openDocumentationPage")

        op = layout.operator(
            OpenUrlOperator.bl_idname,
            text="Beginners Guide",
            icon="PLAY",
        )
        op.tooltip = "Watch the original GScatter tutorial playlist by Graswald"
        url = "https://youtube.com/playlist?list=PLOA3PJ1m8P7sIyw7bY2bYRqaS-sUTd7AZ"
        OpenUrlOperator.configure(op, url, "openGraswaldGscatterPlaylist")

        layout.separator()
        row = layout.row()
        row.alignment = "CENTER"
        row.label(text="Based on GScatter by Graswald GmbH")


classes = (InfoPanel,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
