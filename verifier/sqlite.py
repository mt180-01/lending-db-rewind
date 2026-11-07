"""A pure-Python reader of SQLite database files: the header, the schema and every table's rows.

The verifier may not import sqlite3, so it reads the file's bytes itself (the file format is documented at
sqlite.org/fileformat2.html). It supports rowid tables with integer, text and NULL values, which is all this
plugin's database holds; a REAL or BLOB value, an unknown page type or a malformed page raises DatabaseError.
"""

import json
import re

MAGIC = b"SQLite format 3\x00"
INTEGER_SIZES = (1, 2, 3, 4, 6, 8)
CONSTRAINT = re.compile(r"(primary|unique|foreign|check|constraint)\b", re.IGNORECASE)


class DatabaseError(Exception):
    """The file is not a database this reader can read."""


def varint(data, position):
    value = 0
    for step in range(8):
        byte = data[position + step]
        value = (value << 7) | (byte & 0x7F)
        if byte < 0x80:
            return value, position + step + 1
    return (value << 8) | data[position + 8], position + 9


def decode_record(payload):
    header_size, position = varint(payload, 0)
    kinds = []
    while position < header_size:
        kind, position = varint(payload, position)
        kinds.append(kind)
    if position != header_size:
        raise DatabaseError("a record header overruns its size")
    values = []
    at = header_size
    for kind in kinds:
        if kind == 0:
            values.append(None)
        elif 1 <= kind <= 6:
            size = INTEGER_SIZES[kind - 1]
            values.append(int.from_bytes(payload[at : at + size], "big", signed=True))
            at += size
        elif kind in (8, 9):
            values.append(kind - 8)
        elif kind >= 13 and kind % 2 == 1:
            size = (kind - 13) // 2
            values.append(payload[at : at + size].decode("utf-8"))
            at += size
        else:
            raise DatabaseError(f"unsupported value type {kind}: only integers, text and NULL are read")
    if at > len(payload):
        raise DatabaseError("a record's values overrun its payload")
    return values


class Reader:
    def __init__(self, data):
        if len(data) < 100 or data[:16] != MAGIC:
            raise DatabaseError("not a SQLite 3 database: the header magic is missing")
        self.data = data
        self.page_size = int.from_bytes(data[16:18], "big")
        if self.page_size == 1:
            self.page_size = 65536
        if self.page_size < 512 or self.page_size & (self.page_size - 1):
            raise DatabaseError(f"invalid page size {self.page_size}")
        if len(data) % self.page_size:
            raise DatabaseError("the file is not a whole number of pages")
        self.pages = len(data) // self.page_size
        self.usable = self.page_size - data[20]
        counted = int.from_bytes(data[28:32], "big")
        if data[24:28] == data[92:96] and counted != self.pages:
            raise DatabaseError(f"the header counts {counted} pages but the file holds {self.pages}")
        if int.from_bytes(data[56:60], "big") != 1:
            raise DatabaseError("only UTF-8 databases are read")

    def page(self, number):
        if not 1 <= number <= self.pages:
            raise DatabaseError(f"page {number} is outside the file")
        start = (number - 1) * self.page_size
        return self.data[start : start + self.page_size]

    def payload(self, page, position, size):
        max_local = self.usable - 35
        if size <= max_local:
            return page[position : position + size]
        min_local = (self.usable - 12) * 32 // 255 - 23
        local = min_local + (size - min_local) % (self.usable - 4)
        if local > max_local:
            local = min_local
        data = bytearray(page[position : position + local])
        following = int.from_bytes(page[position + local : position + local + 4], "big")
        while len(data) < size:
            overflow = self.page(following)
            following = int.from_bytes(overflow[:4], "big")
            data += overflow[4 : 4 + min(size - len(data), self.usable - 4)]
        return bytes(data)

    def cells(self, root):
        """Every (rowid, values) in the table b-tree at page ``root``, in rowid order."""
        seen = set()
        last = [0]

        def walk(number):
            if number in seen:
                raise DatabaseError(f"page {number} is reached twice")
            seen.add(number)
            page = self.page(number)
            base = 100 if number == 1 else 0
            kind = page[base]
            count = int.from_bytes(page[base + 3 : base + 5], "big")
            if kind == 0x0D:
                for index in range(count):
                    pointer = int.from_bytes(page[base + 8 + 2 * index : base + 10 + 2 * index], "big")
                    size, position = varint(page, pointer)
                    rowid, position = varint(page, position)
                    if rowid <= last[0]:
                        raise DatabaseError(f"page {number}: rowids are out of order")
                    last[0] = rowid
                    yield rowid, decode_record(self.payload(page, position, size))
            elif kind == 0x05:
                for index in range(count):
                    pointer = int.from_bytes(page[base + 12 + 2 * index : base + 14 + 2 * index], "big")
                    yield from walk(int.from_bytes(page[pointer : pointer + 4], "big"))
                yield from walk(int.from_bytes(page[base + 8 : base + 12], "big"))
            else:
                raise DatabaseError(f"page {number} is not a table b-tree page (type {kind})")

        return walk(root)


def alias_column(sql):
    """The index of the INTEGER PRIMARY KEY column, which a record stores as NULL (the rowid is its value)."""
    body = sql[sql.index("(") + 1 : sql.rindex(")")]
    parts, depth, current = [], 0, ""
    for char in body:
        depth += (char == "(") - (char == ")")
        if char == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += char
    parts.append(current)
    columns = [part.strip() for part in parts if not CONSTRAINT.match(part.strip())]
    for index, column in enumerate(columns):
        if re.match(r'^\W*\w+\W*\s+INTEGER\s+PRIMARY\s+KEY\b', column, re.IGNORECASE):
            return index, len(columns)
    return None, len(columns)


def read_database(data):
    """``{"schema": [canonical JSON of each sqlite_master entry], "tables": {name: [row, ...]}}``."""
    try:
        reader = Reader(data)
        master = [values for _, values in reader.cells(1)]
        schema, tables = [], {}
        for kind, name, table, root, sql in master:
            schema.append(json.dumps([kind, name, table, sql], ensure_ascii=False))
            if kind != "table" or name.startswith("sqlite_"):
                continue
            alias, width = alias_column(sql)
            rows = []
            for rowid, values in reader.cells(root):
                if len(values) != width:
                    raise DatabaseError(f"table {name}: a row has {len(values)} values, not {width}")
                if alias is not None:
                    values[alias] = rowid
                rows.append(values)
            tables[name] = rows
        return {"schema": sorted(schema), "tables": tables}
    except (IndexError, ValueError, UnicodeDecodeError) as error:
        raise DatabaseError(f"malformed database file: {error}") from error
