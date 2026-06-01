import { spawn } from "child_process";
import { NextResponse } from "next/server";

export async function POST(request) {
  try {
    const { url, maxPages } = await request.json();
    if (!url) {
      return NextResponse.json({ error: "URL is required" }, { status: 400 });
    }

    const pagesLimit = Math.min(Math.max(parseInt(maxPages) || 5, 1), 10);

    const stream = new ReadableStream({
      start(controller) {
        // Spawn the Python process
        const pythonProcess = spawn("python", [
          "-c",
          `
import json, sys
from seo_mcp.seo_audit import crawl_website
try:
    result = crawl_website(sys.argv[1], int(sys.argv[2]))
    print("FINAL_JSON:" + json.dumps(result))
except Exception as e:
    print("FINAL_JSON:" + json.dumps({"error": str(e)}))
          `,
          url,
          String(pagesLimit)
        ], {
          cwd: "c:/Users/Equipo/Documents/Projects/MCP/seo-mcp",
          env: { ...process.env, PYTHONPATH: "src", PYTHONIOENCODING: "utf-8" }
        });

        let buffer = "";

        const handleData = (chunk) => {
          buffer += chunk.toString("utf8");
          let lines = buffer.split("\n");
          buffer = lines.pop(); // Keep partial line in buffer

          for (const line of lines) {
            const trimmed = line.trim();
            if (trimmed.startsWith("PROGRESS: ")) {
              const logMsg = trimmed.substring(10);
              controller.enqueue(new TextEncoder().encode(`LOG:${logMsg}\n`));
            } else if (trimmed.startsWith("FINAL_JSON:")) {
              const jsonStr = trimmed.substring(11);
              controller.enqueue(new TextEncoder().encode(`RESULT:${jsonStr}\n`));
            }
          }
        };

        pythonProcess.stdout.on("data", handleData);
        pythonProcess.stderr.on("data", (data) => {
          const str = data.toString("utf8").trim();
          if (str) {
            console.error("Python Stderr:", str);
          }
        });

        pythonProcess.on("close", (code) => {
          if (buffer.trim()) {
            const trimmed = buffer.trim();
            if (trimmed.startsWith("PROGRESS: ")) {
              const logMsg = trimmed.substring(10);
              controller.enqueue(new TextEncoder().encode(`LOG:${logMsg}\n`));
            } else if (trimmed.startsWith("FINAL_JSON:")) {
              const jsonStr = trimmed.substring(11);
              controller.enqueue(new TextEncoder().encode(`RESULT:${jsonStr}\n`));
            }
          }

          if (code !== 0) {
            controller.enqueue(new TextEncoder().encode(`ERROR:Python execution exited with error code ${code}\n`));
          }
          controller.close();
        });

        pythonProcess.on("error", (err) => {
          controller.enqueue(new TextEncoder().encode(`ERROR:Failed to initiate subprocess: ${err.message}\n`));
          controller.close();
        });
      }
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
