import ReactMarkdown from "react-markdown"

/**
 * Renders a coach reply as formatted markdown (headings, bold, lists, code)
 * instead of raw text with literal ** asterisks. Element styles are mapped to
 * the app's own tokens so it matches the rest of the UI.
 */
export function MarkdownMessage({ content }: { content: string }) {
  return (
    <div className="text-sm leading-relaxed markdown-body">
      <ReactMarkdown
        components={{
          p: ({ children }) => <p style={{ margin: "0 0 0.7em" }}>{children}</p>,
          strong: ({ children }) => (
            <strong style={{ fontWeight: 700, color: "var(--text)" }}>{children}</strong>
          ),
          em: ({ children }) => <em style={{ fontStyle: "italic" }}>{children}</em>,
          h1: ({ children }) => (
            <h1 style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: "1.05rem", margin: "0.9em 0 0.4em" }}>{children}</h1>
          ),
          h2: ({ children }) => (
            <h2 style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: "1rem", margin: "0.9em 0 0.4em" }}>{children}</h2>
          ),
          h3: ({ children }) => (
            <h3 style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: "0.95rem", margin: "0.8em 0 0.35em" }}>{children}</h3>
          ),
          ul: ({ children }) => (
            <ul style={{ margin: "0 0 0.7em", paddingLeft: "1.15em", listStyle: "disc" }}>{children}</ul>
          ),
          ol: ({ children }) => (
            <ol style={{ margin: "0 0 0.7em", paddingLeft: "1.25em", listStyle: "decimal" }}>{children}</ol>
          ),
          li: ({ children }) => <li style={{ margin: "0.25em 0" }}>{children}</li>,
          code: ({ children }) => (
            <code style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.85em",
              background: "rgba(255,255,255,0.07)",
              padding: "0.1em 0.35em",
              borderRadius: 4,
            }}>{children}</code>
          ),
          pre: ({ children }) => (
            <pre style={{
              margin: "0 0 0.7em",
              padding: "0.7em",
              background: "rgba(0,0,0,0.35)",
              borderRadius: 10,
              overflowX: "auto",
              fontSize: "0.8em",
            }}>{children}</pre>
          ),
          blockquote: ({ children }) => (
            <blockquote style={{
              margin: "0 0 0.7em",
              paddingLeft: "0.8em",
              borderLeft: "2px solid var(--purple)",
              color: "var(--text-muted)",
            }}>{children}</blockquote>
          ),
          hr: () => <hr style={{ border: 0, borderTop: "1px solid var(--border)", margin: "0.9em 0" }} />,
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noreferrer" style={{ color: "var(--blue)", textDecoration: "underline" }}>{children}</a>
          ),
        }}>
        {content}
      </ReactMarkdown>
    </div>
  )
}
