"""Pre-compute L1+L2 embeddings and upload to S3.

Usage:
    uv run python -m backend.scripts.precompute_embeddings
    uv run python -m backend.scripts.precompute_embeddings --all   # include L3 (~3 min)
    uv run python -m backend.scripts.precompute_embeddings --dry-run  # skip S3 upload
"""

from __future__ import annotations

import sys
from pathlib import Path

OUT = Path("data/embeddings_cache.pkl.gz")


def main(include_l3: bool = False, dry_run: bool = False) -> None:
    from backend.core.dependencies import get_classifier, get_settings
    from backend.infrastructure.s3_store import S3Store

    print("Loading classifier...")
    clf = get_classifier()
    root_id = clf.ontology.root_id

    print("Pre-computing L1...")
    l1_nodes = clf.ontology.children(root_id)
    clf._prefill_cache(root_id, l1_nodes)
    print(f"  {len(l1_nodes)} L1 nodes, {len(clf._anchor_cache)} cache entries")

    print("Pre-computing L2...")
    for l1 in l1_nodes:
        l2_nodes = clf.ontology.children(l1.id)
        if l2_nodes:
            clf._prefill_cache(l1.id, l2_nodes)
    print(f"  {len(clf._anchor_cache)} cache entries total")

    if include_l3:
        print("Pre-computing L3 (this takes ~3 min)...")
        l2_all = [n for n in clf.ontology.nodes_by_id.values() if n.depth == 2]
        for i, l2 in enumerate(l2_all):
            l3_nodes = clf.ontology.children(l2.id)
            if l3_nodes:
                clf._prefill_cache(l2.id, l3_nodes)
            if i % 20 == 0:
                print(f"  {i}/{len(l2_all)} L2 branches done, {len(clf._anchor_cache)} entries")
        print(f"  L3 done: {len(clf._anchor_cache)} cache entries total")

    print(f"Saving to {OUT}...")
    n = clf.save_cache(OUT)
    size_kb = OUT.stat().st_size // 1024
    print(f"  Saved {n} entries, {size_kb} KB")

    if dry_run:
        print("--dry-run: skipping S3 upload")
        return

    settings = get_settings()
    if not (settings.s3_bucket and settings.s3_access_key_id and settings.s3_secret_access_key):
        print("S3 not configured — file saved locally only")
        return

    print(f"Uploading to s3://{settings.s3_bucket}/{settings.s3_embeddings_key}...")
    s3 = S3Store(
        bucket=settings.s3_bucket,
        key=settings.s3_embeddings_key,
        endpoint_url=settings.s3_endpoint_url,
        access_key_id=settings.s3_access_key_id,
        secret_access_key=settings.s3_secret_access_key,
    )
    s3.upload_from(OUT)
    print("Done.")


if __name__ == "__main__":
    main(
        include_l3="--all" in sys.argv,
        dry_run="--dry-run" in sys.argv,
    )
