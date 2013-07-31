from holland.core.stream.plugin import StreamPlugin, StreamError
from holland.core.stream.interface import load_stream_plugin, StreamManager
from .interface import (open_stream, open_basedir,
                        available_methods, load_stream_plugin)

# ensure the compression implementations are loaded
import holland.core.stream.compression
