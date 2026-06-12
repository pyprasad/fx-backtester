from abc import ABC, abstractmethod


class BaseStrategy(ABC):
    @abstractmethod
    def generate_signals(self, *args, **kwargs):
        raise NotImplementedError
