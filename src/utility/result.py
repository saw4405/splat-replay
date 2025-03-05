from typing import Generic, TypeVar, Callable

T = TypeVar('T')
U = TypeVar('U')
E = TypeVar('E')


class Result(Generic[T, E]):
    def is_ok(self) -> bool:
        raise NotImplementedError

    def is_err(self) -> bool:
        raise NotImplementedError

    def unwrap(self) -> T:
        raise NotImplementedError

    def unwrap_err(self) -> E:
        raise NotImplementedError

    def map(self, func: Callable[[T], U]) -> 'Result[U, E]':
        if self.is_ok():
            return Ok(func(self.unwrap()))
        return self  # type: ignore

    def map_err(self, func: Callable[[E], E]) -> 'Result[T, E]':
        if self.is_err():
            return Err(func(self.unwrap_err()))
        return self  # type: ignore


class Ok(Result[T, E]):
    def __init__(self, value: T):
        self._value = value

    def is_ok(self) -> bool:
        return True

    def is_err(self) -> bool:
        return False

    def unwrap(self) -> T:
        return self._value

    def unwrap_err(self) -> E:
        raise Exception(f"Called unwrap_err on Ok({self._value})")

    def __repr__(self):
        return f"Ok({self._value})"


class Err(Result[T, E]):
    def __init__(self, error: E):
        self._error = error

    def is_ok(self) -> bool:
        return False

    def is_err(self) -> bool:
        return True

    def unwrap(self) -> T:
        raise Exception(f"Called unwrap on Err({self._error})")

    def unwrap_err(self) -> E:
        return self._error

    def __repr__(self):
        return f"Err({self._error})"
