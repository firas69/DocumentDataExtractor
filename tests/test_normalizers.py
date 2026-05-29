from extraction_engine.normalizers import detect_currency, normalize_date, normalize_number, normalize_string


def test_string_normalization_trims_and_collapses_spaces():
    assert normalize_string("  Invoice    Number  ") == "Invoice Number"


def test_number_normalization_handles_currency_and_thousands():
    assert normalize_number("$1,200.50") == 1200.5
    assert normalize_number("EUR 1.200,50") == 1200.5


def test_date_normalization_common_formats():
    assert normalize_date("2026-05-12")[0] == "2026-05-12"
    assert normalize_date("12/05/2026")[0] == "2026-05-12"
    assert normalize_date("May 12, 2026")[0] == "2026-05-12"


def test_currency_detection():
    assert detect_currency("TND 120") == "TND"
    assert detect_currency("$120") == "USD"
