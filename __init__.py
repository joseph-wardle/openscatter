#  * Copyright (C) 2024 Graswald GmbH - All Rights Reserved
#  * Modified 2026 by Joseph Wardle (OpenScatter, a fork of GScatter)
#  * You may use, distribute and modify this code under the
#  * terms of the GPLv3 license.
#  *
#  * You should have received a copy of the GPLv3 license with
#  * this file. If not, see <https://www.gnu.org/licenses/>.
#  *

from . import (
    asset_manager,
    common,
    slow_task_manager,
    effects,
    environment,
    icon_viewer,
    icons,
    info,
    extras,
    scatter,
    utils,
)

modules = (
    common,
    slow_task_manager,
    icons,
    scatter,
    icon_viewer,
    asset_manager,
    effects,
    utils,
    environment,
    extras,
    info,
)


def register():
    for module in modules:
        module.register()


def unregister():
    for module in reversed(modules):
        module.unregister()
