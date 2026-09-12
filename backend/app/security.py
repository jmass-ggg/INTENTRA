"""Security utilities for Intentra."""

import re


PERSON_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def validate_person_id(person_id: str) -> str:
    """Validate a person_id against the safe pattern.

    Args:
        person_id: The person identifier to validate

    Returns:
        The validated person_id

    Raises:
        ValueError: If the person_id is invalid (empty, too long, or contains
                    unsafe characters like path traversal sequences)
    """
    if not person_id:
        raise ValueError("person_id cannot be empty")

    if not PERSON_ID_PATTERN.match(person_id):
        raise ValueError(
            f"Invalid person_id: must contain only alphanumeric characters, "
            f"underscores, and hyphens, and be 1-64 characters long"
        )

    return person_id
