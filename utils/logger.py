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


# The add-on's own logger and handler, so the root logger, which Blender and
# other add-ons share, is left alone.
logger: logging.Logger = logging.getLogger(__name__)
logger.handlers.clear()  # from an earlier enable
_handler = logging.StreamHandler()
_handler.setFormatter(
    _Formatter("OpenScatter - %(filename)s:%(lineno)d - %(levelname)s: %(message)s")
)
logger.addHandler(_handler)
logger.propagate = False
logger.setLevel(SUCCESS_LEVEL_NUM)


def update_log_level(level: int | str):
    """Callback to update log level."""
    logger.setLevel(level)
    logger.info(f"Log level updated to {level}")


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

