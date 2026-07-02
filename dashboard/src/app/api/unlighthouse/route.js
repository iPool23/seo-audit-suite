import { spawn } from "child_process";
import { NextResponse } from "next/server";
import fs from "fs";
import path from "path";
import os from "os";

export async function POST(request) {
  try {
    const { url } = await request.json();
    if (!url) {
      return NextResponse.json({ error: "URL is required" }, { status: 400 });
    }

    // Normalize the URL
    let targetUrl = url.trim();
    if (!/^https?:\/\//i.test(targetUrl)) {
      targetUrl = "https://" + targetUrl;
    }

    // Use a temp output directory so we can read the JSON report afterward
    const outputDir = path.join(os.tmpdir(), "unlighthouse-" + Date.now());

    const stream = new ReadableStream({
      start(controller) {
        const enc = new TextEncoder();
        const send = (type, msg) =>
          controller.enqueue(enc.encode(`${type}:${msg}\n`));

        send("LOG", `[UNLIGHTHOUSE] Starting full-site scan for: ${targetUrl}`);
        send("LOG", `[UNLIGHTHOUSE] Output directory: ${outputDir}`);
        send("LOG", `[UNLIGHTHOUSE] Running: npx unlighthouse --site ${targetUrl} --reporter json`);

        // Spawn npx unlighthouse with JSON reporter + no interactive UI
        const proc = spawn(
          "npx",
          [
            "unlighthouse",
            "--site", targetUrl,
            "--output-path", outputDir,
            "--reporter", "json",
            "--no-cache",
          ],
          {
            shell: true,        // Needed on Windows for npx to resolve
            env: {
              ...process.env,
              FORCE_COLOR: "0", // Disable ANSI color codes in output
              CI: "true",       // Unlighthouse headless/non-interactive mode
            },
          }
        );

        let stdoutBuf = "";
        let stderrBuf = "";

        const handleLine = (line) => {
          const trimmed = line.trim();
          if (!trimmed) return;
          // Strip common ANSI escape sequences before forwarding
          const clean = trimmed.replace(/\x1B\[[0-9;]*[mGKHF]/g, "").trim();
          if (clean) send("LOG", `[UNLIGHTHOUSE] ${clean}`);
        };

        proc.stdout.on("data", (chunk) => {
          stdoutBuf += chunk.toString("utf8");
          const lines = stdoutBuf.split("\n");
          stdoutBuf = lines.pop();
          lines.forEach(handleLine);
        });

        proc.stderr.on("data", (chunk) => {
          stderrBuf += chunk.toString("utf8");
          const lines = stderrBuf.split("\n");
          stderrBuf = lines.pop();
          lines.forEach(handleLine);
        });

        proc.on("close", (code) => {
          // Flush remaining buffers
          if (stdoutBuf.trim()) handleLine(stdoutBuf);
          if (stderrBuf.trim()) handleLine(stderrBuf);

          if (code !== 0 && code !== null) {
            send("LOG", `[UNLIGHTHOUSE] Process exited with code ${code}`);
          }

          // Try to find and parse JSON results
          try {
            const reportFile = path.join(outputDir, "results.json");
            if (fs.existsSync(reportFile)) {
              const raw = fs.readFileSync(reportFile, "utf8");
              const data = JSON.parse(raw);
              send("RESULT", JSON.stringify({ success: true, pages: data, site: targetUrl }));
            } else {
              // Walk the output dir to find any JSON file
              let found = null;
              if (fs.existsSync(outputDir)) {
                const walk = (dir) => {
                  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
                    const full = path.join(dir, entry.name);
                    if (entry.isDirectory()) walk(full);
                    else if (entry.name.endsWith(".json")) {
                      found = full;
                      break;
                    }
                  }
                };
                walk(outputDir);
              }

              if (found) {
                const raw = fs.readFileSync(found, "utf8");
                const data = JSON.parse(raw);
                send("RESULT", JSON.stringify({ success: true, pages: data, site: targetUrl }));
              } else {
                send(
                  "RESULT",
                  JSON.stringify({
                    success: true,
                    pages: null,
                    site: targetUrl,
                    note: "Scan completed. JSON report not found – open the Unlighthouse UI at http://localhost:5678 to see results.",
                  })
                );
              }
            }
          } catch (readErr) {
            send("LOG", `[UNLIGHTHOUSE] Could not read report JSON: ${readErr.message}`);
            send("RESULT", JSON.stringify({ success: false, error: readErr.message, site: targetUrl }));
          }

          controller.close();
        });

        proc.on("error", (err) => {
          send("ERROR", `Failed to start Unlighthouse: ${err.message}. Make sure Node.js and npm are in your PATH.`);
          controller.close();
        });
      },
    });

    return new Response(stream, {
      headers: {
        "Content-Type": "text/plain; charset=utf-8",
        "Transfer-Encoding": "chunked",
      },
    });
  } catch (err) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
