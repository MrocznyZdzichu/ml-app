import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, extname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const sourceRoot = join(frontendRoot, "src");
const sourceExtensions = [".ts", ".tsx"];
const files = collectSourceFiles(sourceRoot);
const fileSet = new Set(files);
const graph = new Map(files.map((file) => [file, dependencies(file)]));
const cycles = findCycles(graph);

if (cycles.length) {
  console.error("Frontend import cycles detected:");
  for (const cycle of cycles) {
    console.error(`- ${cycle.map(displayPath).join(" -> ")}`);
  }
  process.exit(1);
}

checkDataWorkspaceBoundaries();

console.log(`Frontend architecture check passed (${files.length} modules, no import cycles).`);

function collectSourceFiles(directory) {
  const collected = [];
  for (const entry of readdirSync(directory)) {
    const path = join(directory, entry);
    if (statSync(path).isDirectory()) {
      collected.push(...collectSourceFiles(path));
    } else if (sourceExtensions.includes(extname(path))) {
      collected.push(path);
    }
  }
  return collected;
}

function dependencies(file) {
  const source = readFileSync(file, "utf8");
  const specifiers = new Set();
  const importPattern = /(?:from\s+|import\s*\()\s*["']([^"']+)["']/g;
  for (const match of source.matchAll(importPattern)) {
    if (match[1].startsWith(".")) {
      specifiers.add(match[1]);
    }
  }
  return [...specifiers]
    .map((specifier) => resolveModule(file, specifier))
    .filter((dependency) => dependency && fileSet.has(dependency));
}

function resolveModule(importer, specifier) {
  const candidate = resolve(dirname(importer), specifier);
  const candidates = [
    candidate,
    ...sourceExtensions.map((extension) => `${candidate}${extension}`),
    ...sourceExtensions.map((extension) => join(candidate, `index${extension}`))
  ];
  return candidates.find((path) => existsSync(path)) ?? null;
}

function findCycles(dependenciesByFile) {
  const visiting = new Set();
  const visited = new Set();
  const stack = [];
  const uniqueCycles = new Map();

  function visit(file) {
    if (visiting.has(file)) {
      const start = stack.indexOf(file);
      const cycle = [...stack.slice(start), file];
      uniqueCycles.set(canonicalCycle(cycle), cycle);
      return;
    }
    if (visited.has(file)) return;

    visiting.add(file);
    stack.push(file);
    for (const dependency of dependenciesByFile.get(file) ?? []) {
      visit(dependency);
    }
    stack.pop();
    visiting.delete(file);
    visited.add(file);
  }

  for (const file of dependenciesByFile.keys()) {
    visit(file);
  }
  return [...uniqueCycles.values()];
}

function canonicalCycle(cycle) {
  const nodes = cycle.slice(0, -1).map(displayPath);
  const rotations = nodes.map((_, index) => [
    ...nodes.slice(index),
    ...nodes.slice(0, index)
  ].join("|"));
  return rotations.sort()[0];
}

function displayPath(file) {
  return relative(sourceRoot, file).replaceAll("\\", "/");
}

function checkDataWorkspaceBoundaries() {
  const dataRoot = join(sourceRoot, "data");
  const facade = join(dataRoot, "DataWorkspacePanels.tsx");
  const requiredModules = [
    join(dataRoot, "analysis", "AnalysisPanel.tsx"),
    join(dataRoot, "browser", "DataBrowsingPanel.tsx"),
    join(dataRoot, "browser", "BrowserDialogs.tsx"),
    join(dataRoot, "browser", "browserDataUtils.ts"),
    join(dataRoot, "profile", "DescriptiveAnalysisPanel.tsx"),
    join(dataRoot, "profile", "DescriptiveProfileDetails.tsx")
  ];
  const missingModules = requiredModules.filter((file) => !existsSync(file));
  const facadeLineCount = readFileSync(facade, "utf8").split(/\r?\n/).length;

  if (missingModules.length || facadeLineCount > 30) {
    console.error(
      "Data workspace architecture boundary violated: keep DataWorkspacePanels.tsx " +
      "as a compatibility facade and implementation in focused analysis/browser/profile modules."
    );
    for (const file of missingModules) {
      console.error(`- missing ${displayPath(file)}`);
    }
    if (facadeLineCount > 30) {
      console.error(`- ${displayPath(facade)} has ${facadeLineCount} lines (maximum 30)`);
    }
    process.exit(1);
  }
}
