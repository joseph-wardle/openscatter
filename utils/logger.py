import logging
import sys

SUCCESS_LEVEL_NUM = 25


class _Formatter(logging.Formatter):
    def format(self, record):
        # Named here rather than with logging.addLevelName, which would rename
        # level 25 for every logger in Blender.
        if record.levelno == SUCCESS_LEVEL_NUM:
            record.levelname = "SUCCESS"
        return super().format(record)


# Messages go up to the root logger like any library's, so whatever handles
# those (by default, Python prints warnings and errors) gets OpenScatter's too.
# Only developer mode adds a handler, to print everything to the console.
logger: logging.Logger = logging.getLogger(__name__)
logger.handlers.clear()  # from an earlier enable
_handler = logging.StreamHandler()
_handler.setFormatter(
    _Formatter("OpenScatter - %(filename)s:%(lineno)d - %(levelname)s: %(message)s")
)


def set_developer_mode(enabled: bool):
    """Print all of OpenScatter's messages in developer mode, otherwise leave
    them to the root logger's settings."""
    if enabled:
        logger.setLevel(logging.DEBUG)
        if _handler not in logger.handlers:
            logger.addHandler(_handler)
    else:
        logger.setLevel(logging.NOTSET)
        logger.removeHandler(_handler)


def debug(*args, sep=" ", end="\n"):
    """
    Debug function that works like print() but uses logging.info.
    - *args: Values to print.
    - sep: Separator between arguments (default: space).
    - end: String appended after the last value (default: newline).
    """
    msg = sep.join(map(str, args)) + end.strip("\n")  # Mimics print behavior
    logger.info(msg, stacklevel=2)


def info(*args, sep=" ", end="\n"):
    msg = sep.join(map(str, args)) + end.strip("\n")  # Mimics print behavior
    logger.info(msg)


def warn(*args, sep=" ", end="\n"):
    msg = sep.join(map(str, args)) + end.strip("\n")  # Mimics print behavior
    logger.warning(msg)


def success(*args, sep=" ", end="\n"):
    msg = sep.join(map(str, args)) + end.strip("\n")  # Mimics print behavior
    logger.log(SUCCESS_LEVEL_NUM, msg)


def error(*args, sep=" ", end="\n"):
    msg = sep.join(map(str, args)) + end.strip("\n")  # Mimics print behavior
    code = sys._getframe().f_back.f_code
    logger.error(
        f"\n{code.co_name} in {code.co_filename}:{code.co_firstlineno}>: {msg}",
        stacklevel=2,
    )


def register():
    pass


def unregister():
    set_developer_mode(False)
