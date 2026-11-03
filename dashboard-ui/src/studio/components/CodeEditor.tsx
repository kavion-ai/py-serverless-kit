import { useEffect, useRef } from "react";
import { autocompletion, closeBrackets, closeBracketsKeymap, completionKeymap } from "@codemirror/autocomplete";
import { defaultKeymap, history, historyKeymap, indentWithTab } from "@codemirror/commands";
import { javascript } from "@codemirror/lang-javascript";
import { json } from "@codemirror/lang-json";
import { python } from "@codemirror/lang-python";
import { yaml } from "@codemirror/lang-yaml";
import {
  bracketMatching,
  foldGutter,
  foldKeymap,
  HighlightStyle,
  indentOnInput,
  indentUnit,
  syntaxHighlighting,
} from "@codemirror/language";
import { highlightSelectionMatches, search, searchKeymap } from "@codemirror/search";
import { Compartment, EditorState, type Extension } from "@codemirror/state";
import {
  crosshairCursor,
  drawSelection,
  dropCursor,
  EditorView,
  highlightActiveLine,
  highlightActiveLineGutter,
  highlightSpecialChars,
  keymap,
  lineNumbers,
  rectangularSelection,
} from "@codemirror/view";
import { tags as t } from "@lezer/highlight";

export type Language = "python" | "yaml" | "json" | "javascript" | "typescript" | "text";

export function languageOf(path: string): Language {
  const p = path.toLowerCase();
  if (p.endsWith(".py") || p.endsWith(".pyi")) return "python";
  if (p.endsWith(".yml") || p.endsWith(".yaml")) return "yaml";
  if (p.endsWith(".json")) return "json";
  if (/\.(ts|mts|cts|tsx)$/.test(p)) return "typescript";
  if (/\.(js|mjs|cjs|jsx)$/.test(p)) return "javascript";
  return "text";
}

function languageExt(lang: Language): Extension {
  if (lang === "python") return [python(), indentUnit.of("    ")];
  if (lang === "yaml") return [yaml(), indentUnit.of("  ")];
  if (lang === "json") return [json(), indentUnit.of("  ")];
  if (lang === "typescript") return [javascript({ typescript: true }), indentUnit.of("  ")];
  if (lang === "javascript") return [javascript(), indentUnit.of("  ")];
  return indentUnit.of("    ");
}

// VS Code "Dark+" / "Light+" inspired palettes.
const darkHighlight = HighlightStyle.define([
  { tag: [t.keyword, t.controlKeyword, t.moduleKeyword, t.operatorKeyword], color: "#c586c0" },
  { tag: [t.definitionKeyword, t.bool, t.null, t.self], color: "#569cd6" },
  { tag: [t.function(t.variableName), t.function(t.propertyName)], color: "#dcdcaa" },
  { tag: [t.definition(t.variableName), t.variableName], color: "#9cdcfe" },
  { tag: [t.className, t.typeName], color: "#4ec9b0" },
  { tag: [t.string, t.special(t.string)], color: "#ce9178" },
  { tag: [t.number], color: "#b5cea8" },
  { tag: [t.comment, t.lineComment, t.blockComment], color: "#6a9955", fontStyle: "italic" },
  { tag: [t.propertyName, t.attributeName], color: "#9cdcfe" },
  { tag: [t.meta, t.annotation], color: "#dcdcaa" },
  { tag: [t.operator, t.punctuation], color: "#d4d4d4" },
  { tag: t.invalid, color: "#f44747" },
]);

const lightHighlight = HighlightStyle.define([
  { tag: [t.keyword, t.controlKeyword, t.moduleKeyword, t.operatorKeyword], color: "#af00db" },
  { tag: [t.definitionKeyword, t.bool, t.null, t.self], color: "#0000ff" },
  { tag: [t.function(t.variableName), t.function(t.propertyName)], color: "#795e26" },
  { tag: [t.definition(t.variableName), t.variableName], color: "#001080" },
  { tag: [t.className, t.typeName], color: "#267f99" },
  { tag: [t.string, t.special(t.string)], color: "#a31515" },
  { tag: [t.number], color: "#098658" },
  { tag: [t.comment, t.lineComment, t.blockComment], color: "#008000", fontStyle: "italic" },
  { tag: [t.propertyName, t.attributeName], color: "#0451a5" },
  { tag: [t.meta, t.annotation], color: "#795e26" },
  { tag: t.invalid, color: "#cd3131" },
]);

