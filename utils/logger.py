from rich.logging import RichHandler
from rich.traceback import install
import logging

install(show_locals=True)

FORMAT = "%(message)s"
logging.basicConfig(
    level="NOTSET", format=FORMAT, datefmt="[%X]", handlers=[RichHandler()]
)


LOGGER = logging.getLogger("rich")