import operator
from collections.abc import Callable, Iterable, Iterator, Mapping
from decimal import Decimal
from enum import Enum, auto
from typing import Final, Generic, Literal, NamedTuple, TypeAlias, TypeVar


class Location(NamedTuple):
    line: int
    column: int

    def __str__(self) -> str:
        return f"{self.line}:{self.column}"


class TokenType(Enum):
    NUMBER = auto()
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    NAME = auto()
    LPAREN = auto()
    RPAREN = auto()


class Token(NamedTuple):
    type: TokenType
    text: str
    location: Location


class SyntaxError(Exception):
    def __init__(self, msg: str, location: Location | None) -> None:
        super().__init__(f"{msg} at {location}" if location else msg)


class _Nothing(Enum):
    NOTHING = auto()


_NothingType = Literal[_Nothing.NOTHING]
_NOTHING: Final[_NothingType] = _Nothing.NOTHING

_T = TypeVar("_T")


class Peekable(Generic[_T], Iterator[_T]):
    def __init__(self, it: Iterable[_T]) -> None:
        self._it = iter(it)
        self._peeked: _T | _NothingType = _NOTHING

    def peek(self) -> _T | None:
        if self._peeked is not _NOTHING:
            return self._peeked
        self._peeked = next(self._it, _NOTHING)
        if self._peeked is not _NOTHING:
            return self._peeked
        return None

    def unpeek(self, val: _T) -> None:
        assert self._peeked is _NOTHING
        self._peeked = val

    def __iter__(self) -> Iterator[_T]:
        return self

    def __next__(self) -> _T:
        if self._peeked is not _NOTHING:
            val = self._peeked
            self._peeked = _NOTHING
        else:
            val = next(self._it)
        return val


_ONE_CHAR: Final[Mapping[str, TokenType]] = {
    "+": TokenType.PLUS,
    "-": TokenType.MINUS,
    "*": TokenType.STAR,
    "/": TokenType.SLASH,
    "(": TokenType.LPAREN,
    ")": TokenType.RPAREN,
}


def tokenize(text: str) -> Iterator[Token]:
    it = Peekable(text)
    line = col = 1

    for c in it:
        loc = Location(line, col)
        if c == "\n":
            line += 1
            col = 1
        else:
            col += 1

        if c.isspace():
            continue

        if c in _ONE_CHAR:
            yield Token(_ONE_CHAR[c], c, loc)
        elif c.isalpha():
            name = c
            for c2 in it:
                if not c2.isalnum() and c2 != "_":
                    it.unpeek(c2)
                    break
                col += 1
                name += c2
            yield Token(TokenType.NAME, name, loc)
        elif c.isnumeric() or c == ".":
            num = c
            has_dot = c == "."
            for c2 in it:
                if c2 == ".":
                    if has_dot:
                        raise SyntaxError("Number with multiple decimals", loc)
                    has_dot = True
                elif not c2.isnumeric():
                    it.unpeek(c2)
                    break
                col += 1
                num += c2
            yield Token(TokenType.NUMBER, num, loc)
        else:
            raise SyntaxError(f"Unexpected '{c}'", loc)


Env: TypeAlias = Mapping[str, Decimal]


def evaluate(raw_expr: str, env: Env | None = None) -> Decimal:
    return _evaluate_expr(env or {}, Peekable(tokenize(raw_expr)))


# The following is a Pratt "parser" except instead of parsing it evaluates the
# expression.


class _BinaryOp(NamedTuple):
    lbp: int
    operation: Callable[[Decimal, Decimal], Decimal]
    associativity: Literal["left", "right"] = "left"


class _UnaryOp(NamedTuple):
    rbp: int
    operation: Callable[[Decimal], Decimal]


def _undefined(*args):
    raise Exception("Operation not defined")


_BINARY_OPS: Final[Mapping[TokenType, _BinaryOp]] = {
    TokenType.RPAREN: _BinaryOp(0, _undefined),
    TokenType.PLUS: _BinaryOp(1, operator.add),
    TokenType.MINUS: _BinaryOp(1, operator.sub),
    TokenType.STAR: _BinaryOp(2, operator.mul),
    TokenType.SLASH: _BinaryOp(2, operator.truediv),
}

_UNARY_OPS: Final[Mapping[TokenType, _UnaryOp]] = {
    TokenType.LPAREN: _UnaryOp(0, lambda x: x),
    TokenType.MINUS: _UnaryOp(3, operator.neg),
}


def _evaluate_expr(env: Env, tokens: Peekable[Token], rbp: int = 0) -> Decimal:
    try:
        tok = next(tokens)
    except StopIteration:
        raise SyntaxError("Unexpected end of input", None)
    left = _nud(env, tokens, tok)
    while (tok := tokens.peek()) and (
        # If the token isn't a valid binop let _led handle the error
        tok.type not in _BINARY_OPS
        or rbp < _BINARY_OPS[tok.type].lbp
    ):
        left = _led(env, tokens, left, next(tokens))
    return left


def _nud(env: Env, tokens: Peekable[Token], token: Token) -> Decimal:
    if token.type == TokenType.NUMBER:
        return Decimal(token.text)
    elif token.type == TokenType.NAME:
        try:
            return env[token.text]
        except KeyError:
            raise SyntaxError(f"Unknown name '{token.text}'", token.location)
    elif token.type in _UNARY_OPS:
        op = _UNARY_OPS[token.type]
        result = op.operation(_evaluate_expr(env, tokens, op.rbp))
        if token.type == TokenType.LPAREN:
            rparen = next(tokens, None)
            if not rparen or rparen.type != TokenType.RPAREN:
                loc = (
                    rparen.location
                    if rparen
                    else token.location._replace(
                        column=token.location.column + len(token.text) + 1
                    )
                )
                raise SyntaxError("Expected right parenthesis", loc)
        return result
    else:
        raise SyntaxError(f"Unexpected '{token.text}'", token.location)


def _led(env: Env, tokens: Peekable[Token], left: Decimal, token: Token) -> Decimal:
    if token.type in _BINARY_OPS:
        op = _BINARY_OPS[token.type]
        right = _evaluate_expr(
            env, tokens, op.lbp if op.associativity == "left" else op.lbp - 1
        )
        return op.operation(left, right)
    else:
        raise SyntaxError(f"Unexpected '{token.text}'", token.location)
