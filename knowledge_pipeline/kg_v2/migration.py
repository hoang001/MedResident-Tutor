"""Conservative old-v2 -> canonical ID crosswalk; never changes old output files."""

from knowledge_pipeline.validation import normalized


def legacy_crosswalk(old_graph, candidates, bindings, locators):
    mappings, unmapped = [], []
    for old in old_graph["nodes"]:
        old_name = normalized(old.get("name", old.get("text", ""))).casefold()
        old_sources = [s for c in old.get("content", []) for s in c["sources"]]
        matches = set()
        for new in candidates["nodes"]:
            if new["type"] != old["type"] or new["id"] not in bindings:
                continue
            new_name = normalized(new.get("name", new.get("text", ""))).casefold()
            if (
                not old_name
                or not new_name
                or not (old_name in new_name or new_name in old_name)
            ):
                continue
            new_sources = [s for c in new.get("content", []) for s in c["sources"]]
            proven = False
            for left in old_sources:
                for right in new_sources:
                    if left["source_id"] != right["source_id"] or not set(
                        left["pdf_pages"]
                    ) & set(right["pdf_pages"]):
                        continue
                    trace = locators[right["locator_id"]]
                    raw_quote = normalized(trace.get("raw_text", right["excerpt"]))
                    old_quote = normalized(left["excerpt"])
                    if (
                        old_quote
                        and raw_quote
                        and (old_quote in raw_quote or raw_quote in old_quote)
                    ):
                        proven = True
            if proven:
                matches.add(bindings[new["id"]])
        if len(matches) == 1:
            mappings.append(
                {
                    "old_id": old["id"],
                    "canonical_id": next(iter(matches)),
                    "basis": "same_type_compatible_name_and_unique_original_source_quote_trace",
                }
            )
        else:
            unmapped.append(
                {
                    "old_id": old["id"],
                    "type": old["type"],
                    "name": old.get("name"),
                    "reason": "ambiguous_correspondence"
                    if matches
                    else "no_proven_same_type_correspondence",
                }
            )
    return {"mappings": mappings, "unmapped": unmapped, "old_data_modified": False}
