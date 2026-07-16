import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const scriptsDirectory = path.dirname(fileURLToPath(import.meta.url));
const repositoryRoot = path.resolve(scriptsDirectory, "..");
const desktopRoot = path.join(repositoryRoot, "apps", "desktop");
const tauriExecutable = path.join(repositoryRoot, "node_modules", ".bin", "tauri");
const requestedArguments = process.argv.slice(2);

if (requestedArguments.length === 0) {
  console.error("Usage: npm run tauri -- <dev|build|...>");
  process.exit(2);
}

const tauriArguments = [...requestedArguments];
if (tauriArguments[0] === "dev") {
  tauriArguments.push("--config", "src-tauri/tauri.dev.conf.json");
}

const result = spawnSync(tauriExecutable, tauriArguments, {
  cwd: desktopRoot,
  env: process.env,
  stdio: "inherit",
  shell: false,
});

if (result.error) {
  console.error(`Unable to start the Tauri CLI: ${result.error.message}`);
  process.exit(1);
}

process.exit(result.status ?? 1);
