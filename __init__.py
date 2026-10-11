# SPDX-FileCopyrightText: 2024 Graswald GmbH
# SPDX-FileCopyrightText: 2026 Joseph Wardle
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# OpenScatter, a fork of GScatter by Graswald GmbH. See NOTICE and LICENSE.

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
