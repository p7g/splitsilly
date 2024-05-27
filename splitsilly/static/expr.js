export class Location {
    constructor(line, column) {
        this.line = line;
        this.column = column;
    }

    toString() {
        return `${this.line}:${this.column}`;
    }
}

export const TokenType = Object.freeze({
    NUMBER: "NUMBER",
    PLUS: "PLUS",
    STAR: "STAR",
    SLASH: "SLASH",
    NAME: "NAME",
    LPAREN: "LPAREN",
    RPAREN: "RPAREN",
});

export class Token {
    constructor(type, text, location) {
        this.type = type;
        this.text = text;
        this.location = location;
    }
}

export class SyntaxError extends Error {
    constructor(msg, location) {
        super(location ? `${msg} at ${location}` : msg);
    }
}

const NOTHING = {};

function* iter(iterable) {
    for (const element of iterable) yield element;
}

class Peekable {
    constructor(it) {
        this._it = iter(it);
        this._peeked = NOTHING;
    }

    peek() {
        if (this._peeked !== NOTHING) return this._peeked;
        const next = this._it.next();
        this._peeked = next.done ? NOTHING : next.value;
        if (this._peeked !== NOTHING) return this._peeked;
        return null;
    }

    unpeek(val) {
        if (this._peeked !== NOTHING) throw new Error();
        this._peeked = val;
    }

    [Symbol.iterator]() {
        return this;
    }

    next() {
        let val;
        if (this._peeked !== NOTHING) {
            val = { value: this._peeked, done: false };
            this._peeked = NOTHING;
        } else {
            val = this._it.next();
        }
        return val;
    }
}

const oneChar = Object.freeze({
    "+": TokenType.PLUS,
    "-": TokenType.MINUS,
    "*": TokenType.STAR,
    "/": TokenType.SLASH,
    "(": TokenType.LPAREN,
    ")": TokenType.RPAREN,
});
const isSpace = /\s/;
const isAlpha = /[a-zA-Z]/;
const isAlnum = /[a-zA-Z0-9]/;
const isNumeric = /[0-9]/;

export function* tokenize(text) {
    const it = new Peekable(text);
    let line = 1, col = 1;

    for (const c of it) {
        const loc = new Location(line, col);
        if (c === "\n") {
            line += 1;
            col = 1;
        } else {
            col += 1;
        }

        if (c.match(isSpace)) {
            continue;
        }

        if (c in oneChar) {
            yield new Token(oneChar[c], c, loc);
        } else if (c.match(isAlpha)) {
            let name = c;
            for (const c2 of it) {
                if (!c2.match(isAlnum) && c2 !== "_") {
                    it.unpeek(c2);
                    break;
                }
                col += 1;
                name += c2;
            }
            yield new Token(TokenType.NAME, name, loc);
        } else if (c.match(isNumeric) || c === ".") {
            let num = c;
            let hasDot = c === ".";
            for (const c2 of it) {
                if (c2 === ".") {
                    if (hasDot) throw new SyntaxError("Number with multiple decimals", loc);
                    hasDot = true;
                } else if (!c2.match(isNumeric)) {
                    it.unpeek(c2);
                    break;
                }
                col += 1;
                num += c2;
            }
            yield new Token(TokenType.NUMBER, num, loc);
        } else {
            throw new SyntaxError(`Unexpected '${c}'`, loc);
        }
    }
}

export function evaluate(rawExpr, env) {
    return evaluateExpr(env || {}, new Peekable(tokenize(rawExpr)));
}

class BinaryOp {
    constructor(lbp, operation, associativity = "left") {
        this.lbp = lbp;
        this.operation = operation;
        this.associativity = associativity;
    }
}

class UnaryOp {
    constructor(rbp, operation) {
        this.rbp = rbp;
        this.operation = operation;
    }
}

function undefined_() {
    throw new Error("Operation not defined");
}

const BINARY_OPS = Object.freeze({
    [TokenType.RPAREN]: new BinaryOp(0, undefined_),
    [TokenType.PLUS]: new BinaryOp(1, (a, b) => a + b),
    [TokenType.MINUS]: new BinaryOp(1, (a, b) => a - b),
    [TokenType.STAR]: new BinaryOp(2, (a, b) => a * b),
    [TokenType.SLASH]: new BinaryOp(2, (a, b) => a / b),
});

const UNARY_OPS = Object.freeze({
    [TokenType.LPAREN]: new UnaryOp(0, x => x),
    [TokenType.MINUS]: new UnaryOp(3, x => -x),
});

function evaluateExpr(env, tokens, rbp = 0) {
    const next = tokens.next();
    if (next.done) throw new SyntaxError("Unexpected end of input", null);
    let tok = next.value;
    let left = nud(env, tokens, tok);
    while ((tok = tokens.peek()) && (
        // If the token isn't a valid binop let _led handle the error
        !(tok.type in BINARY_OPS) ||
        rbp < BINARY_OPS[tok.type].lbp
    )) {
        left = led(env, tokens, left, tokens.next().value);
    }
    return left;
}

function nud(env, tokens, token) {
    if (token.type === TokenType.NUMBER) {
        return parseFloat(token.text);
    } else if (token.type === TokenType.NAME) {
        if (token.text in env) {
            return env[token.text];
        } else {
            throw new SyntaxError(`Unknown name '${token.text}'`, token.location);
        }
    } else if (token.type in UNARY_OPS) {
        const op = UNARY_OPS[token.type];
        const result = op.operation(evaluateExpr(env, tokens, op.rbp));
        if (token.type === TokenType.LPAREN) {
            const rparen = tokens.next().value;
            if (!rparen || rparen.type !== TokenType.RPAREN) {
                const loc = rparen ? rparen.location : new Location(
                    token.location.line,
                    token.location.column + token.text.length + 1,
                );
                throw new SyntaxError("Expected right parenthesis", loc);
            }
        }
        return result;
    } else {
        throw new SyntaxError(`Unexpected '${token.text}'`, token.location);
    }
}

function led(env, tokens, left, token) {
    if (token.type in BINARY_OPS) {
        const op = BINARY_OPS[token.type];
        const right = evaluateExpr(
            env, tokens, op.associativity === "left" ? op.lbp : op.lbp - 1,
        );
        return op.operation(left, right);
    } else {
        throw new SyntaxError(`Unexpected '${token.text}'`, token.location);
    }
}
