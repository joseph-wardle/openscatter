from . import ops, prefs, props, ui, callback

modules = (props, prefs, ops, ui, callback)


def register():
    for module in modules:
        module.register()


def unregister():
    for module in reversed(modules):
        module.unregister()
