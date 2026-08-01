import pytest

from quant.insider_institutional import classify_insider_transaction, summarize_insider_transactions


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Sale at price 295.14 per share.", "sell"),
        ("Purchase at price 10.00 per share.", "buy"),
        ("Stock Gift at price 0.00 per share.", "gift"),
        ("", "other"),
        ("Option Exercise", "other"),
    ],
)
def test_classify_insider_transaction(text, expected):
    assert classify_insider_transaction(text) == expected


def test_summarize_insider_transactions_tallies_by_category():
    transactions = [
        {"shares": 100, "text": "Purchase at price 10.00 per share."},
        {"shares": 50, "text": "Sale at price 20.00 per share."},
        {"shares": 30, "text": "Sale at price 21.00 per share."},
        {"shares": 10, "text": "Stock Gift at price 0.00 per share."},
        {"shares": 5, "text": ""},
    ]

    summary = summarize_insider_transactions(transactions)

    assert summary["transaction_counts"] == {"buy": 1, "sell": 2, "gift": 1, "other": 1}
    assert summary["shares_by_category"] == {"buy": 100, "sell": 80, "gift": 10, "other": 5}
    assert summary["net_buy_sell_shares"] == 100 - 80
    assert summary["total_transactions_seen"] == 5


def test_summarize_insider_transactions_empty_list():
    summary = summarize_insider_transactions([])
    assert summary["total_transactions_seen"] == 0
    assert summary["net_buy_sell_shares"] == 0
