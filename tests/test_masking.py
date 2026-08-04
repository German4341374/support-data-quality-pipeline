from support_data_quality.masking import mask_email, mask_mapping, mask_text


def test_email_masking_is_deterministic() -> None:
    assert mask_email("Person@Example.invalid") == mask_email("person@example.invalid")


def test_email_masking_does_not_preserve_local_part() -> None:
    masked = mask_email("private.person@example.invalid")
    assert "private" not in masked
    assert masked.endswith("@masked.invalid")


def test_empty_email_uses_non_identifying_marker() -> None:
    assert mask_email("").endswith("@masked.invalid")


def test_text_masks_email_and_phone() -> None:
    masked = mask_text("Email user@example.invalid or +1-202-555-0100")
    assert "user@example.invalid" not in masked
    assert "202-555" not in masked
    assert "[PHONE]" in masked


def test_mapping_masks_nested_values() -> None:
    masked = mask_mapping({"owner": "user@example.invalid", "nested": {"phone": "202-555-0199"}})
    assert "@masked.invalid" in str(masked["owner"])
    assert masked["nested"] == {"phone": "[REDACTED]"}


def test_mapping_preserves_non_string_values() -> None:
    assert mask_mapping({"count": 3, "active": True}) == {"count": 3, "active": True}
