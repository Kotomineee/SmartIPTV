"""Deliver worker results to the GUI thread, and discard closed-view callbacks."""
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot
from .client import ProviderError


class Work(QRunnable):
    def __init__(self, owner, token, function):
        super().__init__()
        self.owner, self.token, self.function = owner, token, function

    def run(self):
        try:
            value = self.function()
        except Exception as exc:
            message = str(exc) if isinstance(exc, ProviderError) else "Não foi possível concluir a operação. Tente novamente."
            self.owner.failed.emit(self.token, message)
        else:
            self.owner.succeeded.emit(self.token, value)


class Tasks(QObject):
    succeeded = Signal(int, object)
    failed = Signal(int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(4)
        self.callbacks = {}
        self.counter = 0
        self.succeeded.connect(self._success)
        self.failed.connect(self._failure)

    def submit(self, function, success, failure):
        self.counter += 1
        self.callbacks[self.counter] = (success, failure)
        self.pool.start(Work(self, self.counter, function))
        return self.counter

    def cancel(self, token):
        self.callbacks.pop(token, None)

    @Slot(int, object)
    def _success(self, token, result):
        callbacks = self.callbacks.pop(token, None)
        if callbacks:
            callbacks[0](result)

    @Slot(int, str)
    def _failure(self, token, message):
        callbacks = self.callbacks.pop(token, None)
        if callbacks:
            callbacks[1](message)

    def cancel_all(self):
        self.callbacks.clear()
        self.pool.clear()
