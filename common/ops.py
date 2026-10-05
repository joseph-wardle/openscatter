import bpy

from ..utils.getters import get_preferences
from .props import WindowManagerProps

# GScatter's documentation still applies, as the UI is unchanged. Its tutorial
# playlist is gone, so search for tutorials instead.
DOCUMENTATION_URL = "https://www.notion.so/graswald/Help-Support-Documentation-8822cee19a4944beb30bc6f80c6c699a"
TUTORIALS_URL = "https://www.youtube.com/results?search_query=gscatter+blender+tutorial"
ISSUES_URL = "https://github.com/joseph-wardle/openscatter/issues"


class OpenUrlOperator(bpy.types.Operator):
    """Open a URL in the browser"""

    bl_idname = "gscatter.url_open"
    bl_label = "Open URL"

    url: bpy.props.StringProperty(name="URL", options={"HIDDEN", "SKIP_SAVE"})
    event: bpy.props.StringProperty(name="Event", options={"HIDDEN", "SKIP_SAVE"})
    name: bpy.props.StringProperty(name="Name", options={"HIDDEN", "SKIP_SAVE"})
    value: bpy.props.StringProperty(name="Value", options={"HIDDEN", "SKIP_SAVE"})

    tooltip: bpy.props.StringProperty(default="Open URL in Browser.")

    @classmethod
    def description(cls, context, properties):
        return properties.tooltip

    def execute(self, context: bpy.types.Context) -> set:
        bpy.ops.wm.url_open(url=self.url)
        return {"FINISHED"}

    @staticmethod
    def configure(
        op: bpy.types.OperatorProperties,
        url: str,
        event: str,
        name: str = "",
        value: str = "",
    ):
        op.url, op.event, op.name, op.value = url, event, name, value


class CloseCompatibilityWarningOperator(bpy.types.Operator):
    """Closes Compatibility Warning"""

    bl_idname = "gscatter.close_compatibility_warning"
    bl_label = "OK"

    def execute(self, context: bpy.types.Context) -> set:
        wm_props: WindowManagerProps = context.window_manager.gscatter
        wm_props.compatibility_warning = True
        prefs = get_preferences()
        if wm_props.ignore_compatibility_warning:
            prefs.ignore_compatibility_warning = True
        bpy.ops.wm.save_userpref()
        return {"FINISHED"}


class ShowTutorialPopupOperator(bpy.types.Operator):
    bl_idname = "gscatter.show_tutorial_popup"
    bl_label = "Get Started With OpenScatter"

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.scale_y = 2
        op = col.operator(
            OpenUrlOperator.bl_idname,
            text="Find GScatter Tutorials on YouTube",
            icon="PLAY",
        )
        op.tooltip = (
            "Search YouTube for GScatter tutorials, which also apply to OpenScatter"
        )
        OpenUrlOperator.configure(op, TUTORIALS_URL, "openTutorials")
        col.separator(factor=0.5)
        op = col.operator(
            OpenUrlOperator.bl_idname,
            text="Or Read the GScatter Documentation",
            icon="HELP",
        )
        op.tooltip = "Read the original GScatter documentation by Graswald"
        OpenUrlOperator.configure(op, DOCUMENTATION_URL, "openDocumentationPage")
        layout.separator(factor=1)
        col = layout.column()
        col.scale_y = 0.8
        col.label(text="Dismiss this message permanently by clicking on OK.")
        col.label(text="Tutorials, documentation and issue reports are also in:")
        col.label(text="3D View > OpenScatter > Info")

    def invoke(self, context, event):
        return bpy.context.window_manager.invoke_props_dialog(self, width=350)

    def execute(self, context):
        prefs = get_preferences()
        prefs.show_tutorial_popup = False
        bpy.ops.wm.save_userpref()
        return {"FINISHED"}


classes = (
    OpenUrlOperator,
    CloseCompatibilityWarningOperator,
    ShowTutorialPopupOperator,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
