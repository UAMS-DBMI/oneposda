// posda-api-ts is the Posda API server: a TypeScript/Bun port of the
// Python/FastAPI implementation in posda/fastapi (via the Go port in
// posda/goapi).

import { mkdirSync } from "node:fs";
import { loadConfig } from "./config";
import { Db } from "./db";
import { AuthService } from "./auth";
import { App, notFound, withGzip } from "./server";
import { registerAll } from "./routes/index";

const cfg = loadConfig();

try {
  mkdirSync(cfg.tempStoragePath, { recursive: true });
} catch (err) {
  console.warn(
    `warning: could not create temp storage path ${cfg.tempStoragePath}: ${err}`,
  );
}

console.log("database connecting");
let db: Db;
try {
  db = await Db.connect("posda_files");
} catch (err) {
  console.error(`The database is not available: ${err}`);
  process.exit(1);
}
console.log("database connected");

const auth = new AuthService(db, cfg.redisHost, cfg.systemToken);
const app = new App(cfg, db, auth);
registerAll(app);

const server = Bun.serve({
  port: cfg.apiPort,
  idleTimeout: 120,
  routes: app.serveRoutes(),
  fetch(req) {
    return withGzip(req, notFound());
  },
});
console.log(`listening on :${server.port}`);

async function shutdown(signal: string): Promise<void> {
  console.log(`${signal} received, shutting down...`);
  await server.stop();
  await db.close();
  process.exit(0);
}
process.on("SIGTERM", () => void shutdown("SIGTERM"));
process.on("SIGINT", () => void shutdown("SIGINT"));
