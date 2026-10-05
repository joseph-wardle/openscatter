import bpy

from .common.ops import DOCUMENTATION_URL, ISSUES_URL, TUTORIALS_URL, OpenUrlOperator
from .common.ui import BasePanel


class InfoPanel(BasePanel):
    bl_idname = "GSCATTER_PT_info"
    bl_label = "Info"
    bl_order = 200

    def draw_header(self, context: bpy.types.Context):
        self.layout.label(icon="HELP")

    def draw(self, context: bpy.types.Context):
        layout = self.layout

        op = layout.operator(
            OpenUrlOperator.bl_idname, text="Documentation", icon="HELP"
        )
        op.tooltip = "Read the original GScatter documentation by Graswald"
        OpenUrlOperator.configure(op, DOCUMENTATION_URL, "openDocumentationPage")

        op = layout.operator(OpenUrlOperator.bl_idname, text="Tutorials", icon="PLAY")
        op.tooltip = (
            "Search YouTube for GScatter tutorials, which also apply to OpenScatter"
        )
        OpenUrlOperator.configure(op, TUTORIALS_URL, "openTutorials")

        op = layout.operator(
            OpenUrlOperator.bl_idname, text="Report an Issue", icon="URL"
        )
        op.tooltip = "Report a bug or ask for help on OpenScatter's GitHub page"
        OpenUrlOperator.configure(op, ISSUES_URL, "openIssues")

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
