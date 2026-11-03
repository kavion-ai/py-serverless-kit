export function SearchInput({
  value,
  onChange,
  placeholder,
  label,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  label?: string;
}) {
  return (
    <label className="search">
      <span className="search-icon" aria-hidden="true">
        ⌕
      </span>
      <input
        type="search"
        value={value}
        placeholder={placeholder}
        aria-label={label || placeholder || "Search"}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

export interface Option {
  value: string;
  label: string;
}

export function Select({
  value,
  onChange,
  options,
  label,
  allLabel,
}: {
  value: string;
  onChange: (value: string) => void;
  options: (Option | string)[];
  label: string;
  allLabel?: string;
}) {
  return (
    <select className="select" value={value} aria-label={label} title={label} onChange={(e) => onChange(e.target.value)}>
      {allLabel !== undefined && <option value="">{allLabel}</option>}
      {options.map((o) => {
        const opt = typeof o === "string" ? { value: o, label: o } : o;
        return (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        );
      })}
    </select>
  );
}
