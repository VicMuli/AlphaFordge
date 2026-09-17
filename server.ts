import express from "express";
import path from "path";
import fs from "fs/promises";
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

async function startServer() {
  const app = express();
  const PORT = 3000;

  app.use(express.json());

  // API routes
  app.get("/api/config", async (req, res) => {
    try {
      const configPath = path.join(__dirname, 'config.json');
      const data = await fs.readFile(configPath, 'utf-8');
      res.json(JSON.parse(data));
    } catch (e) {
      res.json({});
    }
  });

  app.post("/api/run", (req, res) => {
    // Mock run endpoint
    setTimeout(() => {
      res.json({ status: "ok", message: `Started ${req.body.script}` });
    }, 500);
  });

  // Vite middleware for development
  if (process.env.NODE_ENV !== "production") {
    const { createServer: createViteServer } = await import("vite");
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), 'dist');
    app.use(express.static(distPath));
    app.get('*', (req, res) => {
      res.sendFile(path.join(distPath, 'index.html'));
    });
  }

  app.listen(PORT, "0.0.0.0", () => {
    console.log(`Server running on http://localhost:${PORT}`);
  });
}

startServer();
