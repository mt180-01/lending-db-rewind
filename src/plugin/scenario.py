"""The incident, built from a seed: a library's lending database, its 02:00 backup and the day's statement log."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta

DAY = "2026-03-14"
SCHEMA = (
    "CREATE TABLE members (id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE, joined_on TEXT NOT NULL)",
    "CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT NOT NULL, author TEXT NOT NULL, copies INTEGER NOT NULL)",
    (
        "CREATE TABLE loans (id INTEGER PRIMARY KEY, book_id INTEGER NOT NULL REFERENCES books(id),"
        " member_id INTEGER NOT NULL REFERENCES members(id), borrowed_at TEXT NOT NULL, due_at TEXT NOT NULL,"
        " returned_at TEXT)"
    ),
    (
        "CREATE TABLE fines (id INTEGER PRIMARY KEY, loan_id INTEGER NOT NULL REFERENCES loans(id),"
        " amount_cents INTEGER NOT NULL, paid INTEGER NOT NULL DEFAULT 0)"
    ),
    "CREATE INDEX idx_loans_member ON loans (member_id)",
)
BAD_SQL = "UPDATE loans SET returned_at = NULL"
DUE = "2026-03-28"

NAMES = [
    "Mira Castellanos", "Jonas Berg", "Priya Raman", "Tomasz Nowak", "Ines Duarte", "Kofi Mensah",
    "Hana Sato", "Luca Ferrari", "Amara Diallo", "Elif Yilmaz", "Noor Hakim", "Sven Lindqvist",
]
TITLES = [
    "The Salt Road", "Ink and Ember", "A Map of Quiet Places", "Glass Orchard", "The Lamplighter's Debt",
    "Northern Tides", "Paper Cities", "The Long Arithmetic", "Winter Cartography", "Small Gods of Lisbon",
    "The Weaver's Algebra", "Harbor Lights", "Notes on Falling", "The Copper Clock", "River Without Maps",
    "Seven Doors", "The Quiet Engine", "Letters to Orion", "The Orchard Keeper", "Tin and Thunder",
]
AUTHORS = ["R. Ashby", "L. Moreau", "T. Okonkwo", "S. Halvorsen", "P. Iyer", "D. Castillo", "M. Novak", "A. Reyes"]


@dataclass(frozen=True)
class Entry:
    seq: int
    ts: str
    sql: str


@dataclass(frozen=True)
class Scenario:
    rows: dict[str, list[tuple]]  # the backup's rows, by table
    entries: tuple[Entry, ...]  # the log, in the order the file holds them
    bad_seq: int


def quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def clock(second: int) -> str:
    return f"{DAY}T{second // 3600:02d}:{second % 3600 // 60:02d}:{second % 60:02d}"


def generate(seed: int) -> Scenario:
    rng = random.Random(seed)
    names = ["Aoife O'Brien", "Zoë Okafor", *rng.sample(NAMES, 10)]
    members = [
        (i, name, f"member{i}@harbor-library.example", f"2025-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}")
        for i, name in enumerate(names, 1)
    ]
    books = [(i, title, rng.choice(AUTHORS), rng.randint(1, 3)) for i, title in enumerate(TITLES, 1)]
    open_ids = rng.sample(range(1, 41), 15)
    loans = []
    for loan_id in range(1, 41):
        borrowed = date(2026, 2, 1) + timedelta(days=rng.randint(0, 30))
        returned = None if loan_id in open_ids else str(borrowed + timedelta(days=rng.randint(1, 13)))
        loans.append((loan_id, rng.randint(1, 20), rng.randint(1, 12), str(borrowed), str(borrowed + timedelta(days=14)), returned))
    returned_ids = [loan[0] for loan in loans if loan[5] is not None]
    fines = [(i, loan_id, rng.choice([50, 125, 300, 475]), 0) for i, loan_id in enumerate(rng.sample(returned_ids, 5), 1)]

    # The bad migration runs in second T of 14:07. Five statements share that second.
    bad_second = 14 * 3600 + 7 * 60 + rng.randint(0, 59)
    pre_returns, post_returns, same_second = open_ids[:6], open_ids[6:10], open_ids[10]
    reopened_before, reopened_after = rng.sample(returned_ids, 2)

    def new_loan(loan_id: int, second: int) -> str:
        return (
            "INSERT INTO loans (id, book_id, member_id, borrowed_at, due_at, returned_at) VALUES"
            f" ({loan_id}, {rng.randint(1, 20)}, {rng.randint(1, 12)}, {quote(clock(second))}, {quote(DUE)}, NULL)"
        )

    def new_member(member_id: int) -> str:
        return (
            "INSERT INTO members (id, name, email, joined_on) VALUES"
            f" ({member_id}, {quote(rng.choice(NAMES) + ' ' + str(member_id))},"
            f" {quote(f'member{member_id}@harbor-library.example')}, {quote(DAY)})"
        )

    def give_back(loan_id: int, second: int) -> str:
        return f"UPDATE loans SET returned_at = {quote(clock(second))} WHERE id = {loan_id}"

    def before(second: int, index: int) -> str:
        if index < 6:
            return give_back(pre_returns[index], second)
        if index < 9:
            return new_member(index + 7)
        if index < 16:
            return new_loan(index + 32, second)
        if index < 18:
            return f"UPDATE books SET copies = copies + 2 WHERE id = {rng.randint(1, 20)}"
        if index < 20:
            return f"UPDATE fines SET paid = 1 WHERE id = {index - 17}"
        if index == 20:
            return f"UPDATE loans SET returned_at = NULL WHERE id = {reopened_before}"
        if index == 21:
            return f"INSERT INTO fines (id, loan_id, amount_cents, paid) VALUES (6, {rng.choice(returned_ids)}, 200, 0)"
        return f"UPDATE books SET copies = copies + 1 WHERE id = {rng.randint(1, 20)}"

    def after(second: int, index: int) -> str:
        if index < 4:
            return give_back(post_returns[index], second)
        if index < 6:
            return give_back(41 + index - 4, second)
        if index < 9:
            return new_loan(index + 43, second)
        if index < 11:
            return new_member(index + 7)
        if index == 11:
            return f"UPDATE fines SET paid = 1 WHERE id = {rng.randint(4, 5)}"
        if index == 12:
            return "DELETE FROM fines WHERE id = 3"
        if index == 13:
            return f"UPDATE loans SET returned_at = NULL WHERE id = {reopened_after}"
        return f"UPDATE books SET copies = copies + 1 WHERE id = {rng.randint(1, 20)}"

    count_before, count_after = 22 + rng.randint(0, 12), 15 + rng.randint(0, 8)
    before_seconds = sorted(rng.sample(range(2 * 3600 + 1, bad_second), count_before))
    before_kinds = rng.sample(range(count_before), count_before)
    after_pool = [second for second in range(bad_second + 1, 17 * 3600 + 1800) if second != 14 * 3600 + 1800]
    seconds = sorted(rng.sample(after_pool, count_after + 1))
    # A late writer: loan 52 is lent and returned in the afternoon, but its return is appended to the file first.
    lent, given_back = sorted(rng.sample(range(len(seconds)), 2))
    after_seconds = [second for index, second in enumerate(seconds) if index not in (lent, given_back)]
    after_kinds = rng.sample(range(1, count_after), count_after - 1)
    # The 14:30 return is the afternoon's first kind of statement, at exactly 14:30:00.
    log: list[tuple[int, str]] = [(second, before(second, kind)) for second, kind in zip(before_seconds, before_kinds)]
    log += [(second, after(second, kind)) for second, kind in zip(after_seconds, after_kinds)]
    log.append((14 * 3600 + 1800, after(14 * 3600 + 1800, 0)))
    log.append((seconds[lent], new_loan(52, seconds[lent])))
    log.append((seconds[given_back], give_back(52, seconds[given_back])))
    log.sort(key=lambda item: item[0])
    first_same = sum(1 for second, _ in log if second < bad_second)
    group = [
        new_loan(48, bad_second),
        BAD_SQL,
        give_back(48, bad_second),
        give_back(same_second, bad_second),
        f"UPDATE loans SET returned_at = NULL WHERE id = {same_second}",
    ]
    log[first_same:first_same] = [(bad_second, sql) for sql in group]
    entries = [Entry(seq, clock(second), sql) for seq, (second, sql) in enumerate(log, 1)]
    bad_seq = first_same + 2
    # The log file was appended out of order inside the shared second.
    entries[first_same:first_same + 5] = [entries[first_same + i] for i in (2, 4, 0, 1, 3)]
    insert = next(i for i, e in enumerate(entries) if e.sql.startswith("INSERT INTO loans") and "VALUES (52," in e.sql)
    update = next(i for i, e in enumerate(entries) if e.sql.endswith("WHERE id = 52"))
    entries[insert], entries[update] = entries[update], entries[insert]
    return Scenario({"members": members, "books": books, "loans": loans, "fines": fines}, tuple(entries), bad_seq)
