"""Every list ordered by a time the database stamps ends on the row's id (#733, #736),
in the app and in the tests that read rows back (#819).

Postgres gives every row written in one transaction the same now(), so two rows a
request (or a test) writes together tie on created_at, and come back in whatever
order the table holds them. A test runs in one transaction, so every row it makes
ties. Ids are UUID v7 (horatio.models.base.Record), which rise in the order rows are
made, so the id breaks the tie as they were recorded.
"""

import ast
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "src" / "horatio"
TESTS = Path(__file__).resolve().parent

# Columns the database fills with now(): they tie within a transaction. Times set in
# Python (datetime.now(UTC)) differ on every call, and times people enter are theirs.
STAMPED = {"created_at", "updated_at"}
STAMPED_ON = {"TroupeMembership.joined_at"}


def _column(node: ast.expr) -> ast.Attribute | None:
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in ("asc", "desc")
        and not node.args
    ):
        node = node.func.value
    return node if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) else None


def _untied() -> list[str]:
    found: list[str] = []
    for path in sorted([*SOURCE.rglob("*.py"), *TESTS.rglob("*.py")]):
        for node in ast.walk(ast.parse(path.read_text(), str(path))):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "order_by"
                and node.args
            ):
                continue
            last = _column(node.args[-1])
            if last is None:
                continue
            assert isinstance(last.value, ast.Name)
            full = f"{last.value.id}.{last.attr}"
            if last.attr in STAMPED or full in STAMPED_ON:
                where = path.relative_to(SOURCE.parents[1])
                found.append(f"{where}:{node.lineno}: order_by(... {ast.unparse(node.args[-1])})")
    return found


def test_lists_ordered_by_a_stamped_time_end_on_the_id() -> None:
    untied = _untied()
    assert not untied, (
        "Add the row's id as the last thing to order by (desc with a desc time), "
        "so rows written in one transaction keep the order they were made:\n" + "\n".join(untied)
    )
