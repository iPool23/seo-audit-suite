"use client";

import { useState, useEffect, useRef } from "react";

export default function Home() {
  const [url, setUrl] = useState("");
  const [maxPages, setMaxPages] = useState(5);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [logs, setLogs] = useState([]);
  const [checkedTasks, setCheckedTasks] = useState({});
  
  const terminalEndRef = useRef(null);

  // Auto-scroll the terminal logs as new ones stream in
  useEffect(() => {
    if (terminalEndRef.current) {
      terminalEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs]);

  // Smooth scroll to the report container once compiled
  useEffect(() => {
    if (result && !loading) {
      setTimeout(() => {
        const reportSection = document.getElementById("report-root");
        if (reportSection) {
          reportSection.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      }, 100);
    }
  }, [result, loading]);

  const handleAudit = async (e) => {
    e.preventDefault();
    if (!url) return;

    setLoading(true);
    setError("");
    setResult(null);
    setLogs(["[SYSTEM] Preparing connection..."]);
    setCheckedTasks({});

    let targetUrl = url.trim();
    if (!/^https?:\/\//i.test(targetUrl)) {
      targetUrl = "https://" + targetUrl;
    }

    try {
      const response = await fetch("/api/audit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: targetUrl, maxPages }),
      });

      if (!response.body) {
        throw new Error("ReadableStream is not supported by your browser.");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop(); // Keep partial line in buffer

        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed.startsWith("LOG:")) {
            const logText = trimmed.substring(4);
            setLogs((prev) => [...prev, `[CRAWLER] ${logText}`]);
          } else if (trimmed.startsWith("RESULT:")) {
            const jsonStr = trimmed.substring(7);
            const parsed = JSON.parse(jsonStr);
            if (parsed.error) {
              throw new Error(parsed.error);
            }
            setResult(parsed);
          } else if (trimmed.startsWith("ERROR:")) {
            const errMsg = trimmed.substring(6);
            throw new Error(errMsg);
          }
        }
      }
    } catch (err) {
      setError(err.message || "An unexpected error occurred during execution.");
      setLogs((prev) => [...prev, `[ERROR] ${err.message || "Execution aborted."}`]);
    } finally {
      setLoading(false);
    }
  };

  const copyToClipboard = () => {
    if (!result) return;
    navigator.clipboard.writeText(JSON.stringify(result, null, 2));
    alert("Audit results JSON copied to clipboard!");
  };

  const getScoreColor = (score) => {
    if (score >= 85) return "hsl(var(--color-pass))";
    if (score >= 60) return "hsl(var(--color-warn))";
    return "hsl(var(--color-fail))";
  };

  // Compile all crawling metrics into three distinct action priority tiers
  const compileRoadmap = (data) => {
    if (!data) return { critical: [], medium: [], low: [] };

    const critical = [];
    const medium = [];
    const low = [];

    // 1. SSL/HTTPS site checks
    const ssl = data.site_checks?.ssl;
    if (ssl) {
      if (!ssl.uses_https) {
        critical.push({ id: "ssl_https", text: "🚨 Habilitar SSL/HTTPS: El dominio no utiliza HTTPS (conexión insegura)." });
      } else if (ssl.certificate && !ssl.certificate.valid) {
        critical.push({ id: "ssl_cert", text: "🚨 Corregir Certificado SSL: El certificado HTTPS no es válido o está expirado." });
      }
    }

    // 2. Robots.txt and Sitemap.xml site checks
    const robots = data.site_checks?.robots_txt;
    if (robots && !robots.exists) {
      medium.push({ id: "robots_missing", text: "⚠️ Crear robots.txt: Falta el archivo de directivas en la raíz del servidor." });
    }
    const sitemap = data.site_checks?.sitemap;
    if (sitemap) {
      if (!sitemap.exists) {
        medium.push({ id: "sitemap_missing", text: "⚠️ Crear sitemap.xml: Falta el archivo sitemap en el servidor para guiar a los bots." });
      } else if (sitemap.url_count === 0) {
        medium.push({ id: "sitemap_empty", text: "⚠️ Sitemap Vacío: El archivo sitemap.xml no contiene ninguna URL indexable." });
      }
    }
    if (robots && robots.exists && (!robots.sitemaps_found || robots.sitemaps_found.length === 0)) {
      low.push({ id: "robots_no_sitemap", text: "ℹ️ Declarar Sitemap en robots.txt: Ayuda a los bots añadiendo la directiva 'Sitemap: [URL]'." });
    }

    // 3. Page specific loop audits
    let internalBrokenCount = 0;
    let externalBrokenCount = 0;
    let redirectChainCount = 0;
    let invalidJsonLdCount = 0;
    let missingLangCount = 0;
    let missingDescCount = 0;
    let noindexCount = 0;
    let missingAltTotal = 0;

    data.pages.forEach((page) => {
      if (page.technical?.noindex) noindexCount++;
      if (page.redirect_count > 1) redirectChainCount++;
      if (page.technical?.json_ld?.invalid_count > 0) invalidJsonLdCount++;
      
      if (page.broken_links?.broken?.length > 0) {
        page.broken_links.broken.forEach((bl) => {
          if (bl.type === "internal") internalBrokenCount++;
          else if (bl.type === "external") externalBrokenCount++;
        });
      }
      
      if (!page.geo_optimization?.html_lang) missingLangCount++;
      if (!page.meta_description) missingDescCount++;
      if (page.images_missing_alt > 0) missingAltTotal += page.images_missing_alt;
    });

    if (noindexCount > 0) {
      critical.push({ id: "noindex_blocks", text: `🚨 Quitar bloqueos noindex: Hay ${noindexCount} página(s) bloqueando la indexación de Google.` });
    }
    if (internalBrokenCount > 0) {
      critical.push({ id: "internal_broken", text: `🚨 Corregir Enlaces Internos Rotos: Se detectaron ${internalBrokenCount} enlaces rotos internos (HTTP 404/5xx).` });
    }
    if (redirectChainCount > 0) {
      critical.push({ id: "redirect_chains", text: `🚨 Resolver Cadenas de Redirección: Hay ${redirectChainCount} página(s) con redirecciones excesivas (>1 salto).` });
    }

    if (externalBrokenCount > 0) {
      medium.push({ id: "external_broken", text: `⚠️ Corregir Enlaces Externos Rotos: Se detectaron ${externalBrokenCount} enlaces salientes rotos que apuntan a webs caídas.` });
    }
    if (invalidJsonLdCount > 0) {
      medium.push({ id: "invalid_json_ld", text: `⚠️ Corregir Sintaxis JSON-LD: Se encontraron ${invalidJsonLdCount} bloque(s) de datos estructurados con errores de código.` });
    }
    if (missingLangCount > 0) {
      medium.push({ id: "missing_lang", text: `⚠️ Añadir idioma HTML: Hay ${missingLangCount} página(s) sin declarar el atributo 'lang' en la etiqueta HTML.` });
    }
    if (missingDescCount > 0) {
      medium.push({ id: "missing_desc", text: `⚠️ Escribir Meta Descripciones: Hay ${missingDescCount} página(s) sin etiqueta de descripción de fragmento.` });
    }

    if (missingAltTotal > 0) {
      low.push({ id: "missing_alts", text: `ℹ️ Optimizar Imágenes (Alt Text): Se encontraron ${missingAltTotal} imágenes sin descripción alt.` });
    }

    // 4. Duplicate metadata checks
    const dupes = data.duplicate_content;
    if (dupes) {
      if (dupes.duplicate_titles?.length > 0) {
        critical.push({ id: "duplicate_titles", text: `🚨 Resolver Títulos Duplicados: Se encontraron ${dupes.duplicate_titles.length} grupos de títulos idénticos entre páginas.` });
      }
      if (dupes.duplicate_descriptions?.length > 0) {
        low.push({ id: "duplicate_descs", text: `ℹ️ Resolver Meta Descripciones Duplicadas: Se encontraron ${dupes.duplicate_descriptions.length} meta descripciones duplicadas.` });
      }
    }

    return { critical, medium, low };
  };

  const roadmap = compileRoadmap(result);
  const totalTasks = roadmap.critical.length + roadmap.medium.length + roadmap.low.length;
  const completedTasks = Object.values(checkedTasks).filter(Boolean).length;
  const progressPercent = totalTasks > 0 ? (completedTasks / totalTasks) * 100 : 0;

  const toggleTask = (taskId) => {
    setCheckedTasks((prev) => ({
      ...prev,
      [taskId]: !prev[taskId],
    }));
  };

  return (
    <main className="container">
      {/* Header section */}
      <header style={{ textAlign: "center", marginBottom: "4rem" }} className="no-print">
        <h1>SEO MCP Web Audit Suite</h1>
        <p className="muted">
          State-of-the-art technical SEO analysis, including SSL socket validations, broken link detections, redirect chains, and JSON-LD schema parsing.
        </p>
      </header>

      {/* Audit Target Config Form */}
      <form onSubmit={handleAudit} className="search-box no-print">
        <div className="input-glow-wrap">
          <input
            type="text"
            className="url-input"
            placeholder="Enter website domain or URL (e.g. ucv.edu.pe)"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            disabled={loading}
            required
          />
        </div>
        <button type="submit" className="btn-submit" disabled={loading || !url}>
          {loading ? "Auditing..." : "Audit Website"}
        </button>
      </form>

      {/* Max Pages Slider Configuration */}
      <div className="config-row no-print">
        <div className="pages-config">
          <span>Max Crawl Pages:</span>
          <input
            type="range"
            min="1"
            max="10"
            value={maxPages}
            onChange={(e) => setMaxPages(parseInt(e.target.value))}
            disabled={loading}
          />
          <span className="value">{maxPages}</span>
        </div>
      </div>

      {/* Error View */}
      {error && (
        <div className="glass" style={{ padding: "2rem", borderColor: "rgba(239, 68, 68, 0.3)", maxWidth: "760px", margin: "2rem auto", background: "rgba(239, 68, 68, 0.03)" }}>
          <h2 style={{ color: "hsl(var(--color-fail))", fontSize: "1.25rem" }}>
            ⚠️ Technical Execution Error
          </h2>
          <p style={{ marginTop: "0.5rem", fontSize: "0.9375rem" }}>{error}</p>
        </div>
      )}

      {/* Stepper & Live Streaming Terminal Loader */}
      {loading && (
        <section className="glass loader-screen no-print">
          <div className="spinner-wrap">
            <div className="spinner"></div>
          </div>
          <h2 style={{ justifyContent: "center" }}>Live Audit in Progress</h2>
          <p className="muted" style={{ fontSize: "0.9375rem" }}>
            Connecting to core Python subprocess. Compiling live diagnostics.
          </p>

          {/* Real-time Glowing Terminal Logs */}
          <div className="terminal-box">
            <div className="terminal-header">
              <div className="terminal-dots">
                <span className="terminal-dot"></span>
                <span className="terminal-dot"></span>
                <span className="terminal-dot"></span>
              </div>
              <span>SEO-CRAWLER-LOGS.SH</span>
            </div>
            {logs.map((log, idx) => (
              <div key={idx} className="log-entry">
                <span className="log-prefix">&gt;</span>
                <span className="log-text">{log}</span>
              </div>
            ))}
            <div ref={terminalEndRef} />
          </div>
        </section>
      )}

      {/* Report view once loaded */}
      {result && !loading && (
        <section id="report-root" style={{ animation: "fadeIn 0.8s ease-in-out" }}>
          
          {/* Action and Sharing buttons */}
          <div className="actions-row no-print">
            <button className="btn-secondary" onClick={copyToClipboard}>
              <svg viewBox="0 0 24 24" width="16" height="16">
                <path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z" />
              </svg>
              Copy JSON
            </button>
            <button className="btn-secondary" onClick={() => window.print()}>
              <svg viewBox="0 0 24 24" width="16" height="16">
                <path d="M19 8H5c-1.66 0-3 1.34-3 3v6h4v4h12v-4h4v-6c0-1.66-1.34-3-3-3zm-3 11H8v-5h8v5zm3-7c-.55 0-1-.45-1-1s.45-1 1-1 1 .45 1 1-.45 1-1 1zm-1-9H6v4h12V3z" />
              </svg>
              Print to PDF
            </button>
          </div>

          {/* Actionable SEO Priorities Roadmap Checklist */}
          <div className="glass roadmap-panel no-print">
            <div className="roadmap-summary-bar">
              <div>
                <h2>📋 Plan de Acción SEO (Roadmap de Prioridades)</h2>
                <p className="muted" style={{ fontSize: "0.8125rem", marginTop: "0.25rem" }}>
                  Tareas prioritarias a realizar organizadas por nivel de impacto. Marca las tareas que vayas completando.
                </p>
              </div>
              <div className="roadmap-progress">
                <span>Completadas: <strong>{completedTasks} / {totalTasks}</strong></span>
                <div className="progress-bar-bg">
                  <div className="progress-bar-fill" style={{ width: `${progressPercent}%` }}></div>
                </div>
              </div>
            </div>

            {totalTasks === 0 ? (
              <div className="panel-empty" style={{ padding: "2rem 0" }}>
                <span className="icon">🏆</span>
                <span style={{ fontWeight: "700", color: "hsl(var(--color-pass))" }}>Sitio Web Optimizado al Máximo</span>
                <p className="muted" style={{ fontSize: "0.75rem" }}>¡No se identificaron tareas pendientes! Todas las validaciones de SEO y GEO están completas.</p>
              </div>
            ) : (
              <div className="roadmap-tiers-container">
                {/* Critical Tier */}
                {roadmap.critical.length > 0 && (
                  <div className="roadmap-tier">
                    <div className="roadmap-tier-header tier-critical">
                      <span>🚨 Alto Impacto (Crítico)</span>
                    </div>
                    <ul className="roadmap-list">
                      {roadmap.critical.map((task) => (
                        <li key={task.id} className={`roadmap-item ${checkedTasks[task.id] ? "checked" : ""}`} onClick={() => toggleTask(task.id)}>
                          <input type="checkbox" className="roadmap-checkbox" checked={!!checkedTasks[task.id]} readOnly />
                          <span className="roadmap-text">{task.text}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Medium Tier */}
                {roadmap.medium.length > 0 && (
                  <div className="roadmap-tier">
                    <div className="roadmap-tier-header tier-medium">
                      <span>⚠️ Medio Impacto (Recomendado)</span>
                    </div>
                    <ul className="roadmap-list">
                      {roadmap.medium.map((task) => (
                        <li key={task.id} className={`roadmap-item ${checkedTasks[task.id] ? "checked" : ""}`} onClick={() => toggleTask(task.id)}>
                          <input type="checkbox" className="roadmap-checkbox" checked={!!checkedTasks[task.id]} readOnly />
                          <span className="roadmap-text">{task.text}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Low Tier */}
                {roadmap.low.length > 0 && (
                  <div className="roadmap-tier">
                    <div className="roadmap-tier-header tier-low">
                      <span>ℹ️ Bajo Impacto (Optimización)</span>
                    </div>
                    <ul className="roadmap-list">
                      {roadmap.low.map((task) => (
                        <li key={task.id} className={`roadmap-item ${checkedTasks[task.id] ? "checked" : ""}`} onClick={() => toggleTask(task.id)}>
                          <input type="checkbox" className="roadmap-checkbox" checked={!!checkedTasks[task.id]} readOnly />
                          <span className="roadmap-text">{task.text}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Overview Header Panel */}
          <div className="glass report-header" style={{ padding: "2.5rem" }}>
            <div className="domain-info">
              <span className="muted" style={{ fontSize: "0.8125rem", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                Technical SEO Audit Report
              </span>
              <div className="domain-badge">{result.input}</div>
              <p className="muted" style={{ fontSize: "0.875rem", marginTop: "0.5rem" }}>
                Start URL: <a href={result.start_url} target="_blank" rel="noreferrer" style={{ color: "#a5b4fc", textDecoration: "none" }}>{result.start_url}</a>
              </p>
            </div>

            {/* Score Ring Gauge */}
            {result.aggregate && (
              <div className="score-circle-container">
                <svg className="score-circle">
                  <circle className="score-circle-bg" cx="70" cy="70" r="45"></circle>
                  <circle
                    className="score-circle-fill"
                    cx="70"
                    cy="70"
                    r="45"
                    style={{
                      stroke: getScoreColor(result.aggregate.average_score),
                      "--dashoffset": 283 - (283 * result.aggregate.average_score) / 100
                    }}
                  ></circle>
                </svg>
                <div className="score-center-text">
                  <span className="score-num">{Math.round(result.aggregate.average_score)}</span>
                  <span className="score-label">Score</span>
                </div>
              </div>
            )}
          </div>

          {/* Technical Assets Grid (SSL, Robots, Sitemap) */}
          <div className="section-grid-3">
            
            {/* SSL Certificate Card */}
            {result.site_checks?.ssl && (() => {
              const ssl = result.site_checks.ssl;
              const hasValidCert = ssl.uses_https && ssl.certificate?.valid;
              let cardClass = "glass asset-card card-pass";
              let badgeType = "badge-pass";
              let statusText = "Secure";

              if (!ssl.uses_https) {
                cardClass = "glass asset-card card-fail";
                badgeType = "badge-fail";
                statusText = "Insecure";
              } else if (!ssl.certificate?.valid) {
                cardClass = "glass asset-card card-warn";
                badgeType = "badge-warn";
                statusText = "Warn";
              }

              return (
                <div className={cardClass}>
                  <div className="card-icon-title">
                    <span className="card-title">HTTPS & SSL Status</span>
                    <span className={`status-badge ${badgeType}`}>{statusText}</span>
                  </div>
                  <div className="card-stats">
                    <div className="stat-item">
                      <span className="stat-label">Uses HTTPS</span>
                      <span className="stat-val">{ssl.uses_https ? "Yes" : "No"}</span>
                    </div>
                    <div className="stat-item">
                      <span className="stat-label">HTTP to HTTPS Redirect</span>
                      <span className="stat-val">{ssl.http_redirects_to_https ? "Active" : "None"}</span>
                    </div>
                    {ssl.certificate && (
                      <>
                        <div className="stat-item">
                          <span className="stat-label">Issuer</span>
                          <span className="stat-val" title={ssl.certificate.issuer}>{ssl.certificate.issuer}</span>
                        </div>
                        <div className="stat-item">
                          <span className="stat-label">Days Remaining</span>
                          <span className="stat-val">{ssl.certificate.days_remaining}</span>
                        </div>
                      </>
                    )}
                  </div>
                  {ssl.issues?.length > 0 && (
                    <div className="card-errors">
                      <div className="card-errors-title">SSL Audits</div>
                      <ul className="card-errors-list">
                        {ssl.issues.map((issue, idx) => (
                          <li key={idx}>⚠️ {issue}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              );
            })()}

            {/* Robots.txt Card */}
            {result.site_checks?.robots_txt && (() => {
              const robots = result.site_checks.robots_txt;
              let cardClass = "glass asset-card card-pass";
              let badgeType = "badge-pass";
              let statusText = "Active";

              if (!robots.exists) {
                cardClass = "glass asset-card card-warn";
                badgeType = "badge-warn";
                statusText = "Missing";
              }

              return (
                <div className={cardClass}>
                  <div className="card-icon-title">
                    <span className="card-title">robots.txt Status</span>
                    <span className={`status-badge ${badgeType}`}>{statusText}</span>
                  </div>
                  <div className="card-stats">
                    <div className="stat-item">
                      <span className="stat-label">HTTP Code</span>
                      <span className="stat-val">{robots.status_code || "N/A"}</span>
                    </div>
                    <div className="stat-item">
                      <span className="stat-label">Sitemaps Declared</span>
                      <span className="stat-val">{robots.sitemaps_found?.length || 0}</span>
                    </div>
                    <div className="stat-item">
                      <span className="stat-label">URL Link</span>
                      <span className="stat-val">
                        {robots.exists ? (
                          <a href={robots.url} target="_blank" rel="noreferrer" style={{ color: "#a5b4fc" }}>
                            View Robots
                          </a>
                        ) : (
                          "None"
                        )}
                      </span>
                    </div>
                  </div>
                  {robots.issues?.length > 0 && (
                    <div className="card-errors">
                      <div className="card-errors-title">Robots Audits</div>
                      <ul className="card-errors-list">
                        {robots.issues.map((issue, idx) => (
                          <li key={idx}>⚠️ {issue}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              );
            })()}

            {/* Sitemap.xml Card */}
            {result.site_checks?.sitemap && (() => {
              const sitemap = result.site_checks.sitemap;
              let cardClass = "glass asset-card card-pass";
              let badgeType = "badge-pass";
              let statusText = sitemap.exists ? "Active" : "Missing";

              if (!sitemap.exists) {
                cardClass = "glass asset-card card-fail";
                badgeType = "badge-fail";
              } else if (sitemap.issues?.length > 0) {
                cardClass = "glass asset-card card-warn";
                badgeType = "badge-warn";
              }

              return (
                <div className={cardClass}>
                  <div className="card-icon-title">
                    <span className="card-title">sitemap.xml Status</span>
                    <span className={`status-badge ${badgeType}`}>{statusText}</span>
                  </div>
                  <div className="card-stats">
                    <div className="stat-item">
                      <span className="stat-label">HTTP Code</span>
                      <span className="stat-val">{sitemap.status_code || "N/A"}</span>
                    </div>
                    <div className="stat-item">
                      <span className="stat-label">URLs Listed</span>
                      <span className="stat-val">{sitemap.url_count !== null ? `${sitemap.url_count} URLs` : "N/A"}</span>
                    </div>
                    <div className="stat-item">
                      <span className="stat-label">Discovery Path</span>
                      <span className="stat-val">{sitemap.via_robots ? "Via Robots.txt" : "Default Root"}</span>
                    </div>
                  </div>
                  {sitemap.issues?.length > 0 && (
                    <div className="card-errors">
                      <div className="card-errors-title">Sitemap Audits</div>
                      <ul className="card-errors-list">
                        {sitemap.issues.map((issue, idx) => (
                          <li key={idx}>⚠️ {issue}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              );
            })()}

          </div>

          {/* GEO (Generative & Geographical) Optimization Panels */}
          <div className="section-grid-2">
            
            {/* AI Agent crawling permissions */}
            <div className="glass panel-card">
              <h2>🤖 Generative AI Agents (robots.txt permissions)</h2>
              <p className="muted" style={{ fontSize: "0.8125rem", marginBottom: "1.25rem" }}>
                Auditing robots.txt block directives targeting major generative search crawler bots.
              </p>
              {(() => {
                const aiAgents = result.site_checks?.robots_txt?.ai_agents;
                if (!aiAgents) {
                  return (
                    <div className="panel-empty">
                      <span className="icon">🤖</span>
                      <span>No robots.txt data found</span>
                    </div>
                  );
                }

                return (
                  <div className="ai-grid">
                    {Object.entries(aiAgents).map(([botName, status]) => {
                      const displayStatus = status === "Allowed" ? "Allowed" : "Blocked";
                      const statusClass = status === "Allowed" ? "ai-allowed" : "ai-blocked";
                      return (
                        <div key={botName} className="ai-card">
                          <span className="ai-bot-name">{botName.replace("-extended", "").replace("bot", " Bot")}</span>
                          <span className={`ai-bot-status ${statusClass}`}>{displayStatus}</span>
                        </div>
                      );
                    })}
                  </div>
                );
              })()}
            </div>

            {/* Geotargeting & Generative Optimization Metrics */}
            <div className="glass panel-card">
              <h2>🌐 Local Geotargeting & Semantic Citability</h2>
              <p className="muted" style={{ fontSize: "0.8125rem", marginBottom: "1.25rem" }}>
                Auditing geographical targeting parameters and semantic markers preferred by generative AI engines.
              </p>
              {(() => {
                let totalHreflangs = 0;
                let htmlLangs = new Set();
                let geoCoordinates = "None declared";
                let totalConversational = 0;
                let totalStats = 0;
                let totalDefs = 0;

                result.pages.forEach((page) => {
                  const geo = page.geo_optimization;
                  if (geo) {
                    totalHreflangs += geo.hreflang_tags?.length || 0;
                    if (geo.html_lang) htmlLangs.add(geo.html_lang);
                    totalConversational += geo.conversational_headings_count || 0;
                    totalStats += geo.statistics_count || 0;
                    totalDefs += geo.definitions_count || 0;
                    
                    if (geo.geo_tags) {
                      const pos = geo.geo_tags["geo.position"] || geo.geo_tags["icbm"];
                      if (pos) geoCoordinates = pos;
                    }
                  }
                });

                const htmlLangsArr = Array.from(htmlLangs);

                return (
                  <div className="card-stats">
                    <div className="stat-item">
                      <span className="stat-label">HTML Declared Langs</span>
                      <span className="stat-val">{htmlLangsArr.length > 0 ? htmlLangsArr.join(", ") : "None"}</span>
                    </div>
                    <div className="stat-item">
                      <span className="stat-label">hreflang Alternate Targets</span>
                      <span className="stat-val">{totalHreflangs} links</span>
                    </div>
                    <div className="stat-item">
                      <span className="stat-label">Geo Location Coordinates</span>
                      <span className="stat-val" style={{ fontFamily: "var(--font-mono)", fontSize: "0.8125rem" }}>{geoCoordinates}</span>
                    </div>
                    <div className="stat-item">
                      <span className="stat-label">Conversational Headings (Q&A)</span>
                      <span className="stat-val">{totalConversational} headings</span>
                    </div>
                    <div className="stat-item">
                      <span className="stat-label">Numerical Data & Statistics</span>
                      <span className="stat-val">{totalStats} counts</span>
                    </div>
                    <div className="stat-item">
                      <span className="stat-label">Entity Definition Anchors</span>
                      <span className="stat-val">{totalDefs} definitions</span>
                    </div>
                  </div>
                );
              })()}
            </div>

          </div>

          {/* Section Grid 2 (Broken Links & JSON-LD validation) */}
          <div className="section-grid-2">
            
            {/* Broken Links Panel */}
            <div className="glass panel-card">
              <h2>🔗 Broken Links (404/5xx Verification)</h2>
              {(() => {
                const brokenLinks = [];
                result.pages.forEach((page) => {
                  if (page.broken_links?.broken?.length > 0) {
                    page.broken_links.broken.forEach((bl) => {
                      brokenLinks.push({
                        url: bl.url,
                        statusCode: bl.status_code,
                        error: bl.error,
                        type: bl.type,
                        pageFound: page.final_url || page.url,
                      });
                    });
                  }
                });

                if (brokenLinks.length === 0) {
                  return (
                    <div className="panel-empty">
                      <span className="icon">✅</span>
                      <span>No broken links detected</span>
                      <p className="muted" style={{ fontSize: "0.75rem" }}>Checked link samples up to 10 internal and 10 external per page in parallel.</p>
                    </div>
                  );
                }

                return (
                  <ul className="panel-list">
                    {brokenLinks.map((bl, idx) => (
                      <li key={idx}>
                        <div style={{ wordBreak: "break-all" }}>
                          <span className={`pill-label pill-${bl.type}`}>{bl.type}</span>
                          <strong>{bl.url}</strong>
                        </div>
                        <div className="meta" style={{ marginTop: "0.25rem" }}>
                          Found on: {bl.pageFound}
                        </div>
                        <div className="meta" style={{ color: "hsl(var(--color-fail))", fontWeight: "600" }}>
                          {bl.statusCode ? `HTTP Status ${bl.statusCode}` : `Error: ${bl.error}`}
                        </div>
                      </li>
                    ))}
                  </ul>
                );
              })()}
            </div>

            {/* JSON-LD Schemas Panel */}
            <div className="glass panel-card">
              <h2>🗂️ Structured Data (JSON-LD Schemas)</h2>
              {(() => {
                let totalSchemas = 0;
                let validSchemas = 0;
                let invalidSchemas = 0;
                const typesFound = new Set();
                const allErrors = [];

                result.pages.forEach((page) => {
                  const jld = page.technical?.json_ld;
                  if (jld) {
                    totalSchemas += jld.count || 0;
                    validSchemas += jld.valid_count || 0;
                    invalidSchemas += jld.invalid_count || 0;
                    if (jld.types_found) jld.types_found.forEach(t => typesFound.add(t));
                    if (jld.errors) jld.errors.forEach(e => allErrors.push({ err: e, page: page.final_url || page.url }));
                  }
                });

                if (totalSchemas === 0) {
                  return (
                    <div className="panel-empty">
                      <span className="icon">📂</span>
                      <span>No JSON-LD blocks discovered</span>
                      <p className="muted" style={{ fontSize: "0.75rem" }}>Ensure schemas are rendered in script tags of type application/ld+json.</p>
                    </div>
                  );
                }

                return (
                  <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
                    <div className="card-stats" style={{ flexDirection: "row", flexWrap: "wrap", gap: "2rem" }}>
                      <div className="pages-config" style={{ padding: "0.75rem 1.25rem" }}>
                        <span>Total blocks:</span>
                        <span className="value" style={{ color: "#c084fc" }}>{totalSchemas}</span>
                      </div>
                      <div className="pages-config" style={{ padding: "0.75rem 1.25rem" }}>
                        <span>Valid blocks:</span>
                        <span className="value" style={{ color: "hsl(var(--color-pass))" }}>{validSchemas}</span>
                      </div>
                      <div className="pages-config" style={{ padding: "0.75rem 1.25rem" }}>
                        <span>Errors:</span>
                        <span className="value" style={{ color: invalidSchemas > 0 ? "hsl(var(--color-fail))" : "hsl(var(--color-pass))" }}>{invalidSchemas}</span>
                      </div>
                    </div>

                    <div>
                      <h3 style={{ fontSize: "0.875rem", marginBottom: "0.5rem", color: "hsl(var(--text-secondary))", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                        Types Discovered
                      </h3>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
                        {Array.from(typesFound).map((type, idx) => (
                          <span key={idx} className="quick-badge" style={{ color: "#a5b4fc" }}>
                            {type}
                          </span>
                        ))}
                        {typesFound.size === 0 && <span className="muted" style={{ fontSize: "0.875rem" }}>None identified</span>}
                      </div>
                    </div>

                    {allErrors.length > 0 && (
                      <div>
                        <h3 style={{ fontSize: "0.875rem", marginBottom: "0.5rem", color: "hsl(var(--color-fail))", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                          Schema Validation Failures
                        </h3>
                        <ul className="panel-list">
                          {allErrors.map((errObj, idx) => (
                            <li key={idx} style={{ borderColor: "rgba(239, 68, 68, 0.2)", background: "rgba(239, 68, 68, 0.02)" }}>
                              <strong style={{ color: "#fca5a5" }}>{errObj.err}</strong>
                              <span className="meta">Found on page: {errObj.page}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                );
              })()}
            </div>

          </div>

          {/* Duplicate Content Panel (Title & Meta duplicate counts) */}
          {result.duplicate_content && (
            <div className="glass panel-card" style={{ marginBottom: "2.5rem" }}>
              <h2>📝 Duplicate Title & Meta Description Scan</h2>
              {(() => {
                const dupes = result.duplicate_content;
                const totalTitles = dupes.duplicate_titles?.length || 0;
                const totalDescs = dupes.duplicate_descriptions?.length || 0;

                if (!dupes.has_duplicates) {
                  return (
                    <div className="panel-empty">
                      <span className="icon">✅</span>
                      <span>No duplicate metadata discovered</span>
                      <p className="muted" style={{ fontSize: "0.75rem" }}>All successfully crawled pages have unique title and meta description elements.</p>
                    </div>
                  );
                }

                return (
                  <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
                    {totalTitles > 0 && (
                      <div>
                        <h3 style={{ fontSize: "0.875rem", marginBottom: "0.75rem", color: "#fbbf24", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                          Duplicate Title Elements
                        </h3>
                        <ul className="panel-list">
                          {dupes.duplicate_titles.map((dt, idx) => (
                            <li key={idx}>
                              <strong>&ldquo;{dt.title}&rdquo;</strong>
                              <div className="meta" style={{ marginTop: "0.25rem" }}>
                                Appears {dt.count} times across:
                              </div>
                              <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem", marginTop: "0.5rem" }}>
                                {dt.urls.map((u, uIdx) => (
                                  <a key={uIdx} href={u} target="_blank" rel="noreferrer" style={{ color: "#a5b4fc", textDecoration: "none", fontSize: "0.8125rem", wordBreak: "break-all" }}>
                                    • {u}
                                  </a>
                                ))}
                              </div>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {totalDescs > 0 && (
                      <div style={{ marginTop: "1rem" }}>
                        <h3 style={{ fontSize: "0.875rem", marginBottom: "0.75rem", color: "#fbbf24", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                          Duplicate Meta Descriptions
                        </h3>
                        <ul className="panel-list">
                          {dupes.duplicate_descriptions.map((dd, idx) => (
                            <li key={idx}>
                              <strong>&ldquo;{dd.description}&rdquo;</strong>
                              <div className="meta" style={{ marginTop: "0.25rem" }}>
                                Appears {dd.count} times across:
                              </div>
                              <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem", marginTop: "0.5rem" }}>
                                {dd.urls.map((u, uIdx) => (
                                  <a key={uIdx} href={u} target="_blank" rel="noreferrer" style={{ color: "#a5b4fc", textDecoration: "none", fontSize: "0.8125rem", wordBreak: "break-all" }}>
                                    • {u}
                                  </a>
                                ))}
                              </div>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                );
              })()}
            </div>
          )}

          {/* Crawl Page Details Table */}
          <div className="glass panel-card">
            <h2>📄 Crawled Pages & Direct Page Audits</h2>
            <p className="muted" style={{ fontSize: "0.875rem", marginBottom: "1.5rem" }}>
              Detailed structural results, redirects, indexability status, and dedicated recommendations for each page.
            </p>

            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Score</th>
                    <th>Page Details</th>
                    <th>Indexable</th>
                    <th>Redirect Hops</th>
                    <th>Issues Found</th>
                    <th>Recommendations</th>
                  </tr>
                </thead>
                <tbody>
                  {result.pages.map((page, idx) => {
                    let scoreClass = "score-pill score-pass";
                    if (page.score < 60) scoreClass = "score-pill score-fail";
                    else if (page.score < 85) scoreClass = "score-pill score-warn";

                    return (
                      <tr key={idx}>
                        <td>
                          <div className={scoreClass}>{Math.round(page.score)}</div>
                        </td>
                        <td>
                          <div className="page-title-url">
                            <strong title={page.title || "No Title tag"}>
                              {page.title || "Untitled Document"}
                            </strong>
                            <a href={page.final_url || page.url} target="_blank" rel="noreferrer" title={page.final_url || page.url}>
                              {page.final_url || page.url}
                            </a>
                          </div>
                        </td>
                        <td>
                          <span className={`quick-badge ${page.indexable ? "index-yes" : "index-no"}`}>
                            {page.indexable ? "Yes" : "No"}
                          </span>
                        </td>
                        <td>
                          <div style={{ textAlign: "center", fontWeight: "700", color: page.redirect_count > 1 ? "hsl(var(--color-fail))" : "inherit" }}>
                            {page.redirect_count || 0}
                          </div>
                        </td>
                        <td className="issues-cell">
                          {page.issues?.length > 0 ? (
                            <ul>
                              {page.issues.map((issue, issueIdx) => (
                                <li key={issueIdx} className="warn-item">• {issue}</li>
                              ))}
                            </ul>
                          ) : (
                            <span className="muted" style={{ fontSize: "0.8125rem" }}>No structural issues</span>
                          )}
                        </td>
                        <td className="issues-cell">
                          {page.recommendations?.length > 0 ? (
                            <ul>
                              {page.recommendations.map((rec, recIdx) => (
                                <li key={recIdx}>• {rec}</li>
                              ))}
                            </ul>
                          ) : (
                            <span style={{ color: "hsl(var(--color-pass))", fontSize: "0.8125rem" }}>✅ Optimizations complete</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

        </section>
      )}

      <footer className="no-print">
        <p>SEO MCP Dashboard &bull; Powered by Google DeepMind Advanced Agentic Coding &bull; 2026</p>
      </footer>
    </main>
  );
}
