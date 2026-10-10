"""Regenerate synthetic data, documents and the local database."""

from scripts.bootstrap import bootstrap

if __name__ == "__main__":
    result = bootstrap(include_generics=True, rebuild=True)
    print(result["ingestion"])
