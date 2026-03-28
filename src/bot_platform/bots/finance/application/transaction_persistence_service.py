from __future__ import annotations

from bot_platform.bots.finance.infrastructure.repositories import LearnedMapping
from bot_platform.bots.finance.models import TransactionRecord

from .guard_service import GuardService


class TransactionPersistenceService:
    def __init__(self, guards: GuardService) -> None:
        self.guards = guards
        self.runtime = guards.runtime

    def append_transaction(self, chat_id: int, transaction: TransactionRecord) -> None:
        self.guards.sheets_client().append_transaction(transaction)
        self.runtime.state_store.set_last_transaction_id(chat_id, transaction.transaction_id)
        self.runtime.state_store.set_transaction_snapshot(transaction)
        self.learn_mapping_from_transaction(transaction)

    def append_transactions(self, chat_id: int, transactions: list[TransactionRecord]) -> None:
        self.guards.sheets_client().append_transactions(transactions)
        self.runtime.state_store.clear_pending(chat_id)
        self.runtime.state_store.set_last_transaction_id(chat_id, transactions[-1].transaction_id)
        for transaction in transactions:
            self.runtime.state_store.set_transaction_snapshot(transaction)
            self.learn_mapping_from_transaction(transaction)

    def update_transaction(self, transaction: TransactionRecord) -> None:
        self.guards.sheets_client().update_transaction(transaction)
        self.runtime.state_store.set_transaction_snapshot(transaction)
        self.learn_mapping_from_transaction(transaction)

    def replace_summary(self, summary) -> None:
        self.guards.sheets_client().replace_summary(summary)

    def learn_mapping_from_transaction(self, transaction: TransactionRecord) -> None:
        pattern = (transaction.merchant_or_source or transaction.description or "").strip()
        if not pattern:
            return
        mapping = LearnedMapping(
            pattern=pattern,
            category=transaction.category,
            subcategory=transaction.subcategory,
            payment_method=transaction.payment_method or transaction.account_from,
            learned_from=transaction.transaction_id,
        )
        self.runtime.finance_repository.save_learned_mapping(mapping)
