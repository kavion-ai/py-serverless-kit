import { useEffect, useState } from "react";

export function CopyButton({ value, label = "copy" }: { value: string; label?: string }) {
  const [done, setDone] = useState(false);
  useEffect(() => {
    if (!done) return undefined;
    const t = window.setTimeout(() => setDone(false), 1200);
    return () => window.clearTimeout(t);
  }, [done]);
  const copy = () => {
    const fallback = () => {
      const area = document.createElement("textarea");
      area.value = value;
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      try {
        document.execCommand("copy");
        setDone(true);
      } finally {
        document.body.removeChild(area);
      }
    };
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(value).then(() => setDone(true), fallback);
    } else {
      fallback();
    }
  };
  return (
    <button type="button" className="copy" onClick={copy} title={`Copy ${value}`}>
      {done ? "copied" : label}
    </button>
  );
}
