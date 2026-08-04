const capabilities = [
  ["Portable engine", "A deterministic C++ core designed for native, WebAssembly, desktop, and cloud execution."],
  ["Local-first", "Analyze private financial data on your own machine or inside customer-managed infrastructure."],
  ["Cloud-scalable", "Run versioned calculations as stateless, partitionable jobs across managed workers."],
  ["Open formats", "Build around Arrow, Parquet, explicit schemas, and reproducible dataset manifests."],
];

export default function Home() {
  return (
    <main>
      <nav>
        <strong>Pacioli</strong>
        <a href="https://github.com/aengebretson/pacioli">GitHub</a>
      </nav>
      <section className="hero">
        <p className="eyebrow">Open financial infrastructure</p>
        <h1>One financial engine. From private local data to managed cloud scale.</h1>
        <p className="lede">
          Pacioli is an open-source financial data and accounting engine for trading systems,
          built around deterministic semantics, portable execution, and auditable datasets.
        </p>
        <div className="actions">
          <a className="primary" href="https://github.com/aengebretson/pacioli">View the project</a>
          <a href="https://github.com/aengebretson/pacioli#build-the-c-engine">Build locally</a>
        </div>
      </section>
      <section className="grid" aria-label="Pacioli capabilities">
        {capabilities.map(([title, description]) => (
          <article key={title}>
            <h2>{title}</h2>
            <p>{description}</p>
          </article>
        ))}
      </section>
      <footer>Apache-2.0 · Built in the open</footer>
    </main>
  );
}
