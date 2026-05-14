from __future__ import annotations

from bms.domain.accounting.models import Account, AccountType


BASELINE_CHART_OF_ACCOUNTS: dict[str, Account] = {
    "1000": Account("1000", "Cash", AccountType.ASSET),
    "1010": Account("1010", "Bank", AccountType.ASSET),
    "1100": Account("1100", "Accounts Receivable", AccountType.ASSET),
    "1200": Account("1200", "Inventory", AccountType.ASSET),
    "1300": Account("1300", "GST Input Tax Receivable", AccountType.ASSET),
    "2000": Account("2000", "Accounts Payable", AccountType.LIABILITY),
    "2100": Account("2100", "GST Output Tax Payable", AccountType.LIABILITY),
    "3000": Account("3000", "Owner Equity", AccountType.EQUITY),
    "4000": Account("4000", "Sales Revenue", AccountType.REVENUE),
    "4100": Account("4100", "Sales Returns", AccountType.REVENUE),
    "5000": Account("5000", "Cost of Goods Sold", AccountType.EXPENSE),
    "5100": Account("5100", "Inventory Adjustment Expense", AccountType.EXPENSE),
}
