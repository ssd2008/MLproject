import type { DocumentItem } from "../api/types";

export function DocumentPicker({
  documents,
  selected,
  onChange,
}: {
  documents: DocumentItem[];
  selected: string[];
  onChange: (ids: string[]) => void;
}) {
  const readyDocuments = documents.filter((document) => document.status === "ready");

  if (readyDocuments.length === 0) {
    return <p className="field-hint">Сначала загрузите и проиндексируйте хотя бы один документ.</p>;
  }

  return (
    <div className="document-picker">
      <label className="document-picker__all">
        <input
          type="checkbox"
          checked={selected.length === 0}
          onChange={() => onChange([])}
        />
        <span>Искать по всем готовым документам</span>
      </label>
      <div className="document-picker__list">
        {readyDocuments.map((document) => {
          const checked = selected.includes(document.id);
          return (
            <label key={document.id} className="document-picker__item">
              <input
                type="checkbox"
                checked={checked}
                onChange={(event) => {
                  if (event.target.checked) {
                    onChange([...selected, document.id]);
                  } else {
                    onChange(selected.filter((id) => id !== document.id));
                  }
                }}
              />
              <span>
                <strong>{document.title}</strong>
                <small>{document.chunk_count} фрагментов</small>
              </span>
            </label>
          );
        })}
      </div>
    </div>
  );
}
