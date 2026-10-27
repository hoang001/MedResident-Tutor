"""Review proposals only; never rewrite legacy IDs, curriculum or source data."""

from .validation import normalized


def legacy_proposals(candidates, old_units, manifests=()):
    locators = {}
    for manifest in manifests:
        for unit_id in manifest.get("source_unit_ids", []):
            locators[unit_id] = manifest["locator"]["pdf_pages"]
    proposals = []
    for new in candidates:
        pages = {s["pdf_page"] for s in new["supports"]}
        quote = normalized("\n".join(s["quote"] for s in new["supports"]))
        for old in old_units:
            if old["source_id"] != new["source_id"]:
                continue
            old_id = old["source_unit_id"]
            loc = locators.get(
                old_id, {"start": old["page_start"], "end": old["page_end"]}
            )
            if not pages.intersection(range(loc["start"], loc["end"] + 1)):
                continue
            proposals.append(
                {
                    "new_source_unit_id": new["source_unit_id"],
                    "existing_source_unit_id": old_id,
                    "basis": "exact_normalized_text"
                    if normalized(old["content"]) == quote
                    else "source_and_locator_overlap_only",
                    "existing_locator_basis": "integration_manifest"
                    if old_id in locators
                    else "legacy_dataset_unverified",
                    "status": "needs_review",
                    "replace_existing": False,
                }
            )
    return proposals
