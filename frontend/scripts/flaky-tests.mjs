// The flaky-test report (#1194). CI retries a failed e2e test once; one that passes
// the second time is "flaky" in Playwright's JSON report, and may be a race in the
// app rather than in the test (#1168 hid as one for a while).
//
//   node scripts/flaky-tests.mjs shard <report.json> <out.json>
//     After a shard: lists its flaky tests in the job summary, marks each with a
//     warning, and writes <out.json> (flaky and failed tests) when there are any.
//   node scripts/flaky-tests.mjs rollup <out-dir>
//     Weekly: gathers every shard's <out.json> of the last FLAKY_DAYS days (14) from
//     the repository's artifacts, and lists the tests that were flaky, or failed and
//     then passed when the job was re-run, with how often and where.
//
// It only reports: whatever goes wrong here, it exits 0 and never fails a build.
import { execFileSync } from "node:child_process";
import { appendFileSync, existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const summary = (markdown) => {
  if (process.env.GITHUB_STEP_SUMMARY) appendFileSync(process.env.GITHUB_STEP_SUMMARY, markdown + "\n");
  else console.log(markdown);
};
const cell = (text) => String(text).replaceAll("|", "\\|").replaceAll("\n", " ");
// GitHub's workflow commands need these escaped in a message.
const command = (text) => String(text).replaceAll("%", "%25").replaceAll("\r", "%0D").replaceAll("\n", "%0A");
const firstLine = (message) =>
  (message ?? "")
    .replace(/\u001b\[[0-9;]*m/g, "")
    .split("\n")
    .find((line) => line.trim())
    ?.trim()
    .slice(0, 200) ?? "";

// Every test of a Playwright JSON report, one per project it ran in. The report's
// top suites are the spec files; the titles are those of the describe blocks within.
function* tests(suite, titles = []) {
  for (const spec of suite.specs ?? []) {
    for (const test of spec.tests ?? []) {
      const failure = (test.results ?? []).find((r) => r.status !== "passed" && r.status !== "skipped");
      yield {
        file: spec.file,
        line: spec.line,
        title: [...titles, spec.title].join(" › "),
        project: test.projectName,
        status: test.status,
        error: firstLine(failure?.error?.message ?? failure?.errors?.[0]?.message),
      };
    }
  }
  for (const child of suite.suites ?? []) yield* tests(child, [...titles, child.title]);
}

function shard(reportPath, outPath) {
  const name = `e2e shard ${process.env.SHARD ?? ""}`.trim();
  if (!existsSync(reportPath)) {
    summary(`### Flaky tests, ${name}\n\nNo Playwright report to read.`);
    return;
  }
  const report = JSON.parse(readFileSync(reportPath, "utf8"));
  const all = (report.suites ?? []).flatMap((suite) => [...tests(suite)]);
  const flaky = all.filter((t) => t.status === "flaky");
  const failed = all.filter((t) => t.status === "unexpected");
  if (flaky.length === 0) {
    summary(`### Flaky tests, ${name}\n\nNone: no test needed its retry.`);
  } else {
    const rows = flaky.map((t) => `| ${cell(t.title)} | ${cell(t.project)} | \`${cell(t.file)}:${t.line}\` | ${cell(t.error)} |`);
    summary(
      [
        `### Flaky tests, ${name}`,
        "",
        `${flaky.length} test${flaky.length === 1 ? "" : "s"} failed, then passed on the retry:`,
        "",
        "| Test | Project | Where | First failure |",
        "| --- | --- | --- | --- |",
        ...rows,
      ].join("\n"),
    );
    for (const t of flaky) {
      console.log(`::warning file=frontend/e2e/${t.file},line=${t.line},title=Flaky e2e test::${command(`${t.title}${t.project ? ` (${t.project})` : ""} failed, then passed on the retry: ${t.error}`)}`);
    }
  }
  if (flaky.length || failed.length) {
    const env = process.env;
    const out = {
      run_id: Number(env.GITHUB_RUN_ID) || null,
      run_attempt: Number(env.GITHUB_RUN_ATTEMPT) || 1,
      shard: env.SHARD ?? null,
      branch: env.GITHUB_HEAD_REF || env.GITHUB_REF_NAME || null,
      sha: env.GITHUB_SHA ?? null,
      flaky,
      failed,
    };
    writeFileSync(outPath, JSON.stringify(out, null, 2));
  }
}

async function rollup(outDir) {
  const { GITHUB_TOKEN: token, GITHUB_REPOSITORY: repo } = process.env;
  const days = Number(process.env.FLAKY_DAYS) || 14;
  const since = new Date(Date.now() - days * 86_400_000).toISOString();
  const api = async (path) => {
    const response = await fetch(`https://api.github.com/repos/${repo}/${path}`, {
      headers: { authorization: `Bearer ${token}`, accept: "application/vnd.github+json" },
    });
    if (!response.ok) throw new Error(`${path}: ${response.status}`);
    return response;
  };

  // The repository's artifacts come newest first.
  const artifacts = [];
  for (let page = 1; page <= 50; page++) {
    const { artifacts: batch } = await (await api(`actions/artifacts?per_page=100&page=${page}`)).json();
    artifacts.push(...batch.filter((a) => a.name.startsWith("e2e-flaky-") && !a.expired && a.created_at >= since));
    if (batch.length < 100 || batch.at(-1).created_at < since) break;
  }

  const downloads = join(outDir, "downloads");
  mkdirSync(downloads, { recursive: true });
  const reports = [];
  for (const artifact of artifacts) {
    try {
      const zip = join(downloads, `${artifact.id}.zip`);
      writeFileSync(zip, Buffer.from(await (await api(`actions/artifacts/${artifact.id}/zip`)).arrayBuffer()));
      const dir = join(downloads, String(artifact.id));
      execFileSync("unzip", ["-o", "-q", zip, "-d", dir]);
      for (const file of readdirSync(dir).filter((f) => f.endsWith(".json"))) {
        reports.push(JSON.parse(readFileSync(join(dir, file), "utf8")));
      }
    } catch (error) {
      console.log(`Skipped artifact ${artifact.id}: ${error.message}`);
    }
  }

  // A test that failed in one attempt of a run, in a run whose last attempt passed:
  // it passed when the job was re-run.
  const runs = new Map();
  for (const id of new Set(reports.map((r) => r.run_id).filter(Boolean))) {
    try {
      runs.set(id, await (await api(`actions/runs/${id}`)).json());
    } catch (error) {
      console.log(`Skipped run ${id}: ${error.message}`);
    }
  }

  const seen = new Map();
  const note = (t, report, how) => {
    const key = `${t.file}\u0000${t.title}`;
    const entry = seen.get(key) ?? { title: t.title, file: t.file, line: t.line, projects: new Set(), runs: new Map(), how: new Set(), error: t.error };
    entry.projects.add(t.project);
    entry.how.add(how);
    const run = runs.get(report.run_id);
    entry.runs.set(report.run_id, { url: run?.html_url, branch: report.branch, at: run?.run_started_at ?? run?.created_at });
    seen.set(key, entry);
  };
  for (const report of reports) {
    for (const t of report.flaky ?? []) note(t, report, "retry");
    const run = runs.get(report.run_id);
    if (run?.conclusion === "success" && run.run_attempt > report.run_attempt) {
      for (const t of report.failed ?? []) note(t, report, "re-run");
    }
  }

  const list = [...seen.values()].sort((a, b) => b.runs.size - a.runs.size || a.title.localeCompare(b.title));
  const lines = [`## Flaky e2e tests, last ${days} days`, ""];
  if (list.length === 0) {
    lines.push(`None: no e2e test failed and then passed, on a retry or a re-run, since ${since.slice(0, 10)}.`);
  } else {
    lines.push(
      `Tests that failed and then passed, on Playwright's retry or a re-run of the job, since ${since.slice(0, 10)}. Most runs first.`,
      "",
      "| Test | Where | Runs | Passed on | Projects | Failure | Seen in |",
      "| --- | --- | --- | --- | --- | --- | --- |",
    );
    for (const e of list) {
      const links = [...e.runs.values()]
        .sort((a, b) => String(b.at).localeCompare(String(a.at)))
        .slice(0, 5)
        .map((r) => (r.url ? `[${cell(r.branch ?? "run")}](${r.url})` : cell(r.branch ?? "run")))
        .join(", ");
      lines.push(
        `| ${cell(e.title)} | \`${cell(e.file)}:${e.line}\` | ${e.runs.size} | ${[...e.how].join(", ")} | ${[...e.projects].join(", ")} | ${cell(e.error)} | ${links} |`,
      );
    }
  }
  lines.push("", `From ${reports.length} shard report${reports.length === 1 ? "" : "s"} in ${runs.size} run${runs.size === 1 ? "" : "s"}.`);
  const markdown = lines.join("\n");
  summary(markdown);
  writeFileSync(join(outDir, "flaky-tests.md"), markdown + "\n");
  writeFileSync(
    join(outDir, "flaky-tests.json"),
    JSON.stringify(
      list.map((e) => ({ ...e, projects: [...e.projects], how: [...e.how], runs: [...e.runs.values()] })),
      null,
      2,
    ),
  );
}

try {
  const [mode, ...args] = process.argv.slice(2);
  if (mode === "shard") shard(args[0], args[1]);
  else if (mode === "rollup") await rollup(args[0] ?? "flaky-tests");
  else console.log("Usage: flaky-tests.mjs shard <report.json> <out.json> | rollup <out-dir>");
} catch (error) {
  console.log(`::warning title=Flaky-test report::${command(`The flaky-test report could not be made: ${error.message}`)}`);
}