function themeFor(dark: boolean): Extension {
  const view = EditorView.theme(
    {
      "&": {
        backgroundColor: dark ? "#1e1e1e" : "#ffffff",
        color: dark ? "#d4d4d4" : "#1f1f1f",
        fontSize: "13px",
        height: "100%",
      },
      ".cm-scroller": { fontFamily: "var(--mono)", lineHeight: "1.55" },
      ".cm-content": { caretColor: dark ? "#aeafad" : "#000000" },
      ".cm-cursor, .cm-dropCursor": { borderLeftColor: dark ? "#aeafad" : "#000000" },
      "&.cm-focused .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection": {
        backgroundColor: dark ? "#264f78" : "#add6ff",
      },
      ".cm-activeLine": { backgroundColor: dark ? "#2a2d2e80" : "#f3f3f380" },
      ".cm-gutters": {
        backgroundColor: dark ? "#1e1e1e" : "#ffffff",
        color: dark ? "#858585" : "#237893",
        border: "none",
      },
      ".cm-activeLineGutter": { backgroundColor: "transparent", color: dark ? "#c6c6c6" : "#0b216f" },
      ".cm-searchMatch": { backgroundColor: dark ? "#623315" : "#f8c9ab" },
      ".cm-selectionMatch": { backgroundColor: dark ? "#3a3d41" : "#e5ebf1" },
      ".cm-panels": { backgroundColor: dark ? "#252526" : "#f3f3f3", color: "inherit" },
      ".cm-tooltip": { backgroundColor: dark ? "#252526" : "#f3f3f3", border: "1px solid var(--line)" },
    },
    { dark },
  );
  return [view, syntaxHighlighting(dark ? darkHighlight : lightHighlight)];
}

export function prefersDark(): boolean {
  const attr = document.documentElement.getAttribute("data-theme");
  if (attr) return attr === "dark";
  return !!window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
}

/** Thin React wrapper around a CodeMirror 6 editor. */
export function CodeEditor({
  value,
  onChange,
  language = "text",
  readOnly = false,
  onSave,
  dark,
  ariaLabel,
  minHeight = 320,
}: {
  value: string;
  onChange?: (value: string) => void;
  language?: Language;
  readOnly?: boolean;
  onSave?: () => void;
  dark?: boolean;
  ariaLabel?: string;
  minHeight?: number;
}) {
  const host = useRef<HTMLDivElement>(null);
  const view = useRef<EditorView | null>(null);
  const langComp = useRef(new Compartment());
  const roComp = useRef(new Compartment());
  const themeComp = useRef(new Compartment());
  const onChangeRef = useRef(onChange);
  const onSaveRef = useRef(onSave);
  onChangeRef.current = onChange;
  onSaveRef.current = onSave;

  useEffect(() => {
    if (!host.current) return undefined;
    const state = EditorState.create({
      doc: value,
      extensions: [
        lineNumbers(),
        highlightActiveLineGutter(),
        highlightSpecialChars(),
        history(),
        foldGutter(),
        drawSelection(),
        dropCursor(),
        EditorState.allowMultipleSelections.of(true),
        indentOnInput(),
        bracketMatching(),
        closeBrackets(),
        autocompletion(),
        rectangularSelection(),
        crosshairCursor(),
        highlightActiveLine(),
        highlightSelectionMatches(),
        search({ top: true }),
        keymap.of([
          {
            key: "Mod-s",
            preventDefault: true,
            run: () => {
              onSaveRef.current?.();
              return true;
            },
          },
          indentWithTab,
          ...closeBracketsKeymap,
          ...defaultKeymap,
          ...searchKeymap,
          ...historyKeymap,
          ...foldKeymap,
          ...completionKeymap,
        ]),
        langComp.current.of(languageExt(language)),
        roComp.current.of([EditorState.readOnly.of(readOnly), EditorView.editable.of(!readOnly)]),
        themeComp.current.of(themeFor(dark ?? prefersDark())),
        EditorView.contentAttributes.of({ "aria-label": ariaLabel || "Code editor" }),
        EditorView.updateListener.of((u) => {
          if (u.docChanged) onChangeRef.current?.(u.state.doc.toString());
        }),
      ],
    });
    const v = new EditorView({ state, parent: host.current });
    view.current = v;
    return () => {
      v.destroy();
      view.current = null;
    };
    // The editor is created once; props below are applied through compartments.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const v = view.current;
    if (v && v.state.doc.toString() !== value) {
      v.dispatch({ changes: { from: 0, to: v.state.doc.length, insert: value } });
    }
  }, [value]);

  useEffect(() => {
    view.current?.dispatch({ effects: langComp.current.reconfigure(languageExt(language)) });
  }, [language]);

  useEffect(() => {
    view.current?.dispatch({
      effects: roComp.current.reconfigure([EditorState.readOnly.of(readOnly), EditorView.editable.of(!readOnly)]),
    });
  }, [readOnly]);

  useEffect(() => {
    const apply = () => view.current?.dispatch({ effects: themeComp.current.reconfigure(themeFor(dark ?? prefersDark())) });
    apply();
    if (dark !== undefined) return undefined;
    const observer = new MutationObserver(apply);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    const mq = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
    mq?.addEventListener?.("change", apply);
    return () => {
      observer.disconnect();
      mq?.removeEventListener?.("change", apply);
    };
  }, [dark]);

  return <div className="code-editor" ref={host} style={{ minHeight }} />;
}
