"""Decode real frames without an offscreen GPU presentation surface."""
from PySide6.QtMultimedia import QVideoSink


def headless_video(player):
    # The offscreen QPA plugin has no presentation device. Keep decoding,
    # metadata and subtitles real while avoiding QRhiWidget GPU presentation.
    if not hasattr(player, "test_sink"):
        player.test_sink = QVideoSink(player)
        player.player.setVideoOutput(player.test_sink)
    return player.test_sink
