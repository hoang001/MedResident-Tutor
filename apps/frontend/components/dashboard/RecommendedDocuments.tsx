import type { RecommendedDocument } from "@/lib/types";
import { Badge } from "@/components/ui/Badge";
import { InlineEmpty } from "@/components/ui/StateViews";

interface RecommendedDocumentsProps {
  documents: RecommendedDocument[];
  emptyMessage: string;
}

export function RecommendedDocuments({
  documents,
  emptyMessage,
}: RecommendedDocumentsProps) {
  if (documents.length === 0) {
    return <InlineEmpty message={emptyMessage} />;
  }

  return (
    <ul className="doc-list">
      {documents.map((doc) => (
        <li key={doc.id} className="doc-item">
          <div className="doc-item-info">
            <p className="doc-item-title">{doc.title}</p>
            <p className="doc-item-meta muted">
              {doc.specialty} · {doc.reason}
            </p>
          </div>
          <Badge tone="neutral">{doc.kind}</Badge>
        </li>
      ))}
    </ul>
  );
}
