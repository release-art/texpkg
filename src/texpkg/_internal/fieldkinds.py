"""What an argument holds, read from texmodel's `FieldType` (N5): texmodel has no public form of it, so this module is
the one place that reaches into its internals."""

from texmodel._internal.fieldtypes import (
    ChoiceType,
    FieldType,
    KeyList,
    ListOf,
    OneOf,
    TupleOf,
    Written,
)


def is_raw(held: FieldType) -> bool:
    """Whether a field of this type can hold TeX written as it is (P25), itself or in a part of it."""
    if isinstance(held, Written):
        return held.verbatim
    if isinstance(held, ListOf):
        return is_raw(held.item)
    if isinstance(held, TupleOf | OneOf):
        return any(is_raw(item) for item in held.items)
    return False


def label(held: FieldType) -> str:
    """What the `interface` snapshot says an argument holds, without a `Choice`'s members: they belong to the data
    contract."""
    if isinstance(held, ChoiceType):
        return f"Choice {held.choice.__name__}"
    if isinstance(held, KeyList):
        return "KeyVals"
    if isinstance(held, Written) and held.verbatim:
        return "Raw"
    return held.name
