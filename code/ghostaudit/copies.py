"""Physical copies. 'primary' is every view of the live system (inventory, bundle, export, log, handover, ledger, history,
snapshot, pdf); each named replica (*_replica*, replica_*) is a separate copy."""


def copy_of(store):
    return store if "replica" in store and store != "search_documents_primary" else "primary"
